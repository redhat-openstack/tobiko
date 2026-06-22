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

from types import SimpleNamespace
from unittest import mock

import testtools

import tobiko
from tobiko.openstack.octavia import _waiters


class WaitForIpv6AdditionalVipTest(testtools.TestCase):

    @mock.patch.object(_waiters, 'wait_for_load_balancer')
    def test_timeout_returns_none(self, wait_for_lb):
        wait_for_lb.side_effect = tobiko.RetryTimeLimitError(
            attempt=mock.Mock())
        lb = SimpleNamespace(
            additional_vips=[{'subnet_id': 's6'}],
            provisioning_status='ACTIVE',
            vip_address='203.0.113.1',
        )
        with mock.patch.object(_waiters, 'get_load_balancer',
                               return_value=lb) as get_lb:
            result = _waiters.wait_for_ipv6_additional_vip('lb-1')

        self.assertIsNone(result)
        wait_for_lb.assert_called_once()
        get_lb.assert_called_once_with('lb-1')

    @mock.patch.object(_waiters, 'wait_for_load_balancer')
    def test_returns_lb_when_ready(self, wait_for_lb):
        lb = SimpleNamespace(id='lb-1')
        wait_for_lb.return_value = lb
        self.assertIs(
            _waiters.wait_for_ipv6_additional_vip('lb-1'), lb)


class WaitForOvnServiceMonitorStatusTest(testtools.TestCase):

    @mock.patch.object(_waiters.topology, 'get_config_setting')
    @mock.patch.object(_waiters.sh, 'execute')
    @mock.patch.object(_waiters.topology, 'get_openstack_topology')
    @mock.patch.object(_waiters.topology, 'list_openstack_nodes')
    def test_waits_for_expected_status(
            self, mock_list_nodes, mock_get_topology,
            mock_execute, mock_get_config):
        # Setup mocks
        mock_get_config.return_value = 'tcp:127.0.0.1:6642'
        mock_topology = mock.Mock()
        mock_topology.has_containers = False
        mock_get_topology.return_value = mock_topology
        mock_controller = mock.Mock()
        mock_controller.ssh_client = mock.Mock()
        mock_list_nodes.return_value = [mock_controller]

        # First call returns 'offline', second call returns 'online'
        mock_result1 = mock.Mock()
        mock_result1.stdout = "offline"
        mock_result2 = mock.Mock()
        mock_result2.stdout = "online"
        mock_execute.side_effect = [mock_result1, mock_result2]

        # Call function
        _waiters.wait_for_ovn_service_monitor_status(
            member_ip='192.168.100.10',
            protocol_port=80,
            expected_status='online',
            timeout=10,
            interval=1)

        # Verify execute was called twice (for ovn-sbctl queries)
        self.assertEqual(2, mock_execute.call_count)
