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

import unittest

import testtools

import tobiko
from tobiko import config
from tobiko.shell import sh
from tobiko.openstack import keystone
from tobiko.openstack import metalsmith
from tobiko import tripleo


CONF = config.CONF


@tripleo.skip_if_missing_undercloud
class UndercloudSshConnectionTest(testtools.TestCase):

    def setUp(self):
        super(UndercloudSshConnectionTest, self).setUp()
        self.ssh_client = tripleo.undercloud_ssh_client()

    def test_connect_to_undercloud(self):
        self.ssh_client.connect()

    def test_fetch_undercloud_credentials(self):
        env = tripleo.load_undercloud_rcfile()
        if not env.get('OS_CLOUD'):
            self.assertTrue(env['OS_AUTH_URL'])
            self.assertTrue(env.get('OS_USERNAME') or env.get('OS_USER_ID'))
            self.assertTrue(env['OS_PASSWORD'])
            self.assertTrue(env.get('OS_TENANT_NAME') or
                            env.get('OS_PROJECT_NAME') or
                            env.get('OS_TENANT_ID') or
                            env.get('OS_PROJECT_ID'))

    def test_execute_command(self):
        result = sh.execute('hostname', ssh_client=self.ssh_client)
        self.assertTrue(result.stdout.startswith('undercloud-0'))


@tripleo.skip_if_missing_undercloud
class UndercloudKeystoneClientTest(testtools.TestCase):

    def test_undercloud_keystone_credentials(self):
        fixture = tripleo.undercloud_keystone_credentials()
        self.assertIsInstance(fixture,
                              keystone.KeystoneCredentialsFixture)
        credentials = keystone.keystone_credentials(fixture)
        credentials.validate()

    def test_undercloud_keystone_session(self):
        session = tripleo.undercloud_keystone_session()
        client = metalsmith.get_metalsmith_client(session=session)
        overcloud_nodes = metalsmith.list_instances(client=client)
        self.assertTrue(overcloud_nodes)

    def test_undercloud_keystone_client(self):
        client = tripleo.undercloud_keystone_client()
        services = keystone.list_services(client=client)
        self.assertTrue(services)


@tripleo.skip_if_missing_undercloud
class UndercloudVersionTest(unittest.TestCase):
    # TODO(eolivare): move the properties to a common class, since they are
    # duplicate in OvercloudVersionTest and UndercloudVersionTest

    @property
    def lower_version(self) -> str:
        v = tripleo.undercloud_version()
        if v.micro > 0:
            lower_v = f"{v.major}.{v.minor}.{v.micro - 1}"
        elif v.minor > 0:
            lower_v = f"{v.major}.{v.minor - 1}.{v.micro}"
        elif v.major > 0:
            lower_v = f"{v.major - 1}.{v.minor}.{v.micro}"
        else:
            raise ValueError(f"wrong version: {v}")
        return lower_v

    @property
    def same_version(self) -> str:
        v = tripleo.undercloud_version()
        return f"{v.major}.{v.minor}.{v.micro}"

    @property
    def higher_version(self) -> str:
        v = tripleo.undercloud_version()
        return f"{v.major}.{v.minor}.{v.micro + 1}"

    @tripleo.skip_if_missing_undercloud
    def test_undercloud_version(self):
        version = tripleo.undercloud_version()
        self.assertTrue(tobiko.match_version(version, min_version='13'))

    def test_has_undercloud(self):
        self.assertTrue(tripleo.has_undercloud())

    def test_has_undercloud_with_min_version(self):
        self.assertTrue(
            tripleo.has_undercloud(min_version=self.same_version))

    def test_has_undercloud_with_min_version_lower(self):
        self.assertTrue(
            tripleo.has_undercloud(min_version=self.lower_version))

    def test_has_undercloud_with_min_version_higher(self):
        self.assertFalse(
            tripleo.has_undercloud(min_version=self.higher_version))

    def test_has_undercloud_with_max_version(self):
        self.assertFalse(
            tripleo.has_undercloud(max_version=self.same_version))

    def test_has_undercloud_with_max_version_lower(self):
        self.assertFalse(
            tripleo.has_undercloud(max_version=self.lower_version))

    def test_has_undercloud_with_max_version_higher(self):
        self.assertTrue(
            tripleo.has_undercloud(max_version=self.higher_version))

    def test_skip_unless_has_undercloud(self):
        self._assert_test_skip_unless_has_undercloud_dont_skip()

    def test_skip_unless_has_undercloud_with_min_version(self):
        self._assert_test_skip_unless_has_undercloud_dont_skip(
            min_version=self.same_version)

    def test_skip_unless_has_undercloud_with_min_version_lower(self):
        self._assert_test_skip_unless_has_undercloud_dont_skip(
            min_version=self.lower_version)

    def test_skip_unless_has_undercloud_with_min_version_higher(self):
        self._assert_test_skip_unless_has_undercloud_skip(
            min_version=self.higher_version)

    def test_skip_unless_has_undercloud_with_max_version(self):
        self._assert_test_skip_unless_has_undercloud_skip(
            max_version=self.same_version)

    def test_skip_unless_has_undercloud_with_max_version_lower(self):
        self._assert_test_skip_unless_has_undercloud_skip(
            max_version=self.lower_version)

    def test_skip_unless_has_undercloud_with_max_version_higher(self):
        self._assert_test_skip_unless_has_undercloud_dont_skip(
            max_version=self.higher_version)

    def _assert_test_skip_unless_has_undercloud_dont_skip(
            self,
            min_version: tobiko.VersionType = None,
            max_version: tobiko.VersionType = None):
        executed = []

        @tripleo.skip_unless_has_undercloud(min_version=min_version,
                                            max_version=max_version)
        def decorated_function():
            executed.append(True)

        self.assertFalse(executed)
        decorated_function()
        self.assertTrue(executed)

    def _assert_test_skip_unless_has_undercloud_skip(
            self,
            min_version: tobiko.VersionType = None,
            max_version: tobiko.VersionType = None):
        @tripleo.skip_unless_has_undercloud(min_version=min_version,
                                            max_version=max_version)
        def decorated_function():
            raise self.fail('Not skipped')

        with self.assertRaises(unittest.SkipTest):
            decorated_function()
