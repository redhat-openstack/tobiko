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
import os.path
import shutil
import socket
import tempfile
import typing

import paramiko
from oslo_log import log

import tobiko
from tobiko.shell.sh import _command
from tobiko.shell.sh import _execute
from tobiko.shell.sh import _hostname
from tobiko.shell.sh import _mktemp
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


def connection_hostname(ssh_client: ssh.SSHClientType = None) -> str:
    return shell_connection(ssh_client=ssh_client).hostname


def connection_login(ssh_client: ssh.SSHClientType = None) -> str:
    return shell_connection(ssh_client=ssh_client).login


def connection_username(ssh_client: ssh.SSHClientType = None) -> str:
    return shell_connection(ssh_client=ssh_client).username


def is_local_connection(ssh_client: ssh.SSHClientType = None) -> bool:
    return shell_connection(ssh_client=ssh_client).is_local


def is_cirros_connection(ssh_client: ssh.SSHClientType = None) -> bool:
    return shell_connection(ssh_client=ssh_client).is_cirros


def get_file(remote_file: str,
             local_file: str,
             ssh_client: ssh.SSHClientType = None) -> bool:
    return shell_connection(
        ssh_client=ssh_client).get_file(remote_file=remote_file,
                                        local_file=local_file)


def put_file(local_file: str,
             remote_file: str,
             ssh_client: ssh.SSHClientType = None) -> bool:
    return shell_connection(
        ssh_client=ssh_client).put_file(local_file=local_file,
                                        remote_file=remote_file)


def make_temp_dir(ssh_client: ssh.SSHClientType = None,
                  auto_clean=True,
                  sudo: bool = None) -> str:
    return shell_connection(ssh_client=ssh_client).make_temp_dir(
        auto_clean=auto_clean, sudo=sudo)


def remove_files(filename: str, *filenames: str,
                 ssh_client: ssh.SSHClientType = None) -> str:
    return shell_connection(ssh_client=ssh_client).remove_files(
        filename, *filenames)


def make_dirs(name: str,
              exist_ok=True,
              ssh_client: ssh.SSHClientType = None) -> str:
    return shell_connection(ssh_client=ssh_client).make_dirs(
        name=name, exist_ok=exist_ok)


def local_shell_connection() -> 'LocalShellConnection':
    return tobiko.get_fixture(LocalShellConnection)


def shell_connection(ssh_client: ssh.SSHClientType = None,
                     manager: 'ShellConnectionManager' = None) -> \
        'ShellConnection':
    return shell_connection_manager(manager).get_shell_connection(
        ssh_client=ssh_client)


def register_shell_connection(connection: 'ShellConnection',
                              manager: 'ShellConnectionManager' = None) -> \
        None:
    tobiko.check_valid_type(connection, ShellConnection)
    shell_connection_manager(manager).register_shell_connection(connection)


def shell_connection_manager(manager: 'ShellConnectionManager' = None):
    if manager is None:
        return tobiko.setup_fixture(ShellConnectionManager)
    else:
        tobiko.check_valid_type(manager, ShellConnectionManager)
        return manager


ShellConnectionKey = typing.Optional[ssh.SSHClientFixture]


class ShellConnectionManager(tobiko.SharedFixture):

    def __init__(self):
        super(ShellConnectionManager, self).__init__()
        self._host_connections: typing.Dict['ShellConnectionKey',
                                            'ShellConnection'] = {}

    def get_shell_connection(self,
                             ssh_client: ssh.SSHClientType) -> \
            'ShellConnection':
        ssh_client = ssh.ssh_client_fixture(ssh_client)
        connection = self._host_connections.get(ssh_client)
        if connection is None:
            connection = self._setup_shell_connection(ssh_client=ssh_client)
            self._host_connections[ssh_client] = connection
        return connection

    def register_shell_connection(self, connection: 'ShellConnection'):
        ssh_client = ssh.ssh_client_fixture(connection.ssh_client)
        self._host_connections[ssh_client] = connection

    @staticmethod
    def _setup_shell_connection(ssh_client: ssh.SSHClientFixture = None) \
            -> 'ShellConnection':
        if ssh_client is None:
            return local_shell_connection()
        else:
            return tobiko.setup_fixture(SSHShellConnection(
                ssh_client=ssh_client))


