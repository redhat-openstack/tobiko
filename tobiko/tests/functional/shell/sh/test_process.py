# Copyright (c) 2021 Red Hat, Inc.
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
from tobiko.openstack import keystone
from tobiko.openstack import stacks
from tobiko.shell import sh
from tobiko.shell import ssh


class ProcessFixture(tobiko.SharedFixture):

    temp_filename: str
    ssh_client: ssh.SSHClientType = None
    process: sh.ShellProcessFixture

    def setup_fixture(self):
        self.temp_filename = sh.execute(
            'mktemp', ssh_client=self.ssh_client).stdout.strip()
        self.addCleanup(sh.execute,
                        f"rm -f '{self.temp_filename}'",
                        ssh_client=self.ssh_client)
        self.process = sh.process(f"tail -f '{self.temp_filename}'",
                                  ssh_client=self.ssh_client)
        self.process.execute()
        self.addCleanup(self.process.kill)


class ProcessTest(testtools.TestCase):

    fixture = tobiko.required_fixture(ProcessFixture)

    def test_stdout(self):
        fixture = self.fixture
        sh.execute(f"echo some text > '{fixture.temp_filename}'",
                   ssh_client=fixture.ssh_client)
        line = self.fixture.process.stdout.readline()
        self.assertEqual(b'some text\n', line)


class LocalProcessFixture(ProcessFixture):

    ssh_client: ssh.SSHClientType = False


class LocalProcessTest(ProcessTest):

    fixture = tobiko.required_fixture(LocalProcessFixture)


class SSHProcessFixture(ProcessFixture):

    stack = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)

    def setup_fixture(self):
        self.ssh_client = self.stack.ssh_client
        super().setup_fixture()


@keystone.skip_unless_has_keystone_credentials()
class SSHProcessTest(ProcessTest):

    fixture = tobiko.required_fixture(SSHProcessFixture)


class CirrosProcessFixture(SSHProcessFixture):

    stack = tobiko.required_fixture(
        stacks.CirrosServerStackFixture)


@keystone.skip_unless_has_keystone_credentials()
class CirrosProcessTest(ProcessTest):

    fixture = tobiko.required_fixture(CirrosProcessFixture)
