# Copyright (c) 2021 Red Hat
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from __future__ import absolute_import

import typing
import collections

import testtools
from oslo_log import log

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import octavia
from tobiko.openstack import stacks
from tobiko.openstack import topology
from tobiko.shell import sh
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


@keystone.skip_if_missing_service(name='octavia')
class OctaviaServicesFaultTest(testtools.TestCase):
    """Octavia services fault test.

    Create a load balancer with 2 members that run a server application,
    Create a client that is connected to the load balancer VIP port,
    Generate network traffic from the client to the load balancer while
    stopping some of the Octavia's services which run under podman container
    runtime environment.

    Each service will be running as a single instance.
    E.g. only one WORKER_SERVICE will run in all controllers, the same for
    API_SERVICE etc.

    Then we test that traffic which is being sent from the client to the LB
    is received as expected.
    """
    lb = None
    listener = None
    pool = None
    server_stack = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)
    other_server_stack = tobiko.required_fixture(
        stacks.OctaviaOtherServerStackFixture)

    # ssh clients of the participating TripleO nodes
    ssh_clients: typing.List[ssh.SSHClientFixture] = list()

    def setUp(self):
        # pylint: disable=no-member
        super(OctaviaServicesFaultTest, self).setUp()

        # Skipping the test if there are not enough instances of the services
        # (if there is only 1 controller and 1 networker, we cannot stop any
        # Octavia service)
        critical_nodes_number = len(
            topology.list_openstack_nodes(group='controller'))
        try:
            networker_nodes = topology.list_openstack_nodes(group='networker')
            critical_nodes_number += len(networker_nodes)
        except topology.NoSuchOpenStackTopologyNodeGroup:
            pass  # Current Octavia architecture doesn't support networker node

        if critical_nodes_number < 2:
            skip_reason = "The number of controllers and networker should be" \
                          " more than 1 for this test, otherwise each " \
                          "service is necessary."
            self.skipTest(skip_reason)

        self.lb, self.listener, self.pool = octavia.deploy_ipv4_amphora_lb(
            servers_stacks=[self.server_stack, self.other_server_stack]
        )

        self._send_http_traffic()

    def _send_http_traffic(self):
        # For 30 seconds we ignore the OctaviaClientException as we know
        # that Octavia services are being stopped and restarted
        for attempt in tobiko.retry(timeout=30.):
            try:
                octavia.check_members_balanced(
                    pool_id=self.pool.id,
                    ip_address=self.lb.vip_address,
                    lb_algorithm=self.pool.lb_algorithm,
                    protocol=self.listener.protocol,
                    port=self.listener.protocol_port)
                break
            except octavia.OctaviaClientException:
                LOG.exception(f"Octavia service was unavailable after "
                              f"#{attempt.number} attempts and "
                              f"{attempt.elapsed_time} seconds")
                if attempt.is_last:
                    raise

    def test_services_fault(self):
        # We get the services we want to stop on all nodes, in a way we leave
        # only one instance of every service on all nodes accumulatively
        services_to_stop = self._get_services_to_stop()

        try:
            self._stop_octavia_main_services(services_to_stop)

        finally:
            self._start_octavia_main_services(services_to_stop)

    def _get_services_to_stop(self) -> dict:
        """Return the running octavia services on controller & networker nodes.

        This method returns a dictionary of the services we are going to stop
        as keys, and the nodes we are going to stop the services on as values.

        For example:
        {
            'tripleo_octavia_worker.service': [ssh_client_of_controller-0,
                                               ssh_client_of_controller-1],
            'tripleo_octavia_api.service': [ssh_client_of_controller-1,
                                            ssh_client_of_controller-2]
             and so on....
        }

        We are leaving exactly one running instance of each service on all
        nodes together.
        The Octavia service that will remain running will be chosen randomly.
        """

        # Gather all controller ssh clients
        for controller in topology.list_openstack_nodes(group='controller'):
            self.ssh_clients.append(controller.ssh_client)

        # Gather all networker ssh clients if reachable
        # (for Composable and Upgrade jobs)
        try:
            for networker in topology.list_openstack_nodes(
                    group='networker'):
                self.ssh_clients.append(networker.ssh_client)
        except topology.NoSuchOpenStackTopologyNodeGroup:
            pass

        # Creating initial mapping of Octavia active units (services) which are
        # currently running on the nodes we gathered above
        services_on_nodes = collections.defaultdict(list)

        # Gathering all Octavia active units (services) which are currently
        # running on the nodes we gathered above
        for ssh_client in self.ssh_clients:
            for service in sh.list_systemd_units(ssh_client=ssh_client):
                if service.unit in octavia.OCTAVIA_SERVICES:
                    services_on_nodes[service.unit].append(ssh_client)

        # Example of the current services_on_nodes:
        # {
        #     'tripleo_octavia_worker.service': [ssh_client_of_controller-0,
        #                                        ssh_client_of_controller-1],
        #     'tripleo_octavia_api.service': [ssh_client_of_controller-1,
        #                                     ssh_client_of_controller-2]
        #      and so on....
        # }

        LOG.debug(f'Full services_on_nodes dictionary:\n {services_on_nodes}')

        # Pop one random node's ssh client from each service.
        # We do that so we could leave exactly one single instance of each
        # service running on all nodes
        import random
        for service in services_on_nodes:
            nodes_length = len(services_on_nodes[service])
            services_on_nodes[service].pop(random.randint(0, nodes_length - 1))

        return services_on_nodes

    def _stop_octavia_main_services(self, services_to_stop: dict):

        """Stops the provided octavia services.

        This method stops the provided octavia services.

        It then sends traffic to validate the Octavia's functionality
        """

        LOG.debug(f'Services we are going to stop:\n {services_to_stop}')

        for service, ssh_clients in services_to_stop.items():
            for ssh_client in ssh_clients:
                sh.stop_systemd_units(service, ssh_client=ssh_client)
                LOG.debug(f'We stopped {service} on {ssh_client.host}')

        octavia.wait_for_octavia_service()

        self._send_http_traffic()

    def _start_octavia_main_services(self, services_to_stop: dict):

        """Start the octavia services.

        This method starts the provided octavia services on the nodes we
        gathered before.

        It then sends traffic to validate the Octavia's functionality
        """

        for service, ssh_clients in services_to_stop.items():
            for ssh_client in ssh_clients:
                sh.start_systemd_units(service, ssh_client=ssh_client)

                LOG.debug(f'We started {service} on {ssh_client.host}')

        self._send_http_traffic()
