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

from unittest import mock

from tobiko.openstack import neutron
from tobiko.openstack.neutron import _ovn
from tobiko.tests import unit


OVN_MODULE = 'tobiko.openstack.neutron._ovn'
TOPOLOGY_MODULE = 'tobiko.openstack.topology'


class BuildOvndbCommandTest(unit.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        self.mock_connection = mock.patch(
            f'{OVN_MODULE}._get_ovndb_connection',
            return_value='tcp:192.168.1.1:6641').start()
        self.mock_prefix = mock.patch(
            f'{OVN_MODULE}._get_ovn_controller_container_prefix',
            return_value='').start()
        self.addCleanup(mock.patch.stopall)

    def test_nbdb_with_format_and_query(self):
        result = neutron.build_ovndb_command(
            neutron.NBDB,
            'find ACL external_ids:"neutron\\:security_group_rule_id"'
            '="test-id"',
            output_format='json')
        self.assertIn('ovn-nbctl', result)
        self.assertIn('--format json', result)
        self.assertIn('--no-leader-only', result)
        self.assertIn('--db=tcp:192.168.1.1:6641', result)
        self.assertIn('find ACL', result)

    def test_sbdb_binary_selection(self):
        result = neutron.build_ovndb_command(
            neutron.SBDB, 'show')
        self.assertIn('ovn-sbctl', result)
        self.assertNotIn('ovn-nbctl', result)

    def test_no_format_flag_when_none(self):
        result = neutron.build_ovndb_command(
            neutron.NBDB, 'show')
        self.assertNotIn('--format', result)

    def test_no_leader_only_disabled(self):
        result = neutron.build_ovndb_command(
            neutron.NBDB, 'show', no_leader_only=False)
        self.assertNotIn('--no-leader-only', result)

    def test_no_leader_only_enabled_by_default(self):
        result = neutron.build_ovndb_command(
            neutron.NBDB, 'show')
        self.assertIn('--no-leader-only', result)

    def test_container_prefix_included(self):
        self.mock_prefix.return_value = 'podman exec ovn_controller '
        result = neutron.build_ovndb_command(
            neutron.NBDB, 'show')
        self.assertTrue(
            result.startswith('podman exec ovn_controller '))

    def test_no_container_prefix_when_empty(self):
        result = neutron.build_ovndb_command(
            neutron.NBDB, 'show')
        self.assertTrue(result.startswith('ovn-nbctl'))

    def test_invalid_ovndb_raises_value_error(self):
        self.assertRaises(
            ValueError,
            neutron.build_ovndb_command,
            'invalid_db', 'show')


class GetOvndbSshClientTest(unit.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        _ovn._cache.clear()  # pylint: disable=W0212

    @mock.patch(f'{TOPOLOGY_MODULE}.get_openstack_node')
    @mock.patch(f'{OVN_MODULE}.agent_mod')
    def test_returns_first_sshable_host(self, mock_agent_mod,
                                        mock_get_node):
        mock_ssh = mock.MagicMock()
        mock_agent = {'host': 'compute-0'}
        mock_agent_mod.list_networking_agents.return_value = [
            mock_agent]
        mock_node = mock.MagicMock()
        mock_node.ssh_client = mock_ssh
        mock_get_node.return_value = mock_node

        result = neutron.get_ovndb_ssh_client()
        self.assertEqual(mock_ssh, result)

    @mock.patch(f'{TOPOLOGY_MODULE}.get_openstack_node')
    @mock.patch(f'{OVN_MODULE}.agent_mod')
    def test_returns_none_when_no_sshable_host(
            self, mock_agent_mod, mock_get_node):
        mock_agent = {'host': 'compute-0'}
        mock_agent_mod.list_networking_agents.return_value = [
            mock_agent]
        mock_node = mock.MagicMock()
        mock_node.ssh_client = None
        mock_get_node.return_value = mock_node

        result = neutron.get_ovndb_ssh_client()
        self.assertIsNone(result)

    def test_caches_result(self):
        mock_ssh = mock.MagicMock()
        _ovn._cache['ssh_client'] = mock_ssh  # pylint: disable=W0212
        result = neutron.get_ovndb_ssh_client()
        self.assertEqual(mock_ssh, result)


class GetOvnControllerContainerPrefixTest(unit.TobikoUnitTest):

    # pylint: disable=W0212
    _get_prefix = staticmethod(
        _ovn._get_ovn_controller_container_prefix)

    @mock.patch(f'{TOPOLOGY_MODULE}.get_openstack_topology')
    def test_with_containers(self, mock_get_topology):
        mock_topology_obj = mock.MagicMock()
        mock_topology_obj.has_containers = True
        mock_topology_obj.container_runtime_cmd = 'podman'
        mock_topology_obj.get_agent_container_name.return_value = (
            'ovn_controller')
        mock_get_topology.return_value = mock_topology_obj

        result = self._get_prefix()
        self.assertEqual(
            'podman exec ovn_controller ', result)

    @mock.patch(f'{TOPOLOGY_MODULE}.get_openstack_topology')
    def test_without_containers(self, mock_get_topology):
        mock_topology_obj = mock.MagicMock()
        mock_topology_obj.has_containers = False
        mock_get_topology.return_value = mock_topology_obj

        result = self._get_prefix()
        self.assertEqual('', result)
