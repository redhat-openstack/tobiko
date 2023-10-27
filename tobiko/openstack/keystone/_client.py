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

import typing

from keystoneclient import base
from keystoneclient import client as keystoneclient
from keystoneauth1 import exceptions
from keystoneclient.v2_0 import client as v2_client
from keystoneclient.v3 import client as v3_client
from keystoneclient.v3 import endpoints as v3_endpoints
from oslo_log import log

import tobiko
from tobiko.openstack import _client


LOG = log.getLogger(__name__)


class KeystoneClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session):
        from tobiko import config
        if config.CONF.tobiko.keystone.interface is None:
            return keystoneclient.Client(session=session)
        else:
            return keystoneclient.Client(
                session=session,
                interface=config.CONF.tobiko.keystone.interface)


class KeystoneClientManager(_client.OpenstackClientManager):

    def create_client(self, session):
        return KeystoneClientFixture(session=session)


CLIENTS = KeystoneClientManager()
CLIENT_CLASSES = (v2_client.Client, v3_client.Client)
KeystoneClient = typing.Union[v2_client.Client, v3_client.Client]
KeystoneClientType = typing.Union[KeystoneClient,
                                  KeystoneClientFixture,
                                  typing.Type[KeystoneClientFixture],
                                  None]


def keystone_client(obj: KeystoneClientType) -> KeystoneClient:
    if obj is None:
        return get_keystone_client()

    if isinstance(obj, CLIENT_CLASSES):
        return obj

    fixture = tobiko.setup_fixture(obj)
    if isinstance(fixture, KeystoneClientFixture):
        return tobiko.setup_fixture(obj).client

    raise TypeError(f"Object {obj} is not a KeystoneClientFixture")


def get_keystone_client(session=None, shared=True, init_client=None,
                        manager=None) -> KeystoneClient:
    manager = manager or CLIENTS
    client = manager.get_client(session=session, shared=shared,
                                init_client=init_client)
    tobiko.setup_fixture(client)
    return client.client


_RAISE_ERROR = object()


def find_endpoint(client=None, unique=False, default=_RAISE_ERROR,
                  **attributes):
    endpoints = list_endpoints(client=client, **attributes)
    if default is _RAISE_ERROR or endpoints:
        if unique:
            return endpoints.unique
        else:
            return endpoints.first
    else:
        return default


def find_service(client=None, unique=False, default=_RAISE_ERROR, **attribute):
    services = list_services(client=client, **attribute)
    if default is _RAISE_ERROR or services:
        if unique:
            return services.unique
        else:
            return services.first
    else:
        return default


def list_endpoints(client=None, service=None, interface=None, region=None,
                   translate=True, **attributes):
    client = keystone_client(client)

    service = service or attributes.pop('service_id', None)
    if service:
        attributes['service_id'] = base.getid(service)

    region = region or attributes.pop('region_id', None)
    if region:
        attributes['region_id'] = base.getid(region)

    try:
        if client.version == 'v2.0':
            endpoints = client.endpoints.list()
            if translate:
                endpoints = translate_v2_endpoints(v2_endpoints=endpoints,
                                                   interface=interface)
        else:
            endpoints = client.endpoints.list(service=service,
                                              interface=interface,
                                              region=region)
    except exceptions.ClientException:
        LOG.exception('Error listing services endpoints:\n'
                      f'  client: {client}\n'
                      f'  service: {service}\n'
                      f'  interface: {interface}\n'
                      f'  region: {region}\n'
                      f'  translate: {translate}\n'
                      f'  attributes: {attributes}\n')
        raise

    endpoints = tobiko.select(endpoints)
    if attributes:
        endpoints = endpoints.with_attributes(**attributes)
    return endpoints


def list_services(client=None, name=None, service_type=None, **attributes):
    client = keystone_client(client)

    service_type = service_type or attributes.pop('type', None)
    if service_type:
        attributes['type'] = base.getid(service_type)

    if name:
        attributes['name'] = name

    if client.version == 'v2.0':
        services = client.services.list()
    else:
        services = client.services.list(name=name,
                                        service_type=service_type)
    services = tobiko.select(services)
    if attributes:
        services = services.with_attributes(**attributes)
    return services


def translate_v2_endpoints(v2_endpoints, interface=None):
    interfaces = interface and [interface] or v3_endpoints.VALID_INTERFACES
    endpoints = []
    for endpoint in v2_endpoints:
        for interface in interfaces:
            url = getattr(endpoint, interface + 'url')
            info = dict(id=endpoint.id,
                        interface=interface,
                        region_id=endpoint.region,
                        service_id=endpoint.service_id,
                        url=url,
                        enabled=endpoint.enabled)
            endpoints.append(v3_endpoints.Endpoint(manager=None,
                                                   info=info))
    return endpoints


def find_service_endpoint(enabled=True, interface='public', client=None,
                          **params):
    client = keystone_client(client)
    service = find_service(client=client, enabled=enabled, **params)
    return find_endpoint(client=client, service=service, interface=interface,
                         enabled=enabled)
