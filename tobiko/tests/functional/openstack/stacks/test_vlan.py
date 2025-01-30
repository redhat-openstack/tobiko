# Copyright (c) 2019 Red Hat, Inc.
#
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

import tobiko
from tobiko.openstack import stacks
from tobiko.shell import ip
from tobiko.tests.functional.openstack.stacks import test_cirros


class VlanProxyServerStackTest(test_cirros.CirrosServerStackTest):

    #: Stack of resources with a server attached to a floating IP
    stack = tobiko.required_fixture(stacks.VlanProxyServerStackFixture)


class AdvancedVlanServerTest(testtools.TestCase):

    #: Stack of resources with a server attached to a floating IP
    stack = tobiko.required_fixture(stacks.AdvancedServerStackFixture)

    def test_vlan_ipv4_fixed_ip(self):
        self._test_vlan_fixed_ip(ip_version=4)

    def test_vlan_ipv6_fixed_ip(self):
        self._test_vlan_fixed_ip(ip_version=6)

    def _test_vlan_fixed_ip(self, ip_version: int):
        expected_ip = self.get_vlan_fixed_ip(ip_version=ip_version)
        for attempt in tobiko.retry(timeout=600.,
                                    interval=10.):
            try:
                actual_ip = ip.find_ip_address(
                    device=self.stack.vlan_device,
                    ip_version=ip_version,
                    ssh_client=self.stack.ssh_client,
                    scope='global',
                    unique=True)
            except tobiko.ObjectNotFound:
                attempt.check_limits()
            else:
                break
        else:
            raise RuntimeError('Broken retry loop')
        self.assertEqual(expected_ip, actual_ip)
        self.stack.assert_vlan_is_reachable(ip_version=ip_version)

    def get_vlan_fixed_ip(self, ip_version: int):
        try:
            return self.stack.find_vlan_fixed_ip(ip_version=ip_version)
        except tobiko.ObjectNotFound:
            self.skipTest(f"Server {self.stack.server_id} has any "
                          f"IPv{ip_version} address on VLAN device.")
