# Copyright 2025 Red Hat
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

import copy

import testtools

from tobiko.openstack.manila._client import to_dict


class FakeResource:
    """Mimics manilaclient Resource objects."""

    def __init__(self, info):
        self._info = info
        for key, value in info.items():
            setattr(self, key, value)

    def to_dict(self):
        return copy.deepcopy(self._info)


class ToDictTest(testtools.TestCase):

    def test_with_dict(self):
        d = {'id': '123', 'name': 'share1'}
        result = to_dict(d)
        self.assertEqual(d, result)
        self.assertIs(d, result)

    def test_with_resource(self):
        info = {'id': '123', 'name': 'share1', 'status': 'available'}
        resource = FakeResource(info)
        result = to_dict(resource)
        self.assertEqual(info, result)
        self.assertIsInstance(result, dict)

    def test_with_list_of_resources(self):
        resources = [
            FakeResource({'id': '1', 'name': 'share1'}),
            FakeResource({'id': '2', 'name': 'share2'}),
        ]
        result = to_dict(resources)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {'id': '1', 'name': 'share1'})
        self.assertEqual(result[1], {'id': '2', 'name': 'share2'})

    def test_with_list_of_dicts(self):
        dicts = [{'id': '1'}, {'id': '2'}]
        result = to_dict(dicts)
        self.assertEqual(dicts, result)

    def test_with_empty_list(self):
        result = to_dict([])
        self.assertEqual([], result)

    def test_with_nested_data_in_resource(self):
        info = {
            'id': '123',
            'metadata': {'key': 'value'},
            'links': [{'href': 'http://example.com', 'rel': 'self'}],
        }
        resource = FakeResource(info)
        result = to_dict(resource)
        self.assertEqual(info, result)
        self.assertIsInstance(result['metadata'], dict)
        self.assertIsInstance(result['links'], list)

    def test_with_resource_without_to_dict(self):
        """Falls back to _info when to_dict() is not available."""

        class BareResource:
            def __init__(self, info):
                self._info = info

        info = {'id': '123', 'name': 'share1'}
        resource = BareResource(info)
        result = to_dict(resource)
        self.assertEqual(info, result)
