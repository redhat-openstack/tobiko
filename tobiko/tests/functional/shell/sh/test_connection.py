# Copyright (c) 2022 Red Hat, Inc.
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

import getpass
import io
import os
import socket
import shutil
import tempfile
import typing
import uuid

import testtools

import tobiko
from tobiko.openstack import stacks
from tobiko.openstack import topology
from tobiko.shell import sh
from tobiko.shell import ssh


class LocalTempDirFixture(tobiko.SharedFixture):

    path: typing.Optional[str] = None

    def setup_fixture(self):
        self.path = self.create_dir()

    def cleanup_fixture(self):
        path = self.path
        if path is not None:
            try:
                self.delete_dir()
            finally:
                del self.path

    def create_dir(self) -> str:
        return tempfile.mkdtemp()

    def delete_dir(self):
        if os.path.isdir(self.path):
            shutil.rmtree(self.path)


class LocalShellConnectionTest(testtools.TestCase):

    @property
    def ssh_client(self) -> ssh.SSHClientType:
        return False

    @property
    def connection(self) -> sh.ShellConnection:
        return sh.shell_connection(self.ssh_client)

    connection_class = sh.LocalShellConnection

    def test_shell_connection(self):
        connection = sh.shell_connection(self.ssh_client)
        self.assertIsInstance(connection, self.connection_class)
        self.assertIs(self.connection, connection)

    @property
    def is_local(self) -> bool:
        return True

    def test_is_local(self):
        self.assertIs(self.is_local, self.connection.is_local)

    def test_is_local_connection(self):
        is_local = sh.is_local_connection(self.ssh_client)
        self.assertIs(self.is_local, is_local)

    @property
    def hostname(self) -> str:
        return socket.gethostname()

    def test_hostname(self):
        self.assertEqual(self.hostname, self.connection.hostname)

    def test_connection_hostname(self):
        hostname = sh.connection_hostname(self.ssh_client)
        self.assertEqual(self.hostname, hostname)

    @property
    def login(self) -> str:
        return f"{self.username}@{self.hostname}"

    def test_login(self):
        self.assertEqual(self.login, self.connection.login)

    def test_connection_login(self):
        login = sh.connection_login(self.ssh_client)
        self.assertEqual(self.login, login)

    @property
    def username(self) -> str:
        return getpass.getuser()

    def test_username(self):
        self.assertEqual(self.username, self.connection.username)

    def test_connection_username(self):
        username = sh.connection_username(self.ssh_client)
        self.assertEqual(self.username, username)

    @property
    def is_cirros(self) -> bool:
        return False

    def test_is_cirros(self):
        self.assertIs(self.is_cirros, self.connection.is_cirros)

    def test_is_cirros_connection(self):
        is_cirros = sh.is_cirros_connection(self.ssh_client)
        self.assertIs(self.is_cirros, is_cirros)

    @property
    def local_connection(self) -> sh.LocalShellConnection:
        return sh.local_shell_connection()

    def test_get_file(self):
        local_file = os.path.join(self.local_connection.make_temp_dir(),
                                  'local_file')
        remote_file = os.path.join(self.connection.make_temp_dir(),
                                   'remote_file')
        text = str(uuid.uuid4())
        sh.execute(f"echo '{text}' > '{remote_file}'",
                   ssh_client=self.ssh_client)
        self.assertFalse(os.path.isfile(local_file))
        sh.get_file(local_file=local_file,
                    remote_file=remote_file,
                    connection=self.ssh_client)
        self.assertTrue(os.path.isfile(local_file), 'file not copied')
        with io.open(local_file, 'rt') as fd:
            self.assertEqual(f'{text}\n', fd.read())

    def test_put_file(self):
        local_file = os.path.join(self.local_connection.make_temp_dir(),
                                  'local_file')
        remote_file = os.path.join(self.connection.make_temp_dir(),
                                   'remote_file')
        text = str(uuid.uuid4())
        with io.open(local_file, 'wt') as fd:
            fd.write(text)
        self.assertRaises(sh.ShellCommandFailed,
                          sh.execute, f"cat '{remote_file}'",
                          ssh_client=self.ssh_client)
        sh.put_file(remote_file=remote_file,
                    local_file=local_file,
                    connection=self.ssh_client)
        output = sh.execute(f"cat '{remote_file}'",
                            ssh_client=self.ssh_client).stdout
        self.assertEqual(text, output)

    def test_put_files(self):
        local_dir = self.local_connection.make_temp_dir()
        local_file = os.path.join(local_dir, 'some_file')
        remote_dir = self.connection.make_temp_dir()
        remote_file = os.path.join(remote_dir,
                                   os.path.basename(local_dir),
                                   'some_file')
        text = str(uuid.uuid4())
        with io.open(local_file, 'wt') as fd:
            fd.write(text)
        self.assertRaises(sh.ShellCommandFailed,
                          sh.execute, f"cat '{remote_file}'",
                          ssh_client=self.ssh_client)
        sh.put_files(local_dir,
                     remote_dir=remote_dir,
                     connection=self.ssh_client)
        output = sh.execute(f"cat '{remote_file}'",
                            ssh_client=self.ssh_client).stdout
        self.assertEqual(text, output)

    def test_open_file(self):
        temp_file = self.connection.make_temp_file()
        with self.connection.open_file(temp_file, 'wt') as fd:
            fd.write('something')
        with self.connection.open_file(temp_file, 'rt') as fd:
            self.assertIn(fd.read(), [b'something',
                                      'something'])

    def test_make_temp_file(self):
        temp_file = self.connection.make_temp_file()
        self.assertTrue(self.connection.exists(temp_file))
        self.assertTrue(self.connection.is_file(temp_file))
        self.assertFalse(self.connection.is_directory(temp_file))

    def test_make_temp_dir(self):
        temp_file = self.connection.make_temp_dir()
        self.assertTrue(self.connection.exists(temp_file))
        self.assertFalse(self.connection.is_file(temp_file))
        self.assertTrue(self.connection.is_directory(temp_file))


class SSHShellConnectionTest(LocalShellConnectionTest):
    connection_class = sh.SSHShellConnection
    server = tobiko.required_fixture(stacks.AdvancedServerStackFixture)

    @property
    def ssh_client(self) -> ssh.SSHClientFixture:
        ssh_client = ssh.ssh_proxy_client()
        if isinstance(ssh_client, ssh.SSHClientFixture):
            return ssh_client

        nodes = topology.list_openstack_nodes()
        for node in nodes:
            if isinstance(node.ssh_client, ssh.SSHClientFixture):
                return node.ssh_client

        return self.server.ssh_client

    @property
    def is_local(self) -> bool:
        return False

    @property
    def hostname(self) -> str:
        return sh.get_hostname(ssh_client=self.ssh_client)

    @property
    def username(self) -> str:
        return self.ssh_client.setup_connect_parameters()['username']


class CirrosShellConnectionTest(SSHShellConnectionTest):
    connection_class = stacks.CirrosShellConnection
    server = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    @property
    def ssh_client(self) -> ssh.SSHClientFixture:
        return self.server.ssh_client

    @property
    def is_cirros(self) -> bool:
        return True

    @tobiko.skip('not implemented')
    def test_open_file(self):
        pass
