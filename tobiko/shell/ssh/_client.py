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

from collections import abc
import contextlib
import getpass
import os
import subprocess
import time
import threading
import typing

import netaddr
import testtools
from oslo_log import log
from oslo_utils.secretutils import md5
import paramiko
from paramiko import common

import tobiko
from tobiko.shell.ssh import _config
from tobiko.shell.ssh import _command


LOG = log.getLogger(__name__)


def get_fingerprint(self):
    """Patch paramiko

    This method needs to be patched to allow paramiko to work under FIPS.
    Until the patch to do this merges, patch paramiko here.

    TODO(eolivare) Remove this when paramiko is patched.
    See https://github.com/paramiko/paramiko/pull/1928
    """
    return md5(self.asbytes(), usedforsecurity=False).digest()


# mypy: disable-error-code="assignment"
paramiko.pkey.PKey.get_fingerprint = get_fingerprint


def valid_hostname(value):
    hostname = str(value)
    if not hostname:
        message = "Invalid hostname: {!r}".format(hostname)
        raise ValueError(message)
    return hostname


def valid_port(value):
    port = int(value)
    if port <= 0 or port > 65535:
        message = "Invalid port number: {!r}".format(port)
        raise ValueError(message)
    return port


def valid_path(value):
    return os.path.abspath(os.path.expanduser(value))


def positive_float(value):
    value = float(value)
    if value <= 0.:
        message = "{!r} is not positive".format(value)
        raise ValueError(message)
    return value


def positive_int(value):
    value = int(value)
    if value <= 0:
        message = "{!r} is not positive".format(value)
        raise ValueError(message)
    return value


def get_key_filename(value):
    if isinstance(value, str):
        value = [value]
    key_filename = [tobiko.tobiko_config_path(v) for v in value]
    return [f
            for f in key_filename
            if os.path.isfile(f)]


SSH_CONNECT_PARAMETERS = {
    #: The server to connect to
    'hostname': valid_hostname,

    #: The server port to connect to
    'port': valid_port,

    #: The username to authenticate as (defaults to the current local username)
    'username': str,

    #: Used for password authentication; is also used for private key
    #: decryption if passphrase is not given
    'password': str,

    #: Used for decrypting private keys
    'passphrase': str,

    #: The filename, or list of filenames, of optional private key(s) and/or
    #: certs to try for authentication
    'key_filename': get_key_filename,

    #: An optional timeout (in seconds) for the TCP connect
    'timeout': positive_float,

    #: Set to False to disable connecting to the SSH agent
    'allow_agent': bool,

    #: Set to False to disable searching for discoverable private key files in
    #: ~/.ssh/
    'look_for_keys': bool,

    #: Set to True to turn on compression
    'compress': bool,

    #: True if you want to use GSS-API authentication
    'gss_auth': bool,

    #: Perform GSS-API Key Exchange and user authentication
    'gss_kex': bool,

    #: Delegate GSS-API client credentials or not
    'gss_deleg_creds': bool,

    #: The targets name in the kerberos database. default: hostname
    'gss_host': str,

    #: Indicates whether or not the DNS is trusted to securely canonicalize the
    #: name of the host being connected to (default True).
    'gss_trust_dns': bool,

    #: An optional timeout (in seconds) to wait for the SSH banner to be
    #: presented.
    'banner_timeout': positive_float,

    #: An optional timeout (in seconds) to wait for an authentication response
    'auth_timeout': positive_float,

    #: Number of connection attempts to be tried before timeout
    'connection_attempts': positive_int,

    #: Minimum amount of time to wait between two connection attempts
    'connection_interval': positive_float,

    #: Amount of time before timing our connection attempt
    'connection_timeout': positive_float,

    #: Command to be executed to open proxy sock
    'proxy_command': str,

    #: Allow to disable some algorithms for old servers
    'disabled_algorithms': dict
}


def gather_ssh_connect_parameters(source=None, destination=None, schema=None,
                                  remove_from_schema=False, **kwargs):
    if schema is None:
        assert not remove_from_schema
        schema = SSH_CONNECT_PARAMETERS
    parameters = {}

    if source:
        # gather from object
        if isinstance(source, abc.Mapping):
            parameters.update(_items_from_mapping(mapping=source,
                                                  schema=schema))
        else:
            parameters.update(_items_from_object(obj=source,
                                                 schema=schema))

    if kwargs:
        # gather from kwargs
        parameters.update(_items_from_mapping(mapping=kwargs, schema=schema))
        kwargs = exclude_mapping_items(kwargs, schema)
        if kwargs:
            message = "Invalid SSH connection parameters: {!r}".format(kwargs)
            raise ValueError(message)

    if remove_from_schema and parameters:
        # update schema
        for name in parameters:
            del schema[name]

    if destination is not None:
        destination.update(parameters)
    return parameters


