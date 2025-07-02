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

from neutronclient.v2_0 import client as neutronclient

import tobiko
from tobiko.openstack import _client


NeutronClientException = neutronclient.exceptions.NeutronClientException
NotFound = neutronclient.exceptions.NotFound
ServiceUnavailable = neutronclient.exceptions.ServiceUnavailable


class NeutronClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session):
        return neutronclient.Client(session=session,
                                    additional_headers={'Connection': 'close'})


class NeutronClientManager(_client.OpenstackClientManager):

    def create_client(self, session):
        return NeutronClientFixture(session=session)


CLIENTS = NeutronClientManager()


NeutronClient = neutronclient.Client
NeutronClientType = typing.Union[neutronclient.Client,
                                 NeutronClientFixture]


def neutron_client(obj: NeutronClientType = None) \
        -> neutronclient.Client:
    if obj is None:
        return get_neutron_client()

    if isinstance(obj, neutronclient.Client):
        return obj

    fixture = tobiko.setup_fixture(obj)
    if isinstance(fixture, NeutronClientFixture):
        return fixture.client

    message = "Object {!r} is not a NeutronClientFixture".format(obj)
    raise TypeError(message)


class HasNeutronClientFixture(tobiko.SharedFixture):

    client: typing.Optional[neutronclient.Client] = None

    def __init__(self, obj: NeutronClientType = None):
        super(HasNeutronClientFixture, self).__init__()
        self._obj = obj

    def setup_fixture(self):
        self.client = neutron_client(self._obj)


def get_neutron_client(session=None, shared=True, init_client=None,
                       manager=None) -> neutronclient.Client:
    manager = manager or CLIENTS
    client = manager.get_client(session=session, shared=shared,
                                init_client=init_client)
    tobiko.setup_fixture(client)
    return client.client
