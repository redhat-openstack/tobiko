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

from unittest import mock

from keystoneauth1 import session as keystonesession

from tobiko.openstack import keystone
from tobiko.tests.unit import openstack


CREDENTIALS = keystone.keystone_credentials(
    api_version=3,
    auth_url='http://127.0.0.1:4000/identiy/v3',
    username='demo',
    project_name='demo',
    password='this is a secret',
    user_domain_name='Default',
    project_domain_name='Default')


DEFAULT_CREDENTIALS = keystone.keystone_credentials(
    api_version=2,
    auth_url='http://127.0.0.1:5000/identiy/v2.0',
    username='admin',
    project_name='admin',
    password='this is a secret')


class CredentialsFixture(keystone.KeystoneCredentialsFixture):

    def _get_credentials(self) -> keystone.KeystoneCredentials:
        return CREDENTIALS


class DefaultCredentialsFixture(CredentialsFixture):

    def _get_credentials(self) -> keystone.KeystoneCredentials:
        return DEFAULT_CREDENTIALS


class KeystoneSessionFixtureTest(openstack.OpenstackTest):

    def test_init(self,
                  credentials: keystone.KeystoneCredentialsType = None):
        # pylint: disable=protected-access
        session = keystone.KeystoneSessionFixture(credentials=credentials)
        self.assertIs(credentials, session._credentials)

    def test_init_with_credentials(self):
        self.test_init(credentials=CREDENTIALS)

    def test_init_with_credentials_fixture(self):
        self.test_init(credentials=CredentialsFixture())

    def test_init_with_credentials_fixture_type(self):
        self.test_init(credentials=CredentialsFixture)

    def test_setup(self,
                   credentials: keystone.KeystoneCredentialsType = None):
        session = keystone.KeystoneSessionFixture(credentials=credentials)
        session.setUp()
        self.assertEqual(keystone.keystone_credentials(credentials),
                         session.credentials)

    def test_setup_with_credentials(self):
        self.test_setup(credentials=CREDENTIALS)

    def test_setup_with_credentials_fixture(self):
        self.test_setup(credentials=CredentialsFixture())

    def test_setup_with_credentials_fixture_type(self):
        self.test_setup(credentials=CredentialsFixture)


class KeystoneSessionManagerTest(openstack.OpenstackTest):

    def test_init(self):
        manager = keystone.KeystoneSessionManager()
        self.assertTrue(manager)
        self.assertEqual({}, manager.sessions)

    def test_get_session(self,
                         credentials: keystone.KeystoneCredentialsType = None,
                         shared=True):
        manager = keystone.KeystoneSessionManager()

        session = manager.get_session(credentials=credentials,
                                      shared=shared)
        self.assertIsNotNone(session.credentials)
        self.assertIs(keystone.keystone_credentials(credentials),
                      session.credentials)
        self.assertIsInstance(session, keystone.KeystoneSessionFixture)
        shared_session = manager.get_session(credentials=credentials)
        if shared in [True, None]:
            self.assertIs(session, shared_session)
        else:
            self.assertIsNot(session, shared_session)

    def test_get_session_with_credentials(self):
        self.test_get_session(credentials=CREDENTIALS)

    def test_get_session_with_not_shared(self):
        self.test_get_session(shared=False)

    def test_get_session_with_credentials_fixture(self):
        self.test_get_session(credentials=CredentialsFixture())

    def test_get_session_with_credentials_fixture_type(self):
        self.test_get_session(credentials=CredentialsFixture)

    def test_get_session_with_init_session(self):
        mock_session = mock.MagicMock(spec=keystone.KeystoneSessionFixture)
        self.assertIsInstance(mock_session, keystone.KeystoneSessionFixture)
        init_session = mock.MagicMock(return_value=mock_session)
        manager = keystone.KeystoneSessionManager()
        session = manager.get_session(credentials=CREDENTIALS,
                                      init_session=init_session)
        self.assertIs(mock_session, session)
        init_session.assert_called_once_with(CREDENTIALS)


class GetKeystomeSessionTest(openstack.OpenstackTest):

    def test_get_keystone_session(
            self,
            credentials: keystone.KeystoneCredentialsType = None,
            shared=True):
        session1 = keystone.get_keystone_session(
            credentials=credentials,
            shared=shared)
        session2 = keystone.get_keystone_session(credentials=credentials,
                                                 shared=shared)
        if shared:
            self.assertIs(session1, session2)
        else:
            self.assertIsNot(session1, session2)
        self.assertIsInstance(session1, keystonesession.Session)
        self.assertIsInstance(session2, keystonesession.Session)

    def test_get_keystone_session_with_not_shared(self):
        self.test_get_keystone_session(shared=False)

    def test_get_keystone_session_with_credentials(self):
        credentials = keystone.default_keystone_credentials()
        self.test_get_keystone_session(credentials=credentials)
