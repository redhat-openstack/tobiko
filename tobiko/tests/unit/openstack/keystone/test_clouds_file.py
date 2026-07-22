# Copyright (c) 2026 Red Hat
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

from tobiko.openstack import keystone
from tobiko.openstack.keystone import _clouds_file
from tobiko.tests.unit import openstack


V3_CLOUDS_CONTENT = {
    'clouds': {
        'mycloud': {
            'auth': {
                'auth_url': 'http://10.0.0.1:5000/v3',
                'username': 'admin',
                'password': 'secret123',
                'project_name': 'admin',
                'user_domain_name': 'Default',
                'project_domain_name': 'Default',
            },
        },
    },
}

V2_CLOUDS_CONTENT = {
    'clouds': {
        'mycloud': {
            'auth': {
                'auth_url': 'http://10.0.0.1:5000/v2.0',
                'username': 'admin',
                'password': 'secret123',
                'project_name': 'admin',
            },
        },
    },
}

V3_CLOUDS_NO_PASSWORD = {
    'clouds': {
        'mycloud': {
            'auth': {
                'auth_url': 'http://10.0.0.1:5000/v3',
                'username': 'admin',
                'project_name': 'admin',
                'user_domain_name': 'Default',
                'project_domain_name': 'Default',
            },
        },
    },
}

SECURE_CONTENT = {
    'clouds': {
        'mycloud': {
            'auth': {
                'password': 'dynamic-password-xyz',
            },
        },
    },
}


class DeepMergeTest(openstack.OpenstackTest):

    def test_flat_merge(self):
        base = {'a': 1, 'b': 2}
        override = {'b': 3, 'c': 4}
        result = _clouds_file.deep_merge(base, override)
        self.assertEqual({'a': 1, 'b': 3, 'c': 4}, result)

    def test_nested_merge(self):
        base = {'clouds': {'mycloud': {'auth': {'username': 'admin'}}}}
        override = {'clouds': {'mycloud': {'auth': {'password': 'pw'}}}}
        result = _clouds_file.deep_merge(base, override)
        expected = {
            'clouds': {
                'mycloud': {
                    'auth': {
                        'username': 'admin',
                        'password': 'pw',
                    },
                },
            },
        }
        self.assertEqual(expected, result)

    def test_override_wins_for_non_dict(self):
        base = {'a': 'old'}
        override = {'a': 'new'}
        result = _clouds_file.deep_merge(base, override)
        self.assertEqual({'a': 'new'}, result)

    def test_empty_override(self):
        base = {'a': 1, 'b': {'c': 2}}
        result = _clouds_file.deep_merge(base, {})
        self.assertEqual({'a': 1, 'b': {'c': 2}}, result)

    def test_does_not_mutate_base(self):
        base = {'a': {'b': 1}}
        override = {'a': {'b': 2}}
        _clouds_file.deep_merge(base, override)
        self.assertEqual({'a': {'b': 1}}, base)


class ParseCredentialsTest(openstack.OpenstackTest):

    def test_parse_v3(self):
        creds = _clouds_file.parse_credentials(
            file_spec='test:clouds.yaml',
            content=V3_CLOUDS_CONTENT,
            cloud_name='mycloud')
        self.assertEqual('admin', creds.username)
        self.assertEqual('secret123', creds.password)
        self.assertEqual('http://10.0.0.1:5000/v3', creds.auth_url)
        self.assertEqual(3, creds.api_version)

    def test_parse_v2(self):
        creds = _clouds_file.parse_credentials(
            file_spec='test:clouds.yaml',
            content=V2_CLOUDS_CONTENT,
            cloud_name='mycloud')
        self.assertEqual('admin', creds.username)
        self.assertEqual('secret123', creds.password)
        self.assertEqual(2, creds.api_version)

    def test_no_clouds_section(self):
        self.assertRaises(
            keystone.NoSuchKeystoneCredentials,
            _clouds_file.parse_credentials,
            file_spec='test:clouds.yaml',
            content={'other': {}},
            cloud_name='mycloud')

    def test_cloud_name_not_found(self):
        self.assertRaises(
            keystone.NoSuchKeystoneCredentials,
            _clouds_file.parse_credentials,
            file_spec='test:clouds.yaml',
            content={'clouds': {'other': {}}},
            cloud_name='mycloud')

    def test_no_auth_section(self):
        self.assertRaises(
            keystone.NoSuchKeystoneCredentials,
            _clouds_file.parse_credentials,
            file_spec='test:clouds.yaml',
            content={'clouds': {'mycloud': {}}},
            cloud_name='mycloud')

    def test_no_password(self):
        self.assertRaises(
            keystone.NoSuchKeystoneCredentials,
            _clouds_file.parse_credentials,
            file_spec='test:clouds.yaml',
            content=V3_CLOUDS_NO_PASSWORD,
            cloud_name='mycloud')

    def test_merged_with_secure(self):
        merged = _clouds_file.deep_merge(
            dict(V3_CLOUDS_NO_PASSWORD), SECURE_CONTENT)
        creds = _clouds_file.parse_credentials(
            file_spec='test:clouds.yaml',
            content=merged,
            cloud_name='mycloud')
        self.assertEqual('dynamic-password-xyz', creds.password)
        self.assertEqual('admin', creds.username)

    def test_secure_overrides_clouds_password(self):
        merged = _clouds_file.deep_merge(
            dict(V3_CLOUDS_CONTENT), SECURE_CONTENT)
        creds = _clouds_file.parse_credentials(
            file_spec='test:clouds.yaml',
            content=merged,
            cloud_name='mycloud')
        self.assertEqual('dynamic-password-xyz', creds.password)

    def test_password_converted_to_string(self):
        content = {
            'clouds': {
                'mycloud': {
                    'auth': {
                        'auth_url': 'http://10.0.0.1:5000/v3',
                        'username': 'admin',
                        'password': 12345,
                        'project_name': 'admin',
                        'user_domain_name': 'Default',
                        'project_domain_name': 'Default',
                    },
                },
            },
        }
        creds = _clouds_file.parse_credentials(
            file_spec='test:clouds.yaml',
            content=content,
            cloud_name='mycloud')
        self.assertEqual('12345', creds.password)
        self.assertIsInstance(creds.password, str)
