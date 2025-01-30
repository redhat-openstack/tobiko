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

import os

import testtools

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import stacks
from tobiko.shell import sh
from tobiko.shell import ssh


CONF = config.CONF


class WhichTest(testtools.TestCase):

    @property
    def ssh_client(self) -> ssh.SSHClientType:
        return False

    def test_find_command(self):
        result = sh.find_command(command='which',
                                 ssh_client=self.ssh_client)
        self.assertEqual('which', os.path.basename(result))

    def test_find_command_with_invalid(self):
        ex = self.assertRaises(sh.CommandNotFound,
                               sh.find_command,
                               command='<invalid_command>',
                               ssh_client=self.ssh_client)
        self.assertEqual('<invalid_command>', ex.command)
        self.assertEqual(sh.get_hostname(ssh_client=self.ssh_client),
                         ex.hostname)
        self.assertIsInstance(ex.__cause__, sh.ShellCommandFailed)

    def test_find_command_with_skip(self):
        result = sh.find_command(command='which',
                                 ssh_client=self.ssh_client,
                                 skip=True)
        self.assertEqual('which', os.path.basename(result))

    def test_find_command_with_invalid_and_skip(self):
        ex = self.assertRaises(sh.SkipOnCommandNotFound,
                               sh.find_command,
                               command='<invalid_command>',
                               skip=True,
                               ssh_client=self.ssh_client)
        self.assertIsInstance(ex, tobiko.SkipException)
        self.assertIsInstance(ex, sh.CommandNotFound)
        self.assertEqual('<invalid_command>', ex.command)
        self.assertEqual(sh.get_hostname(ssh_client=self.ssh_client),
                         ex.hostname)
        self.assertIsInstance(ex.__cause__, sh.ShellCommandFailed)


class ProxyJumpWhichTest(WhichTest):

    def setUp(self):
        super().setUp()
        if ssh.ssh_proxy_client() is None:
            self.skipTest('SSH proxy jump not configured')

    @property
    def ssh_client(self) -> ssh.SSHClientType:
        return None


@keystone.skip_unless_has_keystone_credentials()
class SSHWhichTest(WhichTest):

    server_stack = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)

    @property
    def ssh_client(self):
        return self.server_stack.ssh_client


@keystone.skip_unless_has_keystone_credentials()
class CirrosExecuteTest(SSHWhichTest):
    server_stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)
