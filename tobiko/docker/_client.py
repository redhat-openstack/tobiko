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
import typing

import docker
from docker.transport import unixconn
from docker import constants

import tobiko
from tobiko.docker import _exception
from tobiko.docker import _shell
from tobiko.shell import ssh


def get_docker_client(base_urls: typing.List[str] = None,
                      ssh_client: ssh.SSHClientType = None,
                      sudo=False):
    return DockerClientFixture(base_urls=base_urls,
                               ssh_client=ssh_client,
                               sudo=sudo)


def list_docker_containers(client=None, **kwargs):
    try:
        containers = docker_client(client).containers.list(all=True,
                                                           sparse=True,
                                                           **kwargs)
    except _exception.DockerUrlNotFoundError:
        return tobiko.Selection()
    else:
        return tobiko.select(containers)


def docker_client(obj=None):
    if obj is None:
        obj = get_docker_client()
    if tobiko.is_fixture(obj):
        obj = tobiko.setup_fixture(obj).client
    if isinstance(obj, docker.DockerClient):
        return obj
    raise TypeError('Cannot obtain a DockerClient from {!r}'.format(obj))


class DockerClientFixture(tobiko.SharedFixture):

    base_urls: typing.Optional[typing.List[str]] = None
    ssh_client = ssh.SSHClientType = None
    sudo = False
    client: typing.Optional['DockerClient'] = None

    def __init__(self,
                 base_urls: typing.Iterable[str] = None,
                 ssh_client: ssh.SSHClientType = None,
                 sudo: bool = None):
        super(DockerClientFixture, self).__init__()
        if base_urls:
            self.base_urls = list(base_urls)
        if ssh_client is not None:
            self.ssh_client = ssh_client
        if sudo is not None:
            self.sudo = sudo

    def setup_fixture(self):
        self.setup_ssh_client()
        self.setup_base_urls()
        self.setup_client()

    def setup_ssh_client(self):
        ssh_client = self.ssh_client
        if ssh_client is None:
            self.ssh_client = ssh_client = ssh.ssh_proxy_client() or False
            if ssh_client:
                tobiko.setup_fixture(ssh_client)
        return ssh_client

    def setup_base_urls(self):
        base_urls = self.base_urls
        if base_urls is None:
            self.base_urls = base_urls = self.discover_docker_urls()
        return base_urls

    def setup_client(self):
        client = self.client
        if client is None:
            self.client = client = self.create_client()
        return client

    def create_client(self):
        error: typing.Optional[Exception] = None
        for base_url in self.base_urls:
            client = DockerClient(base_url=base_url,
                                  ssh_client=self.ssh_client,
                                  sudo=self.sudo)
            try:
                client.ping()
            except Exception as ex:
                ex.__cause__ = error
                error = ex
            else:
                return client

        if isinstance(error, Exception):
            raise error
        else:
            raise _exception.DockerError('Unable to create docker client')

    def connect(self):
        return tobiko.setup_fixture(self).client

    def discover_docker_urls(self):
        return _shell.discover_docker_urls(ssh_client=self.ssh_client,
                                           sudo=self.sudo)


class DockerClient(docker.DockerClient):

    def __init__(self,
                 base_url: str,
                 ssh_client: ssh.SSHClientType = None,
                 sudo=False):
        # pylint: disable=super-init-not-called
        self.api = APIClient(base_url=base_url,
                             ssh_client=ssh_client,
                             sudo=sudo)


class APIClient(docker.APIClient):

    def __init__(self,
                 base_url: str,
                 ssh_client: ssh.SSHClientType = None,
                 sudo=False):
        self.ssh_client = ssh_client
        self.sudo = sudo
        super(APIClient, self).__init__(base_url=base_url)

    def get_adapter(self, url):
        adapter = super(APIClient, self).get_adapter(url)
        if isinstance(adapter, unixconn.UnixHTTPAdapter):
            new_adapter = UnixHTTPAdapter(
                socket_url=f"http+unix://{adapter.socket_path}",
                timeout=adapter.timeout,
                max_pool_size=adapter.max_pool_size,
                ssh_client=self.ssh_client,
                sudo=self.sudo)
            self._custom_adapter = new_adapter
            for prefix, other_adapter in self.adapters.items():
                if adapter is other_adapter:
                    self.adapters[prefix] = new_adapter
            return new_adapter
        else:
            return adapter


class UnixHTTPAdapter(unixconn.UnixHTTPAdapter):

    def __init__(self,
                 socket_url: str,
                 timeout=60,
                 pool_connections=constants.DEFAULT_NUM_POOLS,
                 max_pool_size=constants.DEFAULT_MAX_POOL_SIZE,
                 ssh_client: ssh.SSHClientType = None,
                 sudo=False):
        self.ssh_client = ssh_client
        self.sudo = sudo
        super().__init__(socket_url=socket_url,
                         timeout=timeout,
                         pool_connections=pool_connections,
                         max_pool_size=max_pool_size)

    def get_connection(self, url, proxies=None):
        with self.pools.lock:
            pool = self.pools.get(url)
            if pool:
                return pool

            pool = UnixHTTPConnectionPool(base_url=url,
                                          socket_path=self.socket_path,
                                          timeout=self.timeout,
                                          maxsize=self.max_pool_size,
                                          ssh_client=self.ssh_client,
                                          sudo=self.sudo)
            self.pools[url] = pool

        return pool


class UnixHTTPConnectionPool(unixconn.UnixHTTPConnectionPool):

    def __init__(self,
                 base_url: str,
                 socket_path: str,
                 timeout=60,
                 maxsize=10,
                 ssh_client: ssh.SSHClientType = None,
                 sudo=False):
        self.ssh_client = ssh_client
        self.sudo = sudo
        super().__init__(base_url=base_url, socket_path=socket_path,
                         timeout=timeout, maxsize=maxsize)

    def _new_conn(self):
        return UnixHTTPConnection(base_url=self.base_url,
                                  unix_socket=self.socket_path,
                                  timeout=self.timeout,
                                  ssh_client=self.ssh_client,
                                  sudo=self.sudo)


class UnixHTTPConnection(unixconn.UnixHTTPConnection):

    def __init__(self,
                 base_url: str,
                 unix_socket: str,
                 timeout=60,
                 ssh_client: ssh.SSHClientType = None,
                 sudo=False):
        self.ssh_client = ssh_client
        self.sudo = sudo
        self.sock = None
        super(UnixHTTPConnection, self).__init__(base_url=base_url,
                                                 unix_socket=unix_socket,
                                                 timeout=timeout)

    def connect(self):
        ssh_client = ssh.ssh_client_fixture(self.ssh_client)
        if ssh_client is None:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect(self.unix_socket)
        elif self.sudo:
            client = self.ssh_client.connect()
            sock = client.get_transport().open_session(timeout=self.timeout)
            command = f"sudo nc -U '{self.unix_socket}'"
            sock.exec_command(command)
        else:
            sock = self.ssh_client.open_unix_socket(
                socket_path=self.unix_socket)
        self.sock = sock
