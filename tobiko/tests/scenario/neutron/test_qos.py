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

from oslo_log import log
import testtools

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import stacks
from tobiko.shell import ip
from tobiko.shell import iperf3
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.shell import tcpdump


CONF = config.CONF
LOG = log.getLogger(__name__)


@keystone.skip_unless_has_keystone_credentials()
@neutron.skip_if_is_old_ovn()
class QoSNetworkTest(testtools.TestCase):
    """Tests QoS basic functionality"""

    #: Resources stacks with QoS Policy and QoS Rules and Advanced server
    network = tobiko.required_fixture(stacks.QosNetworkStackFixture)
    policy = tobiko.required_fixture(stacks.QosPolicyStackFixture)
    server = tobiko.required_fixture(stacks.QosServerStackFixture)

    def setUp(self):
        super(QoSNetworkTest, self).setUp()
        # this is executed simply to wait until the server boot is completed
        sh.get_hostname(self.server.ssh_client)

    def test_ping_dscp(self):
        capture_file = sh.execute('mktemp', sudo=True).stdout.strip()
        interface = (CONF.tobiko.neutron.dscp_capture_interface or
                     ip.get_network_main_route_device(
                         self.server.floating_ip_address))

        # IPv4 tcpdump DSCP filters explanation:
        # ip[1] refers to the byte 1 (the TOS byte) of the IP header
        # 0xfc = 11111100 is the mask to get only DSCP value from the ToS
        # As DSCP mark is most significant 6 bits we do right shift (>>)
        # twice in order to divide by 4 and compare with the decimal value
        # See details at http://darenmatthews.com/blog/?p=1199
        dscp_mark = CONF.tobiko.neutron.dscp_mark
        capture_filter = (f"'(ip src {self.server.floating_ip_address} and "
                          f"(ip[1] & 0xfc) >> 2 == {dscp_mark})'")

        # start a capture
        process = tcpdump.start_capture(
            capture_file=capture_file,
            interface=interface,
            capture_filter=capture_filter,
            capture_timeout=60)
        # send a ping to the server
        ping.assert_reachable_hosts([self.server.floating_ip_address], count=5)
        # stop tcpdump and get the pcap capture
        pcap = tcpdump.get_pcap(process, capture_file=capture_file)
        # check the capture is not empty
        tcpdump.assert_pcap_is_not_empty(pcap=pcap)

    def test_network_qos_policy_id(self):
        """Verify network policy ID"""
        self.assertEqual(self.policy.qos_policy_id,
                         self.network.qos_policy_id)

    def test_server_qos_policy_id(self):
        """Verify server policy ID"""
        self.assertIsNone(self.server.port_details['qos_policy_id'])

    def test_qos_bw_limit(self):
        """Verify BW limit using the iperf3 tool"""
        self.server.wait_for_iperf3_server()
        # localhost will act as client
        bandwidth_limit = self.policy.bwlimit_kbps * 1000.
        for attempt in tobiko.retry(timeout=100., interval=5.):
            try:
                iperf3.assert_has_bandwith_limits(
                    address=self.server.ip_address,
                    min_bandwith=bandwidth_limit * 0.85,
                    max_bandwith=bandwidth_limit * 1.15,
                    port=self.server.iperf3_port,
                    download=True)
                break
            except sh.ShellCommandFailed as err:
                if ('unable to connect to server: Connection refused'
                        in str(err)):
                    attempt.check_limits()
                    LOG.debug('iperf command failed because the iperf server '
                              'was not ready yet - retrying...')
                else:
                    raise err
