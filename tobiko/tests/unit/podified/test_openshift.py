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

from tobiko.podified import _openshift
from tobiko.tests.unit import _case


class TestHasCompactOcpCluster(_case.TobikoUnitTest):
    """Tests for has_compact_ocp_cluster function.

    A compact OCP cluster is one where master nodes are also labeled as
    workers, so rebooting all controller nodes at once would reboot every
    master simultaneously and break etcd quorum.
    """

    def setUp(self):
        super().setUp()
        self.mock_list_ocp_nodes = mock.patch.object(
            _openshift, 'list_ocp_nodes')
        self.mock_list_ocp_nodes = self.mock_list_ocp_nodes.start()
        self.addCleanup(mock.patch.stopall)

    def test_standard_cluster(self):
        """Masters and workers are disjoint sets: not compact."""
        self.mock_list_ocp_nodes.return_value = [
            {'roles': ['node-role.kubernetes.io/master']},
            {'roles': ['node-role.kubernetes.io/master']},
            {'roles': ['node-role.kubernetes.io/master']},
            {'roles': ['node-role.kubernetes.io/worker']},
            {'roles': ['node-role.kubernetes.io/worker']},
        ]
        self.assertFalse(_openshift.has_compact_ocp_cluster())

    def test_compact_cluster(self):
        """Masters that are also workers: compact."""
        master_worker_roles = [
            'node-role.kubernetes.io/master',
            'node-role.kubernetes.io/worker',
        ]
        self.mock_list_ocp_nodes.return_value = [
            {'roles': master_worker_roles},
            {'roles': master_worker_roles},
            {'roles': master_worker_roles},
            {'roles': ['node-role.kubernetes.io/worker']},
        ]
        self.assertTrue(_openshift.has_compact_ocp_cluster())

    def test_no_nodes(self):
        """Empty node list: not compact."""
        self.mock_list_ocp_nodes.return_value = []
        self.assertFalse(_openshift.has_compact_ocp_cluster())


class TestGetControlplaneName(_case.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        self.mock_oc = mock.patch.object(_openshift, 'oc').start()
        self.addCleanup(mock.patch.stopall)

    def test_get_controlplane_name(self):
        self.mock_oc.selector.return_value.qname.return_value = (
            'openstackcontrolplane/controlplane')
        self.assertEqual(
            'controlplane', _openshift.get_controlplane_name())


class TestAssertControlplaneReady(_case.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        self.mock_get_name = mock.patch.object(
            _openshift, 'get_controlplane_name').start()
        self.mock_get_name.return_value = 'controlplane'
        self.mock_oc = mock.patch.object(_openshift, 'oc').start()
        self.addCleanup(mock.patch.stopall)

    def _set_conditions(self, conditions):
        cp_obj = mock.Mock()
        cp_obj.as_dict.return_value = {'status': {'conditions': conditions}}
        self.mock_oc.selector.return_value.objects.return_value = [cp_obj]

    def test_controlplane_ready(self):
        self._set_conditions([{'type': 'Ready', 'status': 'True'}])
        _openshift.assert_controlplane_ready()

    def test_controlplane_not_ready(self):
        self._set_conditions([{'type': 'Ready', 'status': 'False'}])
        self.assertRaises(
            _openshift.OcpControlPlaneNotReady,
            _openshift.assert_controlplane_ready)
