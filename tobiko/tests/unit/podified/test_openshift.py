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


def _make_pod(name, phase, ready=None):
    status: dict = {'phase': phase}
    if ready is not None:
        status['conditions'] = [{'type': 'Ready',
                                 'status': 'True' if ready else 'False'}]
    pod = mock.Mock()
    pod.name.return_value = name
    pod.as_dict.return_value = {'status': status}
    return pod


class TestIsPodHealthy(_case.TobikoUnitTest):
    # These tests exercise the private _is_pod_healthy() helper directly.
    # pylint: disable=protected-access

    def test_succeeded_phase(self):
        pod = _make_pod('job-1', 'Succeeded')
        self.assertTrue(_openshift._is_pod_healthy(pod))

    def test_running_and_ready(self):
        pod = _make_pod('api-0', 'Running', ready=True)
        self.assertTrue(_openshift._is_pod_healthy(pod))

    def test_running_and_not_ready(self):
        pod = _make_pod('manila-scheduler-1', 'Running', ready=False)
        self.assertFalse(_openshift._is_pod_healthy(pod))

    def test_running_without_ready_condition(self):
        pod = _make_pod('api-0', 'Running')
        self.assertFalse(_openshift._is_pod_healthy(pod))

    def test_pending_phase(self):
        pod = _make_pod('api-0', 'Pending')
        self.assertFalse(_openshift._is_pod_healthy(pod))


class TestAssertOcpPodsRunning(_case.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        self.mock_get_pods = mock.patch.object(
            _openshift, 'get_pods').start()
        self.addCleanup(mock.patch.stopall)

    def test_all_pods_healthy(self):
        self.mock_get_pods.return_value = [
            _make_pod('api-0', 'Running', ready=True),
            _make_pod('job-0', 'Succeeded'),
        ]
        _openshift.assert_ocp_pods_running()

    def test_unhealthy_pod_raises(self):
        self.mock_get_pods.return_value = [
            _make_pod('manila-scheduler-1', 'Running', ready=False),
        ]
        ex = self.assertRaises(
            _openshift.OcpPodsNotRunning, _openshift.assert_ocp_pods_running)
        self.assertIn('manila-scheduler-1 (Running)', str(ex))


class TestWaitForAllOcpPodsRunning(_case.TobikoUnitTest):
    """Regression coverage for the Galera-disruption health-check race.

    After a Galera disruption, consumer pods (e.g. manila-scheduler) can
    stay Running-but-NotReady for a while after the DB cluster itself is
    already reported healthy. wait_for_all_ocp_pods_running() must retry
    instead of failing on the first unhealthy snapshot.
    """

    def setUp(self):
        super().setUp()
        self.mock_get_pods = mock.patch.object(
            _openshift, 'get_pods').start()
        self.addCleanup(mock.patch.stopall)

    def test_waits_until_pods_become_ready(self):
        self.patch_time()
        self.mock_get_pods.side_effect = [
            [_make_pod('manila-scheduler-1', 'Running', ready=False)],
            [_make_pod('manila-scheduler-1', 'Running', ready=False)],
            [_make_pod('manila-scheduler-1', 'Running', ready=True)],
        ]
        _openshift.wait_for_all_ocp_pods_running(timeout=60)
        self.assertEqual(3, self.mock_get_pods.call_count)

    def test_raises_after_timeout(self):
        self.patch_time(time_increment=100.)
        self.mock_get_pods.return_value = [
            _make_pod('manila-scheduler-1', 'Running', ready=False),
        ]
        self.assertRaises(
            tobiko.RetryTimeLimitError,
            _openshift.wait_for_all_ocp_pods_running, timeout=60)