def _items_from_mapping(mapping, schema):
    for name, init in schema.items():
        value = mapping.get(name)
        if value is not None:
            yield name, init(value)


def _items_from_object(obj, schema):
    for name, init in schema.items():
        value = getattr(obj, name, None)
        if value is not None:
            yield name, init(value)


def exclude_mapping_items(mapping, exclude):
    """Exclude parameters that are already in target dictionary"""
    return {key: value
            for key, value in mapping.items()
            if key not in exclude}


class SSHConnectFailure(tobiko.TobikoException):
    message = "Failed to login to {login}\n{cause}"


class SSHClientFixture(tobiko.SharedFixture):

    host = None
    port = 22
    username = getpass.getuser()

    client = None

    default = tobiko.required_fixture(_config.SSHDefaultConfigFixture)
    config_files = None
    host_config = None
    global_host_config = None

    proxy_client = None
    proxy_sock = None
    connect_parameters = None
    schema = SSH_CONNECT_PARAMETERS

    def __init__(self, host=None, proxy_client=None, host_config=None,
                 config_files=None, schema=None, **kwargs):
        super(SSHClientFixture, self).__init__()
        if host:
            self.host = host
        if proxy_client:
            self.proxy_client = proxy_client
        if host_config:
            self.host_config = host_config
        if config_files:
            self.config_files = config_files

        self.schema = schema = dict(schema or self.schema)
        self._connect_parameters = gather_ssh_connect_parameters(
            schema=schema, **kwargs)
        self._forwarders = []

    def setup_fixture(self):
        self.setup_connect_parameters()
        self.setup_ssh_client()

    def setup_global_host_config(self):
        self.global_host_config = config = _config.ssh_host_config(
            host=self.host, config_files=self.config_files)
        return config

    def setup_connect_parameters(self):
        """Fill connect parameters dict

        Get parameters values from below sources:
        - parameters passed to class constructor
        - parameters got from ~/.ssh/config and tobiko.conf
        - parameters got from fixture object attributes
        """
        self.setup_global_host_config()
        self.connect_parameters = parameters = self.get_connect_parameters()
        return parameters

    def get_connect_parameters(self, schema=None):
        schema = dict(schema or self.schema)
        parameters = {}
        self.gather_initial_connect_parameters(
            destination=parameters, schema=schema, remove_from_schema=True)
        self.gather_global_host_config_connect_parameters(
            destination=parameters, schema=schema, remove_from_schema=True)
        self.gather_host_config_connect_parameters(
            destination=parameters, schema=schema, remove_from_schema=True)
        self.gather_default_connect_parameters(
            destination=parameters, schema=schema, remove_from_schema=True)
        return parameters

    def gather_initial_connect_parameters(self, **kwargs):
        if self._connect_parameters:
            gather_ssh_connect_parameters(
                source=self._connect_parameters, **kwargs)

    def gather_host_config_connect_parameters(self, **kwargs):
        if self.host_config:
            gather_ssh_connect_parameters(
                source=self.host_config.connect_parameters, **kwargs)

    def gather_global_host_config_connect_parameters(self, **kwargs):
        if self.global_host_config:
            gather_ssh_connect_parameters(
                source=self.global_host_config.connect_parameters, **kwargs)

    def gather_default_connect_parameters(self, **kwargs):
        return gather_ssh_connect_parameters(source=self, **kwargs)

    def setup_ssh_client(self):
        self.client, self.proxy_sock = ssh_connect(
            proxy_client=self.proxy_client,
            **self.connect_parameters)
        self.addCleanup(self.cleanup_ssh_client)
        if self.proxy_sock:
            self.addCleanup(self.cleanup_proxy_sock)
        for forwarder in self._forwarders:
            self.useFixture(forwarder)

    def cleanup_ssh_client(self):
        client = self.client
        self.client = None
        if client:
            LOG.debug(f"Closing SSH connection... ({self.details})")
            try:
                client.close()
            except Exception:
                LOG.exception("Error closing SSH connection. "
                              f"({self.details})")
            else:
                LOG.debug(f"SSH connection closed. ({self.details})")

    def cleanup_proxy_sock(self):
        proxy_sock = self.proxy_sock
        self.proxy_sock = None
        if proxy_sock:
            LOG.debug(f"Closing SSH proxy sock... ({self.details})")
            try:
                proxy_sock.close()
            except Exception:
                LOG.exception("Error closing proxy socket. "
                              f"({self.details})")
            else:
                LOG.debug(f"SSH proxy sock closed. ({self.details})")

    @contextlib.contextmanager
    def use_connect_parameters(self, **kwargs):
        if kwargs:
            restore_parameters = dict(self._connect_parameters)
            gather_ssh_connect_parameters(schema=self.schema,
                                          destination=self._connect_parameters,
                                          **kwargs)
            self.connect_parameters = self.get_connect_parameters()
        else:
            restore_parameters = None
        try:
            yield
        finally:
            if restore_parameters is not None:
                self._connect_parameters = restore_parameters
                self.connect_parameters = self.get_connect_parameters()

    def connect(self, retry_count: typing.Optional[int] = 2,
                retry_timeout: tobiko.Seconds = None,
                retry_interval: tobiko.Seconds = None,
                **ssh_parameters) -> paramiko.SSHClient:
        """Ensures it is connected to remote SSH server
        """
        with self.use_connect_parameters(**ssh_parameters):
            # This retry is mostly intended to ensure connection is
            # reestablished in case it is lost
            for attempt in tobiko.retry(count=retry_count,
                                        timeout=retry_timeout,
                                        interval=retry_interval):
                LOG.debug(f"Ensuring SSH connection (attempt={attempt})")
                connected = False
                try:
                    client = tobiko.setup_fixture(self).client
                    # For any reason at this point client could
                    # be None: force fixture cleanup
                    if check_ssh_connection(client):
                        LOG.debug("SSH connection is safe to use "
                                  f"(attempt={attempt})")
                        connected = True
                        break
                    else:
                        LOG.warning("SSH connection is not safe to use "
                                    f"(attempt={attempt})")
                except Exception:
                    attempt.check_limits()
                    LOG.exception(f"Failed connecting to '{self.login}' "
                                  f"(attempt={attempt})")
                finally:
                    if not connected:
                        self.close()
            else:
                raise RuntimeError("Broken retry loop")

        return client

    def close(self):
        """Ensures it is disconnected from remote SSH server
        """
        try:
            tobiko.cleanup_fixture(self)
        except Exception:
            LOG.exception(f"Failed closing SSH connection to '{self.login}'")

    def get_ssh_command(self, host=None, username=None, port=None,
                        command=None, config_files=None, host_config=None,
                        proxy_command=None, key_filename=None, **options):
        connect_parameters = self.setup_connect_parameters()
        host = host or connect_parameters.get('hostname')
        username = username or connect_parameters.get('username')
        port = port or connect_parameters.get('port')
        config_files = config_files or connect_parameters.get('config_files')
        if not host_config:
            _host_config = self.setup_global_host_config()
            if hasattr(_host_config, 'host_config'):
                _host_config = host_config
        key_filename = key_filename or connect_parameters.get('key_filename')
        proxy_command = (proxy_command or
                         connect_parameters.get('proxy_command'))
        if not proxy_command and self.proxy_client:
            proxy_command = self.proxy_client.get_ssh_command()

        return _command.ssh_command(host=host,
                                    username=username,
                                    port=port,
                                    command=command,
                                    config_files=config_files,
                                    host_config=host_config,
                                    proxy_command=proxy_command,
                                    key_filename=key_filename,
                                    **options)

    @property
    def login(self):
        parameters = self.setup_connect_parameters()
        return _command.ssh_login(hostname=parameters['hostname'],
                                  username=parameters['username'],
                                  port=parameters['port'])

    @property
    def hostname(self):
        parameters = self.setup_connect_parameters()
        return parameters['hostname']

    @property
    def details(self):
        return f"login='{self.login}'"

    def open_unix_socket(self,
                         socket_path: str,
                         window_size: int = common.DEFAULT_WINDOW_SIZE,
                         max_packet_size: int = common.DEFAULT_MAX_PACKET_SIZE,
                         timeout: tobiko.Seconds = None) \
            -> paramiko.Channel:
        # pylint: disable=protected-access
        transport: typing.Any = self.connect().get_transport()
        if transport is None or not transport.active:
            raise paramiko.SSHException("SSH session not active")
        timeout = 3600 if timeout is None else timeout
        transport.lock.acquire()
        try:
            window_size = transport._sanitize_window_size(window_size)
            max_packet_size = transport._sanitize_packet_size(max_packet_size)
            chanid = transport._next_channel()

            # Documented here:
            # https://github.com/openssh/openssh-portable/blob/master/PROTOCOL
            m = paramiko.Message()
            m.add_byte(b'Z')
            m.add_string('direct-streamlocal@openssh.com')
            m.add_int(chanid)
            m.add_int(window_size)
            m.add_int(max_packet_size)
            m.add_string(socket_path)
            # Reserved stuff
            m.add_string('')
            m.add_int(0)

            sock: typing.Any = paramiko.Channel(chanid)
            transport._channels.put(chanid, sock)
            transport.channel_events[chanid] = event = threading.Event()
            transport.channels_seen[chanid] = True
            sock._set_transport(transport)
            sock._set_window(window_size, max_packet_size)
        finally:
            transport.lock.release()

        transport._send_user_message(m)
        start_ts = tobiko.time()
        while True:
            event.wait(0.1)
            if not transport.active:
                e = transport.get_exception()
                if e is None:
                    e = paramiko.SSHException("Unable to open channel.")
                raise e
            if event.is_set():
                break
            elif start_ts + timeout < time.time():
                raise paramiko.SSHException("Timeout opening channel.")

        sock = transport._channels.get(chanid)
        if sock is None:
            e = transport.get_exception()
            if e is None:
                e = paramiko.SSHException("Unable to open channel.")
            raise e

        return sock

    def __repr__(self):
        return f"SSHClientFixture <{self.details}>"


