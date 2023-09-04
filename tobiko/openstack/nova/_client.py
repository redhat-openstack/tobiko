# Copyright 2019 Red Hat
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

import contextlib
import typing

import novaclient
import novaclient.exceptions
import novaclient.v2.client
import novaclient.v2.servers
import novaclient.v2.hypervisors
from oslo_log import log

import tobiko
from tobiko.openstack import _client


LOG = log.getLogger(__name__)

CLIENT_CLASSES = (novaclient.v2.client.Client,)
NovaClient = typing.Union[novaclient.v2.client.Client]
NovaServer = typing.Union[novaclient.v2.servers.Server]
NovaHypervisor = typing.Union[novaclient.v2.hypervisors.Hypervisor]


class NovaClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session) -> NovaClient:
        return novaclient.client.Client('2.56', session=session)


class NovaClientManager(_client.OpenstackClientManager):

    def create_client(self, session) -> NovaClientFixture:
        return NovaClientFixture(session=session)


CLIENTS = NovaClientManager()

NovaClientType = typing.Union[NovaClient,
                              NovaClientFixture,
                              typing.Type[NovaClientFixture],
                              None]


def nova_client(obj: NovaClientType) -> NovaClient:
    if obj is None:
        return get_nova_client()

    if isinstance(obj, CLIENT_CLASSES):
        return obj

    fixture = tobiko.setup_fixture(obj)
    if isinstance(fixture, NovaClientFixture):
        assert fixture.client is not None
        return fixture.client

    message = f"Object '{obj}' is not a NovaClientFixture"
    raise TypeError(message)


def get_nova_client(session=None, shared=True, init_client=None,
                    manager=None) -> NovaClient:
    manager = manager or CLIENTS
    client = manager.get_client(session=session, shared=shared,
                                init_client=init_client)
    tobiko.setup_fixture(client)
    return client.client


def list_hypervisors(client: NovaClientType = None, detailed=True, **params) \
        -> tobiko.Selection[NovaHypervisor]:
    client = nova_client(client)
    hypervisors = client.hypervisors.list(detailed=detailed)
    return tobiko.select(hypervisors).with_attributes(**params)


def find_hypervisor(client: NovaClientType = None, unique=False, **params) \
        -> NovaHypervisor:
    hypervisors = list_hypervisors(client=client, **params)
    if unique:
        return hypervisors.unique
    else:
        return hypervisors.first


def list_servers(client: NovaClientType = None, **params) -> \
        tobiko.Selection[NovaServer]:
    servers = nova_client(client).servers.list()
    return tobiko.select(servers).with_attributes(**params)


def find_server(client: NovaClientType = None, unique=False, **params) -> \
        NovaServer:
    servers = list_servers(client=client, **params)
    if unique:
        return servers.unique
    else:
        return servers.first


def list_services(client: NovaClientType = None, **params) -> tobiko.Selection:
    client = nova_client(client)
    services = client.services.list()
    return tobiko.select(services).with_attributes(**params)


def find_service(client: NovaClientType = None, unique=False, **params):
    services = list_services(client=client, **params)
    if unique:
        return services.unique
    else:
        return services.first


ServerType = typing.Union[str, NovaServer]


def get_server_id(server: ServerType = None,
                  server_id: str = None) -> str:
    if server_id is None:
        if isinstance(server, str):
            server_id = server
        else:
            assert server is not None
            server_id = server.id
    return server_id


class GetServerError(tobiko.TobikoException):
    message = ("Error getting server '{server_id}' details "
               "(params={params}):\n"
               "{reason}")


class ServerNotFoundError(GetServerError, tobiko.ObjectNotFound):
    pass


def get_server(server: ServerType = None,
               server_id: str = None,
               client: NovaClientType = None,
               **params) -> NovaServer:
    server_id = get_server_id(server=server, server_id=server_id)
    try:
        return nova_client(client).servers.get(server_id, **params)
    except novaclient.exceptions.NotFound as ex:
        raise ServerNotFoundError(server_id=server_id,
                                  params=params,
                                  reason=str(ex)) from ex


def delete_server(server: ServerType = None,
                  server_id: str = None,
                  client: NovaClientType = None,
                  **params):
    server_id = get_server_id(server=server, server_id=server_id)
    try:
        return nova_client(client).servers.delete(server_id, **params)
    except novaclient.exceptions.NotFound as ex:
        raise ServerNotFoundError(server_id=server_id,
                                  params=params,
                                  reason=str(ex)) from ex


def migrate_server(server: ServerType = None,
                   server_id: str = None,
                   host: str = None,
                   client: NovaClientType = None,
                   **params):
    server_id = get_server_id(server=server, server_id=server_id)
    if host is not None:
        params.update(host=host)
    LOG.debug(f"Start server '{server_id}' migration...\n" +
              f"{params}")
    with handle_migration_errors(server_id=server_id, **params):
        # pylint: disable=protected-access
        return nova_client(client).servers._action(
            'migrate', server_id, info=params)


