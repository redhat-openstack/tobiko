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

from heatclient.v1 import client as v1_client

import tobiko
from tobiko.openstack import _client
from tobiko.openstack import keystone


HeatClient = typing.Union[v1_client.Client]


class HeatClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session) -> HeatClient:
        return v1_client.Client(session=session,
                                endpoint_type='public',
                                service_type='orchestration')


class HeatClientManager(_client.OpenstackClientManager):

    def create_client(self, session) -> HeatClientFixture:
        return HeatClientFixture(session=session)


CLIENTS = HeatClientManager()


HeatClientType = typing.Union[None,
                              HeatClient,
                              HeatClientFixture]


@keystone.skip_if_missing_service(name='heat')
def heat_client(obj: HeatClientType = None) -> HeatClient:
    if obj is None:
        return default_heat_client()

    if isinstance(obj, v1_client.Client):
        return obj

    fixture = tobiko.get_fixture(obj)
    if isinstance(fixture, HeatClientFixture):
        return tobiko.setup_fixture(fixture).client

    message = "Object {!r} is not a NeutronClientFixture".format(obj)
    raise TypeError(message)


def default_heat_client() -> HeatClient:
    return get_heat_client()


def get_heat_client(session=None, shared=True, init_client=None,
                    manager=None) -> HeatClient:
    manager = manager or CLIENTS
    fixture = manager.get_client(session=session, shared=shared,
                                 init_client=init_client)
    return tobiko.setup_fixture(fixture).client
