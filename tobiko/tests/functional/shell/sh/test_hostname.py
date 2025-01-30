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

import socket

import testtools

import tobiko
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.openstack import keystone
from tobiko.openstack import stacks


class GetHostnameTest(testtools.TestCase):

    def test_hostname(self,
                      expect_hostname: str = None,
                      **execute_params):
        hostname = sh.get_hostname(**execute_params)
        self.assertIsInstance(hostname, str)
        if expect_hostname:
            self.assertEqual(expect_hostname, hostname)
        else:
            self.assertNotEqual('', hostname)

    def test_local_hostname(self):
        self.test_hostname(expect_hostname=socket.gethostname(),
                           ssh_client=False)

    def test_ssh_hostname(self,
                          ssh_client: ssh.SSHClientFixture = None):
        fixture = ssh.ssh_client_fixture(ssh_client)
        if fixture is None:
            expect_hostname = socket.gethostname()
        else:
            stdin, stdput, stderr = fixture.connect().exec_command('hostname')
            stdin.close()
            self.assertEqual(b'', stderr.read())
            expect_hostname = stdput.read().decode().strip()
        self.test_hostname(ssh_client=ssh_client,
                           expect_hostname=expect_hostname)

    def test_ssh_proxy_hostname(self):
        ssh_client = ssh.ssh_proxy_client()
        if ssh_client is None:
            tobiko.skip_test('SSH proxy server is not configured')
        self.test_ssh_hostname(ssh_client=ssh_client)

    cirros_server = tobiko.required_fixture(
        stacks.CirrosServerStackFixture)

    @keystone.skip_unless_has_keystone_credentials()
    def test_cirros_hostname(self):
        self.test_ssh_hostname(ssh_client=self.cirros_server.ssh_client)

    advanced_server = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)

    @keystone.skip_unless_has_keystone_credentials()
    def test_advanced_vm_hostname(self):
        self.test_ssh_hostname(ssh_client=self.advanced_server.ssh_client)
