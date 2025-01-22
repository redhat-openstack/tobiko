# Copyright (c) 2019 Red Hat
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

import inspect
from unittest import mock

from keystoneauth1 import session as _session

import tobiko
from tobiko.openstack import _client
from tobiko.openstack import keystone
from tobiko.tests.unit import openstack


CLIENT = object()


class ClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session=None):
        return CLIENT


MockSession = mock.create_autospec(_session.Session)


class OpenstackClientFixtureTest(openstack.OpenstackTest):

    def create_client(self, session=None):
        return ClientFixture(session=session)

    def test_init(self, session=None):
        client = self.create_client(session=session)
        self.assertIs(session or None, client.session)

    def test_init_with_credentials(self):
        self.test_init(session=MockSession)

    def test_init_with_credentials_fixture(self):
        self.test_init(session=keystone.KeystoneSessionFixture())

    def test_init_with_credentials_fixture_type(self):
        self.test_init(session=keystone.KeystoneSessionFixture)

    def test_setup(self, session=None):
        client = self.create_client(session=session)
        client.setUp()
        if session:
            if tobiko.is_fixture(session):
                if inspect.isclass(session):
                    session = tobiko.get_fixture(session)
                self.assertIs(session.session, client.session)
            else:
                self.assertIs(session, client.session)
        else:
            self.assertIs(keystone.get_keystone_session(), client.session)

    def test_setup_with_session(self):
        self.test_setup(session=MockSession())

    def test_setup_with_session_fixture(self):
        self.test_setup(session=keystone.KeystoneSessionFixture())

    def test_setup_with_session_fixture_type(self):
        self.test_setup(session=keystone.KeystoneSessionFixture)


class ClientManager(_client.OpenstackClientManager):

    def create_client(self, session):
        return ClientFixture(session=session)


class OpenstackClientManagerTest(openstack.OpenstackTest):

    def setUp(self):
        super(OpenstackClientManagerTest, self).setUp()
        self.patch(keystone, 'get_keystone_session',
                   return_value=MockSession())

    def test_init(self):
        manager = ClientManager()
        self.assertEqual({}, manager.clients)

    def test_get_client(self, session=None, shared=True):
        manager = ClientManager()
        client1 = manager.get_client(session=session, shared=shared)
        client2 = manager.get_client(session=session, shared=shared)
        if shared:
            self.assertIs(client1, client2)
        else:
            self.assertIsNot(client1, client2)

    def test_get_client_with_not_shared(self):
        self.test_get_client(shared=False)

    def test_get_client_with_session(self):
        self.test_get_client(session=MockSession())

    def test_get_client_with_session_fixture(self):
        self.test_get_client(session=keystone.KeystoneSessionFixture())

    def test_get_client_with_session_fixture_type(self):
        self.test_get_client(session=keystone.KeystoneSessionFixture)

    def test_get_client_with_init_client(self):
        init_client = mock.MagicMock(return_value=CLIENT)
        manager = _client.OpenstackClientManager()
        session = MockSession()
        client = manager.get_client(session=session,
                                    init_client=init_client)
        self.assertIs(CLIENT, client)
        init_client.assert_called_once_with(session=session)