def live_migrate_server(server: ServerType = None,
                        server_id: str = None,
                        host: str = None,
                        block_migration: bool = None,
                        client: NovaClientType = None,
                        **params):
    server_id = get_server_id(server=server, server_id=server_id)
    params.update(host=host)
    if block_migration is None:
        params.update(block_migration='auto')
    else:
        params.update(block_migration=block_migration)

    LOG.debug(f"Start server '{server_id}' live migration...\n" +
              f"{params}")
    with handle_migration_errors(server_id=server_id, **params):
        return nova_client(client).servers.live_migrate(server=server_id,
                                                        **params)


@contextlib.contextmanager
def handle_migration_errors(server_id: str, **params):
    try:
        yield
    except novaclient.exceptions.BadRequest as ex:
        reason = str(ex)
        error_class = MigrateServerError
        if 'No valid host was found' in reason:
            error_class = NoValidHostFoundMigrateServerError
        if 'Migration pre-check error' in reason:
            error_class = PreCheckMigrateServerError
        if 'is not on shared storage' in reason:
            error_class = NotInSharedStorageMigrateServerError
        if 'is not on local storage' in reason:
            error_class = NotInLocalStorageMigrateServerError
        raise error_class(server_id=server_id,
                          reason=reason,
                          params=params) from ex


class MigrateServerError(tobiko.TobikoException):
    message = ("Error migrating server '{server_id}' "
               "(params={params}):\n"
               "{reason}")


class NoValidHostFoundMigrateServerError(MigrateServerError):
    pass


class PreCheckMigrateServerError(MigrateServerError):
    pass


class NotInLocalStorageMigrateServerError(MigrateServerError):
    pass


class NotInSharedStorageMigrateServerError(MigrateServerError):
    pass


def confirm_resize(server: typing.Optional[ServerType] = None,
                   server_id: typing.Optional[str] = None,
                   client: NovaClientType = None, **params):
    server_id = get_server_id(server=server, server_id=server_id)
    LOG.debug(f"Confirm server resize (server_id='{server_id}', "
              f"info={params})")
    return nova_client(client).servers.confirm_resize(server_id, **params)


MAX_SERVER_CONSOLE_OUTPUT_LENGTH = 1024 * 256


def get_console_output(server: typing.Optional[ServerType] = None,
                       server_id: typing.Optional[str] = None,
                       timeout: tobiko.Seconds = None,
                       interval: tobiko.Seconds = None,
                       length: typing.Optional[int] = None,
                       client: NovaClientType = None) -> \
        typing.Optional[str]:
    if length is not None:
        length = min(length, MAX_SERVER_CONSOLE_OUTPUT_LENGTH)
    else:
        length = MAX_SERVER_CONSOLE_OUTPUT_LENGTH

    server_id = get_server_id(server=server, server_id=server_id)

    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval,
                                default_timeout=60.,
                                default_interval=5.):
        try:
            output = nova_client(client).servers.get_console_output(
                server=server_id, length=length)
        except (TypeError, novaclient.exceptions.NotFound):
            # Only active servers have console output
            server = get_server(server_id=server_id)
            if server.status != 'ACTIVE':
                LOG.debug(f"Server '{server_id}' has no console output "
                          f"(status = '{server.status}').")
                break
            else:
                # For some reason it could happen resulting body cannot be
                # translated to json object and it is converted to None
                LOG.exception(f"Error getting server '{server_id}' console "
                              "output")
        else:
            if output:
                LOG.debug(f"got server '{server_id}' console output "
                          f"(length = {len(output)}).")
                return output

        if attempt.is_last:
            LOG.info(f"No console output produced by server '{server_id}') "
                     f" after {attempt.elapsed_time} seconds")
            break

        LOG.debug(f"Waiting for server '{server_id}' console output...")

    return None


def wait_for_guest_os_ready(server: typing.Optional[ServerType] = None,
                            server_id: typing.Optional[str] = None,
                            timeout: tobiko.Seconds = 120.,
                            interval: tobiko.Seconds = 5.,
                            client: NovaClientType = None) -> None:

    def system_booted():
        console_output = get_console_output(
            server=server, server_id=server_id, client=client) or ''
        for line in console_output.splitlines():
            if 'login:' in line.lower():
                return True
        return False

    for _ in tobiko.retry(timeout=timeout, interval=interval):
        if system_booted():
            LOG.debug('VM boot completed successfully')
            return
        else:
            LOG.debug('VM boot not completed yet')


class HasNovaClientMixin(object):

    nova_client: NovaClientType = None

    def get_server(self, server: ServerType, **params) -> NovaServer:
        return get_server(server=server, client=self.nova_client, **params)

    def get_server_console_output(self, server: ServerType, **params) -> \
            typing.Optional[str]:
        return get_console_output(server=server, client=self.nova_client,
                                  **params)


class WaitForServerStatusError(tobiko.TobikoException):
    message = ("Server {server_id} not changing status from {server_status} "
               "to {status}")


