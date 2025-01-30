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
import typing

import testtools

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import stacks
from tobiko.shell import sh
from tobiko.shell import ssh


CONF = config.CONF

SSH_EXPECTED_SHELL = None
LOCAL_EXPECTED_SHELL = '/bin/sh -c'


class ExecuteTest(testtools.TestCase):

    @property
    def expected_shell(self) -> typing.Optional[str]:
        if ssh.ssh_proxy_client() is None:
            return LOCAL_EXPECTED_SHELL
        else:
            return SSH_EXPECTED_SHELL

    def test_succeed(self,
                     command: sh.ShellCommandType = 'true',
                     stdin: str = None,
                     stdout: str = None,
                     stderr: str = None,
                     expect_exit_status: typing.Optional[int] = 0,
                     **kwargs):
        process = self.execute(command=command,
                               stdin=stdin,
                               stdout=bool(stdout),
                               stderr=bool(stderr),
                               expect_exit_status=expect_exit_status,
                               **kwargs)
        self.assertEqual(self.expected_command(command), process.command)
        if stdin:
            self.assertEqual(stdin, str(process.stdin))
        else:
            self.assertIsNone(process.stdin)
        if stdout:
            self.assertEqual(stdout, str(process.stdout))
        else:
            self.assertIsNone(process.stdout)
        if stderr:
            self.assertEqual(stderr, str(process.stderr))
        else:
            self.assertIsNone(process.stderr)
        if expect_exit_status is not None:
            self.assertEqual(0, process.exit_status)

    def test_succeed_with_command_list(self):
        self.test_succeed(['echo', 'something'],
                          stdout='something\n')

    def test_succeed_reading_from_stdout(self):
        self.test_succeed('echo something',
                          stdout='something\n')

    def test_succeed_reading_from_stderr(self):
        self.test_succeed('echo something >&2',
                          stderr='something\n')

    def test_succeed_writing_to_stdin(self):
        self.test_succeed('cat',
                          stdin='some input\n',
                          stdout='some input\n')

    def test_succeed_with_timeout(self):
        self.test_succeed(timeout=30.)

    def test_succeed_with_no_exit_status(self):
        self.test_succeed(command='false', expect_exit_status=None)

    def test_succeed_with_current_dir(self):
        temp_file = self.make_temporary()
        self.execute(command=f"echo '{self.id()}' > '{temp_file}'")
        self.test_succeed(command=f"cat './{os.path.basename(temp_file)}'",
                          current_dir=os.path.dirname(temp_file),
                          stdout=f"{self.id()}\n")

    def test_fails(self, command='false', exit_status=None, stdin=None,
                   stdout=None, stderr=None, expect_exit_status=0,
                   **kwargs):
        ex = self.assertRaises(sh.ShellCommandFailed,
                               self.execute,
                               command=command,
                               expect_exit_status=expect_exit_status,
                               stdin=stdin,
                               stdout=bool(stdout),
                               stderr=bool(stderr),
                               **kwargs)
        self.assertEqual(self.expected_command(command), ex.command)
        if stdin:
            self.assertEqual(stdin, ex.stdin)
        else:
            self.assertIsNone(ex.stdin)
        if stdout:
            self.assertEqual(stdout, ex.stdout)
        else:
            self.assertIsNone(ex.stdout)
        if stderr:
            self.assertEqual(stderr, ex.stderr)
        else:
            self.assertIsNone(ex.stderr)
        if exit_status is not None:
            self.assertEqual(exit_status, ex.exit_status)
        else:
            self.assertTrue(ex.exit_status)

    def test_fails_getting_exit_status(self):
        self.test_fails('exit 15', exit_status=15)

    def test_fails_reading_from_stdout(self):
        self.test_fails(command='echo something && false',
                        stdout='something\n')

    def test_fails_reading_from_stderr(self):
        self.test_fails(command='echo something >&2 && false',
                        stderr='something\n')

    def test_fails_writing_to_stdin(self):
        self.test_fails('cat && false',
                        stdin='some input\n',
                        stdout='some input\n')

    def test_fails_with_check_exit_status(self):
        self.test_fails(command='true', expect_exit_status=1, exit_status=0)

    def test_timeout_expires(self, command='sleep 10', timeout=5., stdin=None,
                             stdout=None, stderr=None, **kwargs):
        ex = self.assertRaises(sh.ShellTimeoutExpired,
                               self.execute,
                               command=command,
                               timeout=timeout,
                               stdin=stdin,
                               stdout=bool(stdout),
                               stderr=bool(stderr),
                               **kwargs)
        self.assertEqual(self.expected_command(command), ex.command)
        if stdin:
            self.assertTrue(stdin.startswith(ex.stdin))
        else:
            self.assertIsNone(ex.stdin)
        if stdout:
            self.assertTrue(stdout.startswith(ex.stdout))
        else:
            self.assertIsNone(ex.stdout)
        if stderr:
            self.assertTrue(stderr.startswith(ex.stderr))
        else:
            self.assertIsNone(ex.stderr)
        self.assertEqual(timeout, ex.timeout)

    def make_temporary(self,
                       directory=False,
                       add_cleanup=True) -> str:
        command = sh.shell_command('mktemp')
        if directory:
            command += '-d'
        temporary_path = self.execute(command=command).stdout.strip()
        if add_cleanup:
            self.addCleanup(sh.execute, f"rm -fR '{temporary_path}'")
        return temporary_path

    def execute(self, **kwargs):
        return sh.execute(**kwargs)

    def expected_command(self, command):
        command = sh.shell_command(command)
        if self.expected_shell is not None:
            command = sh.shell_command(self.expected_shell) + [str(command)]
        return str(command)


class LocalExecuteTest(ExecuteTest):

    expected_shell = LOCAL_EXPECTED_SHELL

    def execute(self, **kwargs):
        return sh.local_execute(**kwargs)


@keystone.skip_unless_has_keystone_credentials()
class SSHExecuteTest(ExecuteTest):

    expected_shell = SSH_EXPECTED_SHELL

    server_stack = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)

    @property
    def ssh_client(self):
        return self.server_stack.ssh_client

    def execute(self, **kwargs):
        return sh.ssh_execute(ssh_client=self.ssh_client, **kwargs)


@keystone.skip_unless_has_keystone_credentials()
class CirrosSSHExecuteTest(SSHExecuteTest):

    server_stack = tobiko.required_fixture(
        stacks.CirrosServerStackFixture)
