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
from types import SimpleNamespace
from unittest import mock

from keystoneclient.v3 import endpoints
from octaviaclient.api.v2 import octavia as octaviaclient
import testtools

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import octavia
from tobiko.openstack.octavia import _client
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


class HasLbAdditionalVipsSupportTest(testtools.TestCase):

    def _patch_lb_proxy(self, lb_proxy):
        os_sdk_client = SimpleNamespace(load_balancer=lb_proxy)
        return mock.patch(
            'tobiko.openstack.octavia._client.openstacksdkclient.'
            'openstacksdk_client',
            return_value=os_sdk_client)

    def test_max_version_from_endpoint_data(self):
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion='2.27')
        with self._patch_lb_proxy(lb_proxy):
            self.assertEqual(
                _client.get_octavia_max_api_version(),
                tobiko.parse_version('2.27'))
            self.assertTrue(_client.has_lb_additional_vips_support())

    def test_max_version_from_endpoint_data_as_tuple(self):
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion=(2, 26))
        with self._patch_lb_proxy(lb_proxy):
            self.assertTrue(_client.has_lb_additional_vips_support())

    def test_older_api_not_supported(self):
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion='2.25')
        with self._patch_lb_proxy(lb_proxy):
            self.assertFalse(_client.has_lb_additional_vips_support())

    def test_fallback_to_version_document(self):
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion=None)
        lb_proxy.get_endpoint.return_value = 'https://host:13876/v2.0'
        lb_proxy.get.return_value = SimpleNamespace(
            json=lambda: {'versions': [
                {'id': 'v2.0', 'min_version': '2.0',
                 'max_version': '2.28'}]})
        with self._patch_lb_proxy(lb_proxy):
            self.assertEqual(
                _client.get_octavia_max_api_version(),
                tobiko.parse_version('2.28'))
            self.assertTrue(_client.has_lb_additional_vips_support())
        lb_proxy.get.assert_called_with('https://host:13876/')

    def test_fallback_version_list_by_id(self):
        # Octavia deployments that list one entry per minor version (each
        # carrying an 'id' but no 'max_version'), as seen in the field.
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion=None)
        lb_proxy.get_endpoint.return_value = 'https://host:13876/v2'
        lb_proxy.get.return_value = SimpleNamespace(
            json=lambda: {'versions': [
                {'id': '2.0', 'status': 'SUPPORTED'},
                {'id': '2.24', 'status': 'CURRENT'}]})
        with self._patch_lb_proxy(lb_proxy):
            self.assertEqual(
                _client.get_octavia_max_api_version(),
                tobiko.parse_version('2.24'))
            # 2.24 < 2.26 -> additional_vips not supported
            self.assertFalse(_client.has_lb_additional_vips_support())
        lb_proxy.get.assert_called_with('https://host:13876/')

    def test_fallback_version_list_by_id_supported(self):
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion=None)
        lb_proxy.get_endpoint.return_value = 'https://host:13876/v2'
        lb_proxy.get.return_value = SimpleNamespace(
            json=lambda: {'versions': [
                {'id': 'v2.0', 'status': 'SUPPORTED'},
                {'id': 'v2.26', 'status': 'CURRENT'}]})
        with self._patch_lb_proxy(lb_proxy):
            self.assertEqual(
                _client.get_octavia_max_api_version(),
                tobiko.parse_version('2.26'))
            self.assertTrue(_client.has_lb_additional_vips_support())

    def test_fallback_older_api_not_supported(self):
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion=None)
        lb_proxy.get_endpoint.return_value = 'https://host:13876/v2.0'
        lb_proxy.get.return_value = SimpleNamespace(
            json=lambda: {'versions': [
                {'id': 'v2.0', 'min_version': '2.0',
                 'max_version': '2.11'}]})
        with self._patch_lb_proxy(lb_proxy):
            self.assertFalse(_client.has_lb_additional_vips_support())

    def test_unknown_version_not_supported(self):
        lb_proxy = mock.Mock()
        lb_proxy.get_endpoint_data.return_value = SimpleNamespace(
            max_microversion=None)
        lb_proxy.get_endpoint.return_value = 'https://host:13876/v2.0'
        lb_proxy.get.return_value = SimpleNamespace(
            json=lambda: {'versions': []})
        with self._patch_lb_proxy(lb_proxy):
            self.assertIsNone(_client.get_octavia_max_api_version())
            self.assertFalse(_client.has_lb_additional_vips_support())


class FindIpv6VipOnLoadBalancerTest(testtools.TestCase):

    def test_dict_entry_ipv6(self):
        lb = SimpleNamespace(additional_vips=[
            {'subnet_id': 's1', 'ip_address': '2001:db8::1'},
        ])
        self.assertEqual(
            _client.find_ipv6_vip_on_load_balancer(lb),
            '2001:db8::1')

    def test_object_entry_ipv6(self):
        vip = SimpleNamespace(ip_address='2001:db8::2')
        lb = SimpleNamespace(additional_vips=[vip])
        self.assertEqual(
            _client.find_ipv6_vip_on_load_balancer(lb),
            '2001:db8::2')

    def test_skips_ipv4_uses_next(self):
        lb = SimpleNamespace(additional_vips=[
            {'ip_address': '203.0.113.1'},
            {'ip_address': '2001:db8::3'},
        ])
        self.assertEqual(
            _client.find_ipv6_vip_on_load_balancer(lb),
            '2001:db8::3')

    def test_none_additional_vips_returns_none(self):
        lb = SimpleNamespace(additional_vips=None)
        self.assertIsNone(_client.find_ipv6_vip_on_load_balancer(lb))

    def test_empty_additional_vips_returns_none(self):
        lb = SimpleNamespace(additional_vips=[])
        self.assertIsNone(_client.find_ipv6_vip_on_load_balancer(lb))
