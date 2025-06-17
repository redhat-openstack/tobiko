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
from collections import abc

from oslo_log import log
from designateclient.v2 import client

import tobiko
from tobiko.openstack import _client

DESIGNATE_CLIENT_CLASSES = client.Client,

LOG = log.getLogger(__name__)


class DesignateClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session) -> client.Client:
        return client.Client(session=session)


class DesignateClientManager(_client.OpenstackClientManager):

    def create_client(self, session) -> DesignateClientFixture:
        return DesignateClientFixture(session=session)


CLIENTS = DesignateClientManager()

DesignateClientType = typing.Union[client.Client, DesignateClientFixture]


DesignateZone = typing.Mapping[str, typing.Any]
DesignateZoneType = typing.Union[str, typing.Mapping[str, typing.Any]]


def designate_client(obj: DesignateClientType = None):
    if obj is None:
        return get_designate_client()

    if isinstance(obj, client.Client):
        return obj

    fixture = tobiko.setup_fixture(obj)
    if isinstance(fixture, DesignateClientFixture):
        return fixture.client

    message = "Object {!r} is not an DesignateClientFixture".format(obj)
    raise TypeError(message)


def get_designate_client(session=None,
                         shared=True,
                         init_client=None,
                         manager: DesignateClientManager = None) \
        -> client.Client:
    manager = manager or CLIENTS
    fixture = manager.get_client(session=session,
                                 shared=shared,
                                 init_client=init_client)
    tobiko.setup_fixture(fixture)
    return fixture.client


def designate_zone_id(zone: DesignateZoneType) -> str:
    if isinstance(zone, str):
        return zone
    elif isinstance(zone, abc.Mapping):
        return zone['id']
    else:
        raise TypeError(f'{zone} object is an invalid Designate zone type')


def get_designate_zone(zone: str) -> DesignateZone:
    zone_id = designate_zone_id(zone)
    return designate_client().zones.get(zone_id)


def list_recordsets(zone: str) -> DesignateZone:
    zone_id = designate_zone_id(zone)
    return designate_client().recordsets.list(zone_id)


def create_recordsets(zone: str, name: str, type_: str,
                      records: typing.List[str]):
    zone_id = designate_zone_id(zone)
    return designate_client().recordsets.create(
        zone_id, name=name, type_=type_, records=records)


def get_recordset(zone_id: str, recordset_id: str):
    return designate_client().recordsets.get(
        zone=zone_id, recordset=recordset_id)


def wait_for_status(status_key, status, get_client, object_id,
                    interval: tobiko.Seconds = None,
                    timeout: tobiko.Seconds = None,
                    **kwargs):
    """Waits for an object to reach a specific status.

    :param status_key: The key of the status field in the response.
                       Ex. status
    :param status: The status to wait for. Ex. "ACTIVE"
    :param get_client: The tobiko client get method.
                        Ex. _client.get_zone
    :param object_id: The id of the object to query.
    :param interval: How often to check the status, in seconds.
    :param timeout: The maximum time, in seconds, to check the status.
    :raises TimeoutException: The object did not achieve the status or ERROR in
                              the check_timeout period.
    :raises UnexpectedStatusException: The request returned an unexpected
                                       response code.
    """
    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval,
                                default_timeout=300.,
                                default_interval=3.):
        response = get_client(object_id, **kwargs)
        if response[status_key] == status:
            return response

        attempt.check_limits()

        LOG.debug(f"Waiting for {get_client.__name__} {status_key} to get "
                  f"from '{response[status_key]}' to '{status}'...")
