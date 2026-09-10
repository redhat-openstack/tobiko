# Copyright 2026 Red Hat
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

import tobiko
from tobiko.podified import containers
from tobiko.tests import unit


COLUMNS = ['container_host', 'container_name', 'container_state']


def _table(*rows):
    return tobiko.TableData(list(rows), columns=COLUMNS)


class SelectContainerTest(unit.TobikoUnitTest):
    # These tests exercise the private _select_container() helper directly.
    # pylint: disable=protected-access

    def test_returns_name_and_attrs_when_present(self):
        table = _table(('node-0', 'nova_compute', 'running'))
        name, attrs, fail = containers._select_container(
            'nova_compute', full_name=True, node_name='node-0',
            containers_list_td=table)
        self.assertEqual('nova_compute', name)
        self.assertFalse(attrs.empty)
        self.assertEqual([], fail)

    def test_returns_none_name_when_absent(self):
        # An absent container must yield a None name (not the loop candidate),
        # so callers can treat it as "not found" instead of dereferencing the
        # empty attrs table.
        table = _table(('node-0', 'nova_compute', 'running'))
        name, attrs, fail = containers._select_container(
            'ovn_bgp_agent', full_name=True, node_name='node-0',
            containers_list_td=table)
        self.assertIsNone(name)
        self.assertTrue(attrs.empty)
        self.assertEqual(1, len(fail))

    def test_returns_none_name_when_all_alternatives_absent(self):
        table = _table(('node-0', 'nova_compute', 'running'))
        name, attrs, fail = containers._select_container(
            ('ovn_metadata_agent', 'ovn_agent'), full_name=True,
            node_name='node-0', containers_list_td=table)
        self.assertIsNone(name)
        self.assertTrue(attrs.empty)
        self.assertEqual(2, len(fail))


class AssertContainersRunningTest(unit.TobikoUnitTest):

    def _patch_nodes(self, rows):
        node = mock.Mock()
        node.name = 'node-0'
        self.patch(containers.topology, 'list_openstack_nodes',
                   return_value=[node])
        self.patch(containers, 'list_node_containers', return_value=[])
        self.patch(containers, 'get_container_states_list',
                   return_value=list(rows))

    def test_bool_check_returns_false_for_absent_container(self):
        # Regression: an absent container used to raise ValueError
        # ("Can't call item() on empty data") instead of returning False.
        self._patch_nodes([('node-0', 'nova_compute', 'running')])
        result = containers.assert_containers_running(
            'edpm-compute', ['ovn_bgp_agent'], bool_check=True)
        self.assertFalse(result)

    def test_bool_check_returns_true_for_running_container(self):
        self._patch_nodes([('node-0', 'nova_compute', 'running')])
        result = containers.assert_containers_running(
            'edpm-compute', ['nova_compute'], bool_check=True)
        self.assertTrue(result)