class ShellConnection(tobiko.SharedFixture):

    def connect(self) -> 'ShellConnection':
        return tobiko.setup_fixture(self)

    def close(self) -> 'ShellConnection':
        return tobiko.cleanup_fixture(self)

    def reconnect(self):
        return tobiko.reset_fixture(self)

    @property
    def hostname(self) -> str:
        raise NotImplementedError

    @property
    def ssh_client(self) -> ssh.SSHClientType:
        raise NotImplementedError

    @property
    def is_local(self) -> bool:
        raise NotImplementedError

    @property
    def is_cirros(self) -> bool:
        return False

    @property
    def username(self) -> str:
        raise NotImplementedError

    @property
    def login(self) -> str:
        return f"{self.username}@{self.hostname}"

    def execute(self,
                command: _command.ShellCommandType,
                *args, **execute_params) -> \
            _execute.ShellExecuteResult:
        execute_params.setdefault('ssh_client', self.ssh_client)
        return _execute.execute(command, *args, **execute_params)

    def put_file(self, local_file: str, remote_file: str):
        raise NotImplementedError

    def get_file(self, remote_file: str, local_file: str):
        raise NotImplementedError

    def __str__(self) -> str:
        return f"{type(self).__name__}<{self.login}>"

    def make_temp_dir(self, auto_clean=True, sudo: bool = None) -> str:
        raise NotImplementedError

    def remove_files(self, filename: str, *filenames: str):
        raise NotImplementedError

    def make_dirs(self, name: str, exist_ok=True):
        raise NotImplementedError


class LocalShellConnection(ShellConnection):

    @property
    def ssh_client(self) -> bool:
        return False

    @property
    def is_local(self) -> bool:
        return True

    @property
    def username(self) -> str:
        return getpass.getuser()

    @property
    def hostname(self) -> str:
        return socket.gethostname()

    def put_file(self, local_file: str, remote_file: str):
        LOG.debug(f"Copy local file as {self.login}: '{local_file}' -> "
                  f"'{remote_file}' ...")
        shutil.copyfile(local_file, remote_file)

    def get_file(self, remote_file: str, local_file: str):
        LOG.debug(f"Copy local file as {self.login}: '{remote_file}' -> "
                  f"'{local_file}' ...")
        shutil.copyfile(remote_file, local_file)

    def make_temp_dir(self, auto_clean=True, sudo: bool = None) -> str:
        if sudo:
            return _mktemp.make_temp_dir(ssh_client=self.ssh_client,
                                         sudo=True)
        else:
            temp_dir = tempfile.mkdtemp()
            LOG.debug(f"Local temporary directory created as {self.login}: "
                      f"{temp_dir}")
            if auto_clean:
                tobiko.add_cleanup(self.remove_files, temp_dir)
            return temp_dir

    def remove_files(self, filename: str, *filenames: str):
        filenames = (filename,) + filenames
        LOG.debug(f"Remove local files as {self.login}: {filenames}")
        for filename in filenames:
            if os.path.exists(filename):
                shutil.rmtree(filename)

    def make_dirs(self, name: str, exist_ok=True):
        os.makedirs(name=name,
                    exist_ok=exist_ok)


class SSHShellConnection(ShellConnection):

    def __init__(self,
                 ssh_client: ssh.SSHClientFixture = None):
        super().__init__()
        self._ssh_client = ssh_client

    def setup_fixture(self):
        self._ssh_client.connect()

    def cleanup_fixture(self):
        self._ssh_client.close()

    @property
    def ssh_client(self) -> ssh.SSHClientFixture:
        if self._ssh_client is None:
            raise ValueError('Unspecified SSH client')
        return self._ssh_client

    @property
    def is_local(self) -> bool:
        return False

    @property
    def username(self) -> str:
        return self.ssh_client.username

    _hostname: typing.Optional[str] = None

    @property
    def hostname(self) -> str:
        if self._hostname is None:
            self._hostname = _hostname.ssh_hostname(ssh_client=self.ssh_client)
        return self._hostname

    _sftp: typing.Optional[paramiko.SFTPClient] = None

    @property
    def sftp_client(self) -> paramiko.SFTPClient:
        if self._sftp is None:
            self._sftp = self.ssh_client.connect().open_sftp()
        return self._sftp

    def put_file(self, local_file: str, remote_file: str):
        LOG.debug(f"Put remote file as {self.login}: '{local_file}' -> "
                  f"'{remote_file}'...")
        self.sftp_client.put(local_file, remote_file)

    def get_file(self, remote_file: str, local_file: str):
        LOG.debug(f"Get remote file as {self.login}: '{remote_file}' -> "
                  f"'{local_file}'...")
        self.sftp_client.get(remote_file, local_file)

    def make_temp_dir(self, auto_clean=True, sudo: bool = None) -> str:
        temp_dir = self.execute('mktemp -d', sudo=sudo).stdout.strip()
        LOG.debug(f"Remote temporary directory created as {self.login}: "
                  f"{temp_dir}")
        if auto_clean:
            tobiko.add_cleanup(self.remove_files, temp_dir)
        return temp_dir

    def remove_files(self, filename: str, *filenames: str):
        filenames = (filename,) + filenames
        LOG.debug(f"Remove remote files as {self.login}: {filenames}")
        command = _command.shell_command('rm -fR') + filenames
        self.execute(command)

    def make_dirs(self, name: str, exist_ok=True):
        command = _command.shell_command('mkdir')
        if exist_ok:
            command += '-p'
        command += name
        self.execute(command)