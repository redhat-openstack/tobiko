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

from octaviaclient.api.v2 import octavia

import tobiko
from tobiko.openstack import _client, openstacksdkclient
from tobiko.openstack import keystone


OCTAVIA_CLIENT_CLASSSES = octavia.OctaviaAPI,


OctaviaClientType = typing.Union[octavia.OctaviaAPI,
                                 'OctaviaClientFixture']


def get_octavia_endpoint(keystone_client=None):
    return keystone.find_service_endpoint(name='octavia',
                                          client=keystone_client)


class OctaviaClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session):
        keystone_client = keystone.get_keystone_client(session=session)
        endpoint = get_octavia_endpoint(keystone_client=keystone_client)
        return octavia.OctaviaAPI(session=session, endpoint=endpoint.url)


class OctaviaClientManager(_client.OpenstackClientManager):

    def create_client(self, session):
        return OctaviaClientFixture(session=session)


CLIENTS = OctaviaClientManager()


@keystone.skip_if_missing_service(name='octavia')
def octavia_client(obj: OctaviaClientType = None) -> octavia.OctaviaAPI:
    if obj is None:
        return get_octavia_client()

    if isinstance(obj, OCTAVIA_CLIENT_CLASSSES):
        return obj

    fixture = tobiko.setup_fixture(obj)
    if isinstance(fixture, OctaviaClientFixture):
        return fixture.client

    message = "Object {!r} is not an OctaviaClientFixture".format(obj)
    raise TypeError(message)


def get_octavia_client(session=None, shared=True, init_client=None,
                       manager=None):
    manager = manager or CLIENTS
    client = manager.get_client(session=session, shared=shared,
                                init_client=init_client)
    tobiko.setup_fixture(client)
    return client.client


def list_members(pool_id: str):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.members(pool=pool_id)


def list_load_balancers(**lb_kwargs):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.load_balancers(**lb_kwargs)


def find_load_balancer(lb_name: str):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.find_load_balancer(lb_name)


def create_load_balancer(lb_kwargs):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.create_load_balancer(**lb_kwargs)


def find_listener(listener_name: str):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.find_listener(listener_name)


def create_listener(listener_kwargs):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.create_listener(**listener_kwargs)


def find_pool(pool_name: str):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.find_pool(pool_name)


def create_pool(pool_kwargs):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.create_pool(**pool_kwargs)


def find_member(member_name: str, pool: str):
    # Note that pool could be either id or name
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.find_member(member_name, pool)


def create_member(member_kwargs):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.create_member(**member_kwargs)


def create_health_monitor(hm_kwargs):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.create_health_monitor(**hm_kwargs)


def find_health_monitor(hm_name: str):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.find_health_monitor(hm_name)


def get_load_balancer(lb_id: str):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.get_load_balancer(lb_id)


def get_health_monitor(hm_id: str):
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    return os_sdk_client.load_balancer.get_health_monitor(hm_id)


# The load balancer ``additional_vips`` attribute (used for dual-stack VIPs)
# was introduced in the Octavia API version 2.26.
LB_ADDITIONAL_VIPS_API_VERSION = '2.26'


def _to_version_string(value: typing.Any) -> str:
    if isinstance(value, (tuple, list)):
        return '.'.join(str(part) for part in value)
    return str(value)


def get_octavia_max_api_version() -> typing.Optional[tobiko.Version]:
    """Return the Octavia (load-balancer) API max version.

    Octavia uses an additive minor-version model rather than negotiated
    microversions, so its version discovery document may either expose a
    single object holding ``min_version``/``max_version`` or a list with one
    entry per supported minor version (each carrying an ``id`` such as
    ``2.24``). Both layouts are handled here.

    Returns None when the maximum version cannot be determined.
    """
    os_sdk_client = openstacksdkclient.openstacksdk_client()
    lb_proxy = os_sdk_client.load_balancer

    # openstacksdk may already have discovered the microversion range
    try:
        endpoint_data = lb_proxy.get_endpoint_data()
    except Exception:  # pylint: disable=broad-except
        endpoint_data = None
    if endpoint_data is not None:
        max_microversion = getattr(endpoint_data, 'max_microversion', None)
        if max_microversion:
            return tobiko.parse_version(_to_version_string(max_microversion))

    # Fall back to reading Octavia's version discovery document. Take the
    # highest version advertised, reading ``max_version`` when present and
    # otherwise the per-entry ``id`` (e.g. '2.24').
    endpoint = lb_proxy.get_endpoint()
    root = endpoint.split('/v2', 1)[0].rstrip('/') + '/'
    versions = lb_proxy.get(root).json().get('versions', [])
    candidates = [version.get('max_version') or version.get('id')
                  for version in versions]
    parsed = [tobiko.parse_version(_to_version_string(value))
              for value in candidates if value]
    if not parsed:
        return None
    return max(parsed)


def has_lb_additional_vips_support() -> bool:
    """Return True if the Octavia API supports load balancer additional_vips.

    The ``additional_vips`` attribute (used for dual-stack VIPs) was added in
    the Octavia API version 2.26.
    """
    max_version = get_octavia_max_api_version()
    return (max_version is not None and
            tobiko.match_version(
                max_version, min_version=LB_ADDITIONAL_VIPS_API_VERSION))


def find_ipv6_vip_on_load_balancer(lb: typing.Any) -> typing.Optional[str]:
    """Return the IPv6 address from ``additional_vips``, or None."""
    additional = getattr(lb, 'additional_vips', None) or []
    for entry in additional:
        if isinstance(entry, dict):
            addr = entry.get('ip_address')
        else:
            addr = getattr(entry, 'ip_address', None)
        if not addr:
            continue
        addr = str(addr)
        if ':' in addr:
            return addr
    return None
