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

import netaddr
import testtools

import tobiko
from tobiko.shell import ifconfig
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.openstack import keystone
from tobiko.openstack import stacks


class IfconfigTest(testtools.TestCase):

    cirros_stack = tobiko.required_fixture(
        stacks.CirrosServerStackFixture)

    advanced_vm_stack = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)

    def test_list_ip_addresses(self, ip_version=None, **execute_params):
        result = sh.execute(command='ls /sbin/ifconfig',
                            expect_exit_status=None, **execute_params)
        if result.exit_status != 0:
            self.skip(f"{result.stderr}")

        ips = ifconfig.list_ip_addresses(ip_version=ip_version,
                                         **execute_params)
        self.assertIsInstance(ips, tobiko.Selection)
        for ip in ips:
            self.assertIsInstance(ip, netaddr.IPAddress)
        if ip_version:
            self.assertEqual(ips.with_attributes(version=ip_version), ips)

    def test_list_ip_addresses_with_ipv4(self):
        self.test_list_ip_addresses(ip_version=4)

    def test_list_ip_addresses_with_ipv6(self):
        self.test_list_ip_addresses(ip_version=6)

    @keystone.skip_unless_has_keystone_credentials()
    def test_list_ip_addresses_with_cirros_server(self):
        self.test_list_ip_addresses(ssh_client=self.cirros_stack.ssh_client)

    @keystone.skip_unless_has_keystone_credentials()
    def test_list_ip_addresses_with_advanced_server(self):
        self.test_list_ip_addresses(
            ssh_client=self.advanced_vm_stack.ssh_client)

    def test_list_ip_addresses_with_proxy_ssh_client(self):
        ssh_client = ssh.ssh_proxy_client()
        if ssh_client is None:
            self.skip('SSH proxy server not configured')
        self.test_list_ip_addresses(ssh_client=ssh_client)