UNDEFINED_CLIENT = 'UNDEFINED_CLIENT'


class SSHClientManager(object):

    default = tobiko.required_fixture(_config.SSHDefaultConfigFixture)

    def __init__(self):
        self.clients = {}

    def get_client(self, host, hostname=None, username=None, port=None,
                   proxy_jump=None, host_config=None, config_files=None,
                   proxy_client=None, **connect_parameters) -> \
            SSHClientFixture:
        if isinstance(host, netaddr.IPAddress):
            host = str(host)

        if host_config:
            hostname = hostname or host_config.hostname
            port = port or host_config.port
            username = username or host_config.username

        global_host_config = _config.ssh_host_config(host=host,
                                                     config_files=config_files)
        hostname = hostname or global_host_config.hostname
        port = port or global_host_config.port
        username = username or global_host_config.username

        host_key = hostname, port, username, proxy_jump
        existing_client = self.clients.get(host_key)
        if isinstance(existing_client, SSHClientFixture):
            return existing_client

        # Put a placeholder to avoid infinite recursive lookup
        if existing_client is UNDEFINED_CLIENT:
            raise RuntimeError('Recursive SSH proxy client definition')
        self.clients[host_key] = UNDEFINED_CLIENT

        proxy_client = proxy_client or self.get_proxy_client(
            host=host, proxy_jump=proxy_jump, config_files=config_files)
        self.clients[host_key] = new_client = SSHClientFixture(
            host=host, hostname=hostname, port=port, username=username,
            proxy_client=proxy_client, host_config=host_config,
            **connect_parameters)
        return new_client

    def get_proxy_client(self,
                         host=None,
                         proxy_jump=None,
                         host_config=None,
                         config_files=None):
        if isinstance(proxy_jump, SSHClientFixture):
            return proxy_jump
        host_config = host_config or _config.ssh_host_config(
            host=host, config_files=config_files)
        proxy_jump = host_config.proxy_jump
        return proxy_jump and self.get_client(proxy_jump) or None


