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

import testtools
from oslo_log import log

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import octavia
from tobiko.openstack import stacks
from tobiko.shell import sh
from tobiko import tripleo


LOG = log.getLogger(__name__)


@keystone.skip_if_missing_service(name='octavia')
@tripleo.skip_if_missing_overcloud
class OctaviaBasicFaultTest(testtools.TestCase):
    """Octavia fault scenario test.

    Create a load balancer with 2 members that run a server application,
    Create a client that is connected to the load balancer VIP port,
    Generate network traffic from the client to the load balancer VIP.
    Restart the amphora's compute node to create a failover.
    Reach the members to make sure they are ready to be checked.
    Generate network traffic again to verify Octavia functionality.
    """
    lb = None
    listener = None
    pool = None
    server_stack = tobiko.required_fixture(
        stacks.UbuntuServerStackFixture)
    other_server_stack = tobiko.required_fixture(
        stacks.OctaviaOtherServerStackFixture)

    def setUp(self):
        # pylint: disable=no-member
        super(OctaviaBasicFaultTest, self).setUp()

        self.lb, self.listener, self.pool = octavia.deploy_ipv4_amphora_lb(
            servers_stacks=[self.server_stack, self.other_server_stack]
        )

        self._send_http_traffic()

    def _send_http_traffic(self):
        # For 5 minutes we ignore specific exceptions as we know
        # that Octavia resources are being provisioned
        for attempt in tobiko.retry(timeout=300.):
            try:
                octavia.check_members_balanced(
                    pool_id=self.pool.id,
                    ip_address=self.lb.vip_address,
                    lb_algorithm=self.pool.lb_algorithm,
                    protocol=self.listener.protocol,
                    port=self.listener.protocol_port)
                break
            except (octavia.RoundRobinException,
                    octavia.TrafficTimeoutError,
                    sh.ShellCommandFailed):
                LOG.exception(
                    f"Traffic didn't reach all members after "
                    f"#{attempt.number} attempts and "
                    f"{attempt.elapsed_time} seconds")
                if attempt.is_last:
                    raise

    def test_reboot_amphora_compute_node(self):
        amphora_compute_host = octavia.get_amphora_compute_node(
            load_balancer_id=self.lb.id,
            port=self.listener.protocol_port,
            protocol=self.listener.protocol,
            ip_address=self.lb.vip_address)

        LOG.debug('Rebooting compute node...')

        # Reboot Amphora's compute node will initiate a failover
        amphora_compute_host.reboot_node()

        LOG.debug('Compute node has been rebooted')

        # Wait for the LB to be updated
        try:
            octavia.wait_for_status(object_id=self.lb.id)

        # The reboot_overcloud_node function restarts other running nova
        # vms/backend servers after the compute node reboot by default.
        # Those restart operations may take longer than the LB transitions into
        # PENDING_UPDATE and then into ACTIVE altogether. So if the restarted
        # vms will finish their restart process after the LB reaches ACTIVE
        # status, the lb will never reach PENDING_UPDATE
        except tobiko.RetryTimeLimitError:
            LOG.info('The restarted servers/backend members reached ACTIVE '
                     'status after the LB finished its update process, hence '
                     'no exception is being raised even though the update '
                     'timeout was reached.')

        octavia.wait_for_status(object_id=self.lb.id)

        LOG.debug(f'Load Balancer {self.lb.id} is ACTIVE')

        self._send_http_traffic()

    def test_kill_amphora_agent(self):
        """Kill the MASTER amphora agent

        This test kills the amphora agent on the MASTER amphora.
        Killing the amphora agent will cause a failover.

        Octavia's functionality will be verified afterwards.
        """

        self._skip_if_not_active_standby()

        # Finding the amphora agent pid and kill it
        amp_agent_pid_command = (
            "ps -ef | awk '/amphora/{print $2}' | head -n 1")
        amp_agent_pid = octavia.run_command_on_amphora(
            command=amp_agent_pid_command,
            lb_id=self.lb.id,
            lb_vip=self.lb.vip_address)
        LOG.info(f'The amp_agent_pid is {amp_agent_pid}')

        octavia.run_command_on_amphora(
            command=f'kill -9 {amp_agent_pid}',
            lb_id=self.lb.id,
            lb_vip=self.lb.vip_address,
            sudo=True)

        self._wait_for_failover_and_test_functionality()

    def test_stop_keepalived(self):
        """Stop keepalived on MASTER amphora

        This test stops keepalived on the MASTER amphora.
        Stopping keepalived on the amphora will cause a failover.

        Octavia's functionality will be verified afterwards.
        """

        self._skip_if_not_active_standby()

        stop_keepalived_cmd = 'systemctl stop octavia-keepalived'

        octavia.run_command_on_amphora(
            command=stop_keepalived_cmd,
            lb_id=self.lb.id,
            lb_vip=self.lb.vip_address,
            sudo=True)

        self._wait_for_failover_and_test_functionality()

    def test_stop_haproxy(self):
        """Stop haproxy on MASTER amphora

        This test stops haproxy on the MASTER amphora.
        Stopping haproxy on the amphora will cause a failover.

        Octavia's functionality will be verified afterwards.
        """

        self._skip_if_not_active_standby()

        # Finding the amphora haproxy unit name and stop it
        amp_haproxy_unit_command = (
            "systemctl list-units | awk '/haproxy-/{print $1}'")

        for attempt in tobiko.retry(timeout=300., interval=5.):
            amp_haproxy_unit = octavia.run_command_on_amphora(
                command=amp_haproxy_unit_command,
                lb_id=self.lb.id,
                lb_vip=self.lb.vip_address)

            if amp_haproxy_unit:
                break

            # it will raise tobiko.RetryTimeLimitError in case of timeout
            attempt.check_limits()

            LOG.debug(f"Waiting for haproxy instance on LB {self.lb.id} to get"
                      " the haproxy unit id")

        LOG.info(f'The amp_haproxy_unit is {amp_haproxy_unit}')

        octavia.run_command_on_amphora(
            command=f'systemctl stop {amp_haproxy_unit}',
            lb_id=self.lb.id,
            lb_vip=self.lb.vip_address,
            sudo=True)

        self._wait_for_failover_and_test_functionality()

    def _skip_if_not_active_standby(self):
        """Skip the test if Octavia doesn't use Active/standby topology
        """
        if len(list(octavia.list_amphorae(load_balancer_id=self.lb.id))) < 2:
            skipping_stmt = ('Skipping the test as it requires '
                             'Active/standby topology.')
            LOG.info(skipping_stmt)
            self.skipTest(skipping_stmt)

    def _wait_for_failover_and_test_functionality(self, timeout=70):
        """Wait for failover to end and test Octavia functionality"""

        octavia.wait_for_status(object_id=self.lb.id,
                                status=octavia.PENDING_UPDATE,
                                timeout=timeout)

        octavia.wait_for_status(object_id=self.lb.id)

        LOG.debug(f'Load Balancer {self.lb.id} is ACTIVE')

        self._send_http_traffic()
