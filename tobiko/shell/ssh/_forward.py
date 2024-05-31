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

import collections
import contextlib
import socket
import urllib

from oslo_log import log
import sshtunnel

import tobiko
from tobiko.shell.ssh import _client


LOG = log.getLogger(__name__)


def get_forward_port_address(address, ssh_client=None, manager=None):
    if ssh_client is None:
        ssh_client = _client.ssh_proxy_client()
    manager = manager or DEFAULT_SSH_PORT_FORWARD_MANAGER
    return manager.get_forward_port_address(address, ssh_client=ssh_client)


def get_forward_url(url, ssh_client=None, manager=None):
    url = parse_url(url)
    if ssh_client is None:
        ssh_client = _client.ssh_proxy_client()
    manager = manager or DEFAULT_SSH_PORT_FORWARD_MANAGER
    address = binding_address(url)
    forward_address = get_forward_port_address(address, ssh_client=ssh_client,
                                               manager=manager)
    return binding_url(forward_address)


def reset_default_ssh_port_forward_manager():
    # pylint: disable=global-statement
    global DEFAULT_SSH_PORT_FORWARD_MANAGER
    DEFAULT_SSH_PORT_FORWARD_MANAGER = SSHPortForwardManager()


class SSHPortForwardManager(object):

    def __init__(self):
        self.forward_addresses = {}
        self.forwarders = {}

    def get_forward_port_address(self, address, ssh_client):
        try:
            return self.forward_addresses[address, ssh_client]
        except KeyError:
            pass

        forwarder = self.get_forwarder(address, ssh_client=ssh_client)
        if forwarder:
            forward_address = forwarder.get_forwarding(address)
        else:
            forward_address = address

        self.forward_addresses[address, ssh_client] = forward_address
        return forward_address

    def get_forwarder(self, address, ssh_client):
        try:
            return self.forwarders[address, ssh_client]
        except KeyError:
            pass

        if ssh_client:
            tobiko.check_valid_type(ssh_client, _client.SSHClientFixture)
            forwarder = SSHTunnelForwarderFixture(ssh_client=ssh_client)
            forwarder.put_forwarding(address)
            tobiko.setup_fixture(forwarder)
        else:
            forwarder = None

        self.forwarders[address, ssh_client] = forwarder
        return forwarder


DEFAULT_SSH_PORT_FORWARD_MANAGER = SSHPortForwardManager()


class SSHTunnelForwarderFixture(tobiko.SharedFixture):

    forwarder = None

    def __init__(self, ssh_client):
        super(SSHTunnelForwarderFixture, self).__init__()
        self.ssh_client = ssh_client
        self._forwarding = collections.OrderedDict()

    def put_forwarding(self, remote, local=None):
        if not local:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with contextlib.closing(sock):
                sock.bind(('127.0.0.1', 0))
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                hostname, port = sock.getsockname()
                local = hostname, port
        return self._forwarding.setdefault(remote, local)

    def get_forwarding(self, remote):
        return self._forwarding.get(remote)

    def setup_fixture(self):
        self.setup_forwarder()

    def setup_forwarder(self):
        forwarder = self.forwarder
        if not forwarder:
            remote_bind_addresses = list(self._forwarding.keys())
            local_bind_addresses = list(self._forwarding.values())
            self.forwarder = forwarder = SSHTunnelForwarder(
                ssh_client=self.ssh_client,
                local_bind_addresses=local_bind_addresses,
                remote_bind_addresses=remote_bind_addresses)
            self.addCleanup(self.cleanup_forwarder)
            forwarder.start()
            self.ssh_client.addCleanup(self.cleanup_forwarder)
        return forwarder

    def cleanup_forwarder(self):
        forwarder = self.forwarder
        if forwarder:
            del self.forwarder
            forwarder.stop()


# pylint: disable=protected-access
class SSHUnixForwardHandler(sshtunnel._ForwardHandler):

    transport = None

    def handle(self):
        uid = sshtunnel.get_connection_id()
        self.info = '#{0} <-- {1}'.format(uid, self.client_address or
                                          self.server.local_address)

        remote_address = self.remote_address
        assert isinstance(remote_address, str)
        command = 'sudo nc -U "{}"'.format(remote_address)

        # reusing the same timeout value that is used by the parent class
        chan = self.transport.open_session(timeout=sshtunnel.TUNNEL_TIMEOUT)
        chan.exec_command(command)

        self.logger.log(sshtunnel.TRACE_LEVEL,
                        '{0} connected'.format(self.info))
        try:
            self._redirect(chan)
        except socket.error:
            # Sometimes a RST is sent and a socket error is raised, treat this
            # exception. It was seen that a 3way FIN is processed later on, so
            # no need to make an ordered close of the connection here or raise
            # the exception beyond this point...
            self.logger.log(sshtunnel.TRACE_LEVEL,
                            '{0} sending RST'.format(self.info))
        except Exception as e:
            self.logger.log(sshtunnel.TRACE_LEVEL,
                            '{0} error: {1}'.format(self.info, repr(e)))
        finally:
            chan.close()
            self.request.close()
            self.logger.log(sshtunnel.TRACE_LEVEL,
                            '{0} connection closed.'.format(self.info))