CLIENTS = SSHClientManager()


def ssh_client(host, port=None, username=None, proxy_jump=None,
               host_config=None, config_files=None, manager=None,
               **connect_parameters) -> SSHClientFixture:
    manager = manager or CLIENTS
    return manager.get_client(host=host, port=port, username=username,
                              proxy_jump=proxy_jump, host_config=host_config,
                              config_files=config_files,
                              **connect_parameters)


KEY_CLASSES: typing.List[typing.Type[paramiko.PKey]] = [
    paramiko.RSAKey,
    paramiko.DSSKey,
    paramiko.ECDSAKey,
    paramiko.Ed25519Key,
]


def load_private_keys(key_filenames: typing.List[str],
                      password: str = None) \
        -> typing.List[paramiko.PKey]:
    pkeys: typing.List[paramiko.PKey] = []
    for filename in key_filenames:
        if os.path.exists(filename):
            try:
                pkey = load_private_key(filename, password=password)
            except LoadPrivateKeyError as ex:
                LOG.exception(f'Error loading key file: {ex}')
            else:
                pkeys.append(pkey)
        else:
            LOG.debug(f'Key file not found: {filename}')
    return pkeys


class LoadPrivateKeyError(tobiko.TobikoException):
    message = "Unable to load private key from file {filename}"


