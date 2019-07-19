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

from keystoneclient import base
from keystoneclient import client as keystoneclient
from keystoneclient.v2_0 import client as v2_client
from keystoneclient.v3 import client as v3_client
from keystoneclient.v3 import endpoints as v3_endpoints

import tobiko
from tobiko.openstack import _client


class KeystoneClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session):
        return keystoneclient.Client(session=session)


class KeystoneClientManager(_client.OpenstackClientManager):

    def create_client(self, session):
        return KeystoneClientFixture(session=session)


CLIENTS = KeystoneClientManager()


CLIENT_CLASSES = (v2_client.Client, v3_client.Client)


def keystone_client(obj):
    if not obj:
        return get_keystone_client()

    if isinstance(obj, CLIENT_CLASSES):
        return obj

    fixture = tobiko.setup_fixture(obj)
    if isinstance(fixture, KeystoneClientFixture):
        return fixture.client

    message = "Object {!r} is not a KeystoneClientFixture".format(obj)
    raise TypeError(message)


def get_keystone_client(session=None, shared=True, init_client=None,
                        manager=None):
    manager = manager or CLIENTS
    client = manager.get_client(session=session, shared=shared,
                                init_client=init_client)
    tobiko.setup_fixture(client)
    return client.client


def find_endpoint(client=None, check_found=True, check_unique=False,
                  **params):
    endpoints = list_endpoints(client=client, **params)
    return find_resource(resources=endpoints, check_found=check_found,
                         check_unique=check_unique)


def find_service(client=None, check_found=True, check_unique=False,
                 **params):
    services = list_services(client=client, **params)
    return find_resource(resources=services, check_found=check_found,
                         check_unique=check_unique)


def list_endpoints(client=None, service=None, interface=None, region=None,
                   translate=True, **params):
    client = keystone_client(client)

    service = service or params.pop('service_id', None)
    if service:
        params['service_id'] = base.getid(service)

    region = region or params.pop('region_id', None)
    if region:
        params['region_id'] = base.getid(region)

    if client.version == 'v2.0':
        endpoints = client.endpoints.list()
        if translate:
            endpoints = translate_v2_endpoints(v2_endpoints=endpoints,
                                               interface=interface)
    else:
        endpoints = client.endpoints.list(service=service,
                                          interface=interface,
                                          region=region)
    if params:
        endpoints = find_resources(endpoints, **params)
    return list(endpoints)


def list_services(client=None, name=None, service_type=None, **params):
    client = keystone_client(client)

    service_type = service_type or params.pop('type', None)
    if service_type:
        params['type'] = base.getid(service_type)

    if name:
        params['name'] = name

    if client.version == 'v2.0':
        services = client.services.list()
    else:
        services = client.services.list(name=name,
                                        service_type=service_type)

    if params:
        services = find_resources(services, **params)
    return list(services)


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


def find_resource(resources, check_found=True, check_unique=True, **params):
    """Look for a service matching some property values"""
    resource_it = find_resources(resources, **params)
    try:
        resource = next(resource_it)
    except StopIteration:
        resource = None

    if check_found and resource is None:
        raise KeystoneResourceNotFound(params=params)

    if check_unique:
        duplicate_ids = [s.id for s in resource_it]
        if duplicate_ids:
            raise MultipleKeystoneResourcesFound(params=params)

    return resource


def find_resources(resources, **params):
    """Look for a service matching some property values"""
    # Remove parameters with None value
    for resource in resources:
        for name, match in params.items():
            value = getattr(resource, name)
            if match is not None and match != value:
                break
        else:
            yield resource


class KeystoneResourceNotFound(tobiko.TobikoException):
    message = 'No such resource found with parameters {params!r}'


class MultipleKeystoneResourcesFound(tobiko.TobikoException):
    message = 'Multiple resources found with parameters {params!r}'
