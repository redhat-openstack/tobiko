# Copyright 2021 Red Hat
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

import ironicclient
import ironicclient.v1.client
from oslo_log import log

import tobiko
from tobiko.openstack import _client


LOG = log.getLogger(__name__)

CLIENT_CLASSES = (ironicclient.v1.client.Client,)
IronicClient = typing.Union[ironicclient.v1.client.Client]


class IronicClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session) -> IronicClient:
        return ironicclient.client.get_client(
            1, session=session, additional_headers={'Connection': 'close'})


class IronicClientManager(_client.OpenstackClientManager):

    def create_client(self, session) -> IronicClientFixture:
        return IronicClientFixture(session=session)


CLIENTS = IronicClientManager()

IronicClientType = typing.Union[IronicClient,
                                IronicClientFixture,
                                typing.Type[IronicClientFixture],
                                None]


def ironic_client(obj: IronicClientType) -> IronicClient:
    if obj is None:
        return get_ironic_client()

    if isinstance(obj, CLIENT_CLASSES):
        return obj

    fixture = tobiko.setup_fixture(obj)
    if isinstance(fixture, IronicClientFixture):
        assert fixture.client is not None
        return fixture.client

    message = f"Object '{obj}' is not an IronicClientFixture instance"
    raise TypeError(message)


def get_ironic_client(session=None, shared=True, init_client=None,
                      manager=None) -> IronicClient:
    manager = manager or CLIENTS
    client = manager.get_client(session=session, shared=shared,
                                init_client=init_client)
    tobiko.setup_fixture(client)
    return client.client