def load_private_key(filename: str,
                     password: str = None) -> paramiko.PKey:
    errors: typing.List[tobiko.ExceptionInfo] = []
    for key_class in KEY_CLASSES:
        try:
            pkey: paramiko.PKey = key_class.from_private_key_file(
                filename=filename, password=password)
        except (paramiko.SSHException, ValueError):
            errors.append(tobiko.exc_info())
        else:
            LOG.debug(f'Key file loaded: {filename} (key_class={key_class})')
            return pkey

    cause = testtools.MultipleExceptions(*errors)
    raise LoadPrivateKeyError(filename=filename) from cause


def ssh_connect(hostname, username=None, port=None, connection_interval=None,
                connection_attempts=None, connection_timeout=None,
                proxy_command=None, proxy_client=None, key_filename=None,
                password: str = None,
                **parameters):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    login = _command.ssh_login(hostname=hostname, username=username, port=port)

    assert isinstance(key_filename, list)
    pkeys = load_private_keys(key_filename, password=password)
    auth_failed: typing.Optional[Exception] = None
    for attempt in tobiko.retry(count=connection_attempts,
                                timeout=connection_timeout,
                                interval=connection_interval,
                                default_count=60,
                                default_timeout=300.,
                                default_interval=5.):
        LOG.debug(f"Logging in to '{login}'...\n"
                  f"  - parameters: {parameters}\n"
                  f"  - attempt: {attempt.details}\n")
        for pkey in pkeys + [None]:  # type: ignore
            succeeded = False
            proxy_sock = ssh_proxy_sock(
                hostname=hostname,
                port=port,
                command=proxy_command,
                client=proxy_client,
                timeout=connection_timeout,
                connection_attempts=1,
                connection_interval=connection_interval)
            try:
                client.connect(hostname=hostname,
                               username=username,
                               port=port,
                               sock=proxy_sock,
                               pkey=pkey,
                               **parameters)
            except paramiko.ssh_exception.AuthenticationException as ex:
                if auth_failed is not None:
                    ex.__cause__ = auth_failed
                auth_failed = ex
                continue
            except Exception as ex:
                LOG.debug(f"Error logging in to '{login}': {ex}", exc_info=1)
                attempt.check_limits()
                break
            else:
                LOG.debug(f"Successfully logged in to '{login}'")
                succeeded = True
                return client, proxy_sock
            finally:
                if not succeeded:
                    try:
                        proxy_sock.close()
                    except Exception:
                        pass
        else:
            if isinstance(auth_failed, Exception):
                raise auth_failed


def ssh_proxy_sock(hostname=None, port=None, command=None, client=None,
                   source_address=None, timeout=None,
                   connection_attempts=None, connection_interval=None):
    if not command:
        if client:
            # I need a command to execute with proxy client
            options = []
            if source_address:
                options += ['-s', str(source_address)]
            command = ['nc'] + options + ['{hostname!s}', '{port!s}']
        elif not command:
            # Proxy sock is not required
            return None

    # Apply connect parameters to proxy command
    if not isinstance(command, str):
        command = subprocess.list2cmdline(command)
    if hostname:
        command = command.format(hostname=hostname, port=(port or 22))
    if client:
        if isinstance(client, SSHClientFixture):
            # Connect to proxy server
            client = client.connect(connection_timeout=timeout,
                                    connection_attempts=connection_attempts,
                                    connection_interval=connection_interval)
        elif not isinstance(client, paramiko.SSHClient):
            message = "Object {!r} is not an SSHClient".format(client)
            raise TypeError(message)

        # Open proxy channel
        LOG.debug("Execute proxy command with proxy client %r: %r",
                  client, command)
        sock = client.get_transport().open_session(timeout=timeout)
        sock.exec_command(command)
    else:
        LOG.debug("Execute proxy command on local host: %r", command)
        sock = paramiko.ProxyCommand(command)

    return sock


def ssh_proxy_client(manager=None,
                     host=None,
                     host_config=None,
                     config_files=None):
    manager = manager or CLIENTS
    return manager.get_proxy_client(host=host,
                                    host_config=host_config,
                                    config_files=config_files)


def check_ssh_connection(client):
    if client:
        transport = client.get_transport()
        if transport.is_authenticated():
            # Send a keep-alive message
            transport.send_ignore()
            return True
    return False


SSHClientType = typing.Union[None, bool, SSHClientFixture]


def ssh_client_fixture(obj: SSHClientType) -> \
        typing.Optional[SSHClientFixture]:
    if obj is None:
        return ssh_proxy_client()
    if obj is False:
        return None
    if isinstance(obj, SSHClientFixture):
        return obj
    raise TypeError(f"Can't get an SSHClientFixture from objeck {obj}")
