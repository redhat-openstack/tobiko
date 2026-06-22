# Copyright (c) 2026 Red Hat
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
from tobiko.openstack import neutron
from tobiko.openstack import octavia
from tobiko.openstack import stacks


LOG = log.getLogger(__name__)


@octavia.skip_unless_has_dual_stack_external
@neutron.skip_unless_is_ovn()
@keystone.skip_if_missing_service(name='octavia')
class OctaviaOVNDualStackTrafficTest(testtools.TestCase):
    """Octavia OVN dual-stack VIP traffic test.

    Create an OVN provider load balancer with IPv4 primary VIP and IPv6
    additional VIP, IPv4 and IPv6 pool members for each backend server, then
    verify TCP traffic to both VIP addresses.
    """
    lb = None
    listener = None
    pool = None
    server_stack = tobiko.required_fixture(
        stacks.OctaviaServerStackFixture)
    other_server_stack = tobiko.required_fixture(
        stacks.OctaviaOtherServerStackFixture)

    def setUp(self):
        # pylint: disable=no-member
        super(OctaviaOVNDualStackTrafficTest, self).setUp()

        self.lb, self.listener, self.pool = octavia.deploy_dual_stack_ovn_lb(
            servers_stacks=[self.server_stack, self.other_server_stack]
        )

    def test_ipv4_and_ipv6_vip_traffic(self):
        """Send traffic to IPv4 and IPv6 VIPs (SOURCE_IP_PORT pool)."""
        timeout = 300
        servers_count = 2  # server_stack + other_server_stack
        common = dict(
            pool_id=self.pool.id,
            lb_algorithm=self.pool.lb_algorithm,
            protocol=self.listener.protocol,
            port=self.listener.protocol_port,
            timeout=timeout,
            members_count=servers_count,
        )
        octavia.verify_lb_traffic(
            ip_address=self.lb.vip_address,
            **common)
        vip_v6 = octavia.ipv6_vip_from_load_balancer(self.lb)
        self.assertIsNotNone(
            vip_v6, 'No IPv6 additional VIP address on load balancer')
        octavia.verify_lb_traffic(
            ip_address=vip_v6,
            **common)