class WaitForServerStatusTimeout(WaitForServerStatusError):
    message = ("Server {server_id} didn't change its status from "
               "{server_status} to {status} status after {timeout} seconds")


NOVA_SERVER_TRANSIENT_STATUS: typing.Dict[str, typing.Set[str]] = {
    'ACTIVE': {'BUILD', 'SHUTOFF', 'REBOOT'},
    'SHUTOFF': {'ACTIVE'},
    'VERIFY_RESIZE': {'RESIZE'},
}


def wait_for_server_status(
        server: ServerType,
        status: str,
        client: NovaClientType = None,
        timeout: tobiko.Seconds = None,
        sleep_time: tobiko.Seconds = None,
        transient_status: typing.Optional[typing.Container[str]] = None) -> \
            NovaServer:
    if transient_status is None:
        transient_status = NOVA_SERVER_TRANSIENT_STATUS.get(status) or []
    server_id = get_server_id(server)
    for attempt in tobiko.retry(timeout=timeout,
                                interval=sleep_time,
                                default_timeout=300.,
                                default_interval=5.):
        _server = get_server(server_id=server_id, client=client)
        if _server.status == status:
            break

        if _server.status not in transient_status:
            raise WaitForServerStatusError(server_id=server_id,
                                           server_status=_server.status,
                                           status=status)
        try:
            attempt.check_time_left()
        except tobiko.RetryTimeLimitError as ex:
            raise WaitForServerStatusTimeout(server_id=server_id,
                                             server_status=_server.status,
                                             status=status,
                                             timeout=timeout) from ex

        progress = getattr(server, 'progress', None)
        LOG.debug(f"Waiting for server {server_id} status to get from "
                  f"{_server.status} to {status} "
                  f"(progress={progress}%)")
    else:
        raise RuntimeError("Broken retry loop")

    return _server


def shutoff_server(server: ServerType = None,
                   client: NovaClientType = None,
                   timeout: tobiko.Seconds = None,
                   sleep_time: tobiko.Seconds = None) -> NovaServer:
    client = nova_client(client)
    server = get_server(server=server, client=client)
    if server.status == 'SHUTOFF':
        return server

    LOG.info(f"stop server '{server.id}' (status='{server.status}').")
    client.servers.stop(server.id)
    return wait_for_server_status(server=server.id,
                                  status='SHUTOFF',
                                  client=client,
                                  timeout=timeout,
                                  sleep_time=sleep_time)


def activate_server(server: ServerType,
                    client: NovaClientType = None,
                    timeout: tobiko.Seconds = None,
                    sleep_time: tobiko.Seconds = None) -> NovaServer:
    client = nova_client(client)
    server = get_server(server=server, client=client)
    if server.status == 'ACTIVE':
        return server

    if server.status == 'SHUTOFF':
        LOG.info(f"Start server '{server.id}' (status='{server.status}').")
        client.servers.start(server.id)
    elif server.status == 'RESIZE':
        server = wait_for_server_status(
            server=server.id, status='VERIFY_RESIZE', client=client,
            timeout=timeout, sleep_time=sleep_time)
        LOG.info(f"Confirm resize of server '{server.id}' "
                 f"(status='{server.status}').")
        client.servers.confirm_resize(server)
    elif server.status == 'VERIFY_RESIZE':
        LOG.info(f"Confirm resize of server '{server.id}' "
                 f"(status='{server.status}').")
        client.servers.confirm_resize(server)
    elif server.status != 'REBOOT':
        LOG.warning(f"Try activating server '{server.id}' by rebooting "
                    f"it  (status='{server.status}').")
        client.servers.reboot(server.id, reboot_type='HARD')

    return wait_for_server_status(server=server.id, status='ACTIVE',
                                  client=client,
                                  timeout=timeout,
                                  sleep_time=sleep_time)


def reboot_server(server: ServerType,
                  client: NovaClientType = None,
                  timeout: tobiko.Seconds = None,
                  sleep_time: tobiko.Seconds = None) -> NovaServer:
    client = nova_client(client)
    server = get_server(server=server, client=client)
    if server.status == 'REBOOT':
        return server

    if server.status == 'SHUTOFF':
        LOG.info(f"Start server '{server.id}' (status='{server.status}').")
        client.servers.start(server.id)
    else:
        LOG.info(f"Reboot server '{server.id}' (status='{server.status}').")
        client.servers.reboot(server.id)

    return wait_for_server_status(server=server.id, status='ACTIVE',
                                  client=client, timeout=timeout,
                                  sleep_time=sleep_time)


def ensure_server_status(server: ServerType,
                         status: str,
                         client: NovaClientType = None,
                         timeout: tobiko.Seconds = None,
                         sleep_time: tobiko.Seconds = None) -> NovaServer:
    if status == 'ACTIVE':
        return activate_server(server=server, client=client, timeout=timeout,
                               sleep_time=sleep_time)
    elif status == 'SHUTOFF':
        return shutoff_server(server=server, client=client, timeout=timeout,
                              sleep_time=sleep_time)
    else:
        raise ValueError(f"Unsupported server status: '{status}'")
