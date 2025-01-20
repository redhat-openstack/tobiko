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

import inspect
from unittest import mock

from keystoneclient.v3 import endpoints
from octaviaclient.api.v2 import octavia as octaviaclient

from tobiko.openstack import keystone
from tobiko.openstack import octavia
from tobiko.tests import unit
from tobiko.tests.unit import openstack
from tobiko.tests.unit.openstack import test_client


class KeystoneModulePatch(unit.PatchFixture):

    client = object()
    endpoint = endpoints.Endpoint(manager=None,
                                  info={'url': 'http://some/endpoint'})
    session = None
    name = None

    def setup_fixture(self):
        module = inspect.getmodule(octavia.OctaviaClientFixture)
        self.patch(module, 'keystone', self)

    def get_keystone_client(self, session):
        self.session = session
        return self.client

    def find_service_endpoint(self, name, client):
        self.name = name
        assert self.client is client
        return self.endpoint


class OctaviaClientFixtureTest(test_client.OpenstackClientFixtureTest):

    def setUp(self):
        super(OctaviaClientFixtureTest, self).setUp()
        self.useFixture(KeystoneModulePatch())

    def create_client(self, session=None):
        return octavia.OctaviaClientFixture(session=session)


class GetOctaviaClientTest(openstack.OpenstackTest):

    def setUp(self):
        super(GetOctaviaClientTest, self).setUp()
        self.useFixture(KeystoneModulePatch())

    def test_get_octavia_client(self, session=None, shared=True):
        client1 = octavia.get_octavia_client(session=session, shared=shared)
        client2 = octavia.get_octavia_client(session=session, shared=shared)
        if shared:
            self.assertIs(client1, client2)
        else:
            self.assertIsNot(client1, client2)
        self.assertIsInstance(client1, octaviaclient.OctaviaAPI)
        self.assertIsInstance(client2, octaviaclient.OctaviaAPI)

    def test_get_octavia_client_with_not_shared(self):
        self.test_get_octavia_client(shared=False)

    def test_get_octavia_client_with_session(self):
        session = keystone.get_keystone_session()
        self.test_get_octavia_client(session=session)


class OctaviaClientTest(openstack.OpenstackTest):

    def setUp(self):
        super(OctaviaClientTest, self).setUp()
        self.useFixture(KeystoneModulePatch())

    def _get_octavia_client(self, client_type):
        with mock.patch('tobiko.openstack.keystone._services.has_service',
                        return_value=True):
            return octavia.octavia_client(client_type)

    def test_octavia_client_with_none(self):
        default_client = octavia.get_octavia_client()
        client = self._get_octavia_client(None)
        self.assertIsInstance(client, octaviaclient.OctaviaAPI)
        self.assertIs(default_client, client)

    def test_octavia_client_with_client(self):
        default_client = octavia.get_octavia_client()
        client = self._get_octavia_client(default_client)
        self.assertIsInstance(client, octaviaclient.OctaviaAPI)
        self.assertIs(default_client, client)

    def test_octavia_client_with_fixture(self):
        fixture = octavia.OctaviaClientFixture()
        client = self._get_octavia_client(fixture)
        self.assertIsInstance(client, octaviaclient.OctaviaAPI)
        self.assertIs(client, fixture.client)
