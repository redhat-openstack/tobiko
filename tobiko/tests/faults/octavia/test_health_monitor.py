# Copyright (c) 2025 Red Hat
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
# mypy: disable-error-code="attr-defined"
from __future__ import absolute_import

import testtools
from oslo_log import log

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import octavia
from tobiko.openstack import nova
from tobiko.openstack import stacks


LOG = log.getLogger(__name__)


@neutron.skip_unless_is_ovn()
@keystone.skip_if_missing_service(name='octavia')
class OctaviaOVNProviderHealthMonitorTest(testtools.TestCase):
    # pylint: disable=no-member
    """Octavia OVN provider health monitor test.

    Create an OVN provider load balancer with 2 members.
    Create a client that is connected to the load balancer
    Create a health monitor that is connected to the load balancer,
    pause server one validate degraded status
    pause other server validate error status
    bring both servers back and validate status
    """
    lb = None
    listener = None
    pool = None
    health_monitor = None
    server_stack = tobiko.required_fixture(
        stacks.OctaviaServerStackFixture)
    other_server_stack = tobiko.required_fixture(
        stacks.OctaviaOtherServerStackFixture)

    def setUp(self):
        # pylint: disable=no-member
        super(OctaviaOVNProviderHealthMonitorTest, self).setUp()

        self.lb, self.listener, self.pool = octavia.deploy_ipv4_ovn_lb(
            servers_stacks=[self.server_stack, self.other_server_stack]
        )

        self.health_monitor = octavia.deploy_hm(
            octavia.OVN_PROVIDER, octavia.HM_OVN_NAME, self.pool.id)

    def test_hm(self) -> None:
        # Wait for health monitor to be ONLINE
        octavia.wait_for_status(
            object_id=self.health_monitor.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.ONLINE,
            get_client=octavia.get_health_monitor
        )
        LOG.info(f"Health monitor {self.health_monitor.name} is ONLINE")

        # Wait for load balancer to be ONLINE
        octavia.wait_for_status(
            object_id=self.lb.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.ONLINE,
            get_client=octavia.get_load_balancer
        )
        LOG.info(f"Load balancer {self.lb.name} is ONLINE")

        # Get member IPs and port from the server stacks and listener
        server_one_ip = str(self.server_stack.fixed_ipv4)
        other_server_ip = str(self.other_server_stack.fixed_ipv4)
        protocol_port = self.listener.protocol_port

        # Wait for OVN Service_Monitor entries to be online
        # This ensures ovn-controller has completed initial health checks
        octavia.wait_for_ovn_service_monitor_status(
            member_ip=server_one_ip,
            protocol_port=protocol_port,
            expected_status='online')
        octavia.wait_for_ovn_service_monitor_status(
            member_ip=other_server_ip,
            protocol_port=protocol_port,
            expected_status='online')
        LOG.info(f"Service_Monitor for {server_one_ip}:{protocol_port} and "
                 f"{other_server_ip}:{protocol_port} are online")

        # Stop first server and wait for DEGRADED status
        server_one = nova.find_server(
            id=self.server_stack.outputs.server_id)
        other_server = nova.find_server(
            id=self.other_server_stack.outputs.server_id)

        server_one.stop()
        nova.wait_for_server_status(server=server_one.id, timeout=900,
                                    status='SHUTOFF')

        # Wait for Service_Monitor to reflect the change
        octavia.wait_for_ovn_service_monitor_status(
            member_ip=server_one_ip,
            protocol_port=protocol_port,
            expected_status='offline')
        LOG.info(f"Service_Monitor for {server_one_ip}:{protocol_port} is "
                 "offline")

        octavia.wait_for_status(
            object_id=self.lb.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.DEGRADED,
            get_client=octavia.get_load_balancer
        )
        LOG.info(f"Load balancer {self.lb.name} is DEGRADED after stopping "
                 "first server")

        # Stop second server and wait for ERROR status
        other_server.stop()
        nova.wait_for_server_status(server=other_server.id,  timeout=900,
                                    status='SHUTOFF')

        # Wait for Service_Monitor to reflect the change
        octavia.wait_for_ovn_service_monitor_status(
            member_ip=other_server_ip,
            protocol_port=protocol_port,
            expected_status='offline')
        LOG.info(f"Service_Monitor for {other_server_ip}:{protocol_port} is "
                 "offline")

        octavia.wait_for_status(
            object_id=self.lb.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.ERROR,
            get_client=octavia.get_load_balancer
        )
        LOG.info(f"Load balancer {self.lb.name} is ERROR after stopping both "
                 "servers")

        # Start second server and wait for DEGRADED status
        other_server.start()
        nova.wait_for_server_status(server=other_server.id,  timeout=900,
                                    status='ACTIVE')

        # Wait for Service_Monitor to reflect the change
        octavia.wait_for_ovn_service_monitor_status(
            member_ip=other_server_ip,
            protocol_port=protocol_port,
            expected_status='online')
        LOG.info(f"Service_Monitor for {other_server_ip}:{protocol_port} is "
                 "online")

        octavia.wait_for_status(
            object_id=self.lb.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.DEGRADED,
            get_client=octavia.get_load_balancer
        )
        LOG.info(f"Load balancer {self.lb.name} is DEGRADED after starting "
                 "second server")

        # Start first server and wait for ONLINE status
        server_one.start()
        nova.wait_for_server_status(server=server_one.id,  timeout=900,
                                    status='ACTIVE')

        # Wait for Service_Monitor to reflect the change
        octavia.wait_for_ovn_service_monitor_status(
            member_ip=server_one_ip,
            protocol_port=protocol_port,
            expected_status='online')
        LOG.info(f"Service_Monitor for {server_one_ip}:{protocol_port} is "
                 "online")

        octavia.wait_for_status(
            object_id=self.lb.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.ONLINE,
            get_client=octavia.get_load_balancer
        )
        LOG.info(f"Load balancer {self.lb.name} is ONLINE after starting "
                 "both servers")