# pylint: enable=protected-access


class SSHTunnelForwarder(sshtunnel.SSHTunnelForwarder):

    daemon_forward_servers = True  #: flag tunnel threads in daemon mode
    daemon_transport = True  #: flag SSH transport thread in daemon mode

    def __init__(self, ssh_client, **kwargs):
        self.ssh_client = ssh_client
        params = self._merge_parameters(self._get_connect_parameters(),
                                        **kwargs)
        super(SSHTunnelForwarder, self).__init__(**params)

    def _merge_parameters(self, *dicts, **kwargs):
        result = {}
        for d in dicts + (kwargs,):
            if d:
                result.update((k, v) for k, v in d.items() if v is not None)
        return result

    @staticmethod
    def _consolidate_auth(ssh_password=None,
                          ssh_pkey=None,
                          ssh_pkey_password=None,
                          allow_agent=True,
                          host_pkey_directories=None,
                          logger=None):
        return None, None

    def _get_connect_parameters(self):
        parameters = self.ssh_client.setup_connect_parameters()
        return dict(ssh_address_or_host=parameters['hostname'],
                    ssh_username=parameters.get('username'),
                    ssh_password=parameters.get('password'),
                    ssh_pkey=parameters.get('pkey'),
                    ssh_port=parameters.get('port'),
                    ssh_private_key_password=parameters.get('passphrase'),
                    compression=parameters.get('compress'),
                    allow_agent=parameters.get('allow_agent'))

    def _connect_to_gateway(self):
        # pylint: disable=attribute-defined-outside-init
        self._transport = self._get_transport()

    def _get_transport(self):
        return self.ssh_client.connect().get_transport()

    def _stop_transport(self, force=True):
        if self.is_active:
            del self._transport
            assert not self.is_active
        super(SSHTunnelForwarder, self)._stop_transport(force=force)

    @staticmethod
    def _get_binds(bind_address, bind_addresses, is_remote=False):
        addr_kind = 'remote' if is_remote else 'local'

        if not bind_address and not bind_addresses:
            if is_remote:
                raise ValueError("No {0} bind addresses specified. Use "
                                 "'{0}_bind_address' or '{0}_bind_addresses'"
                                 " argument".format(addr_kind))
            else:
                return []
        elif bind_address and bind_addresses:
            raise ValueError("You can't use both '{0}_bind_address' and "
                             "'{0}_bind_addresses' arguments. Use one of "
                             "them.".format(addr_kind))
        if bind_address:
            bind_addresses = [bind_address]
        if not is_remote:
            # Add random port if missing in local bind
            for (i, local_bind) in enumerate(bind_addresses):
                if isinstance(local_bind, tuple) and len(local_bind) == 1:
                    bind_addresses[i] = (local_bind[0], 0)
        # check_addresses(bind_addresses, is_remote)
        return bind_addresses

    def _make_ssh_forward_handler_class(self, remote_address_):
        """
        Make SSH Handler class
        """
        if isinstance(remote_address_, tuple):
            return super(
                SSHTunnelForwarder, self)._make_ssh_forward_handler_class(
                    remote_address_)

        class Handler(SSHUnixForwardHandler):
            transport = self._transport
            remote_address = remote_address_
            logger = self.logger
        return Handler


def parse_url(url):
    if isinstance(url, urllib.parse.ParseResult):
        return url
    else:
        return urllib.parse.urlparse(url)


def binding_address(url):
    url = parse_url(url)
    if url.netloc:
        # Retains only scheme and netloc
        return (url.hostname, url.port)
    elif url.path:
        # Retains only scheme and path
        return url.path

    raise ValueError('Invalid URL: {!r}'.format(url))


def binding_url(address):
    if isinstance(address, tuple):
        try:
            hostname, port = address
        except ValueError:
            hostname, port = address
        return 'tcp://{hostname}:{port}'.format(hostname=hostname,
                                                port=port)

    elif isinstance(address, str):
        return 'unix://{path}'.format(path=address)

    raise TypeError('Invalid address type: {!r}'.format(address))
