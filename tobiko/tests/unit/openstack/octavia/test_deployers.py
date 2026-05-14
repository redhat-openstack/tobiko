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
from tobiko.openstack.octavia import _client
from tobiko.openstack.octavia import _deployers
from tobiko.openstack.octavia import _waiters


class HasDualStackExternalNetworkTest(testtools.TestCase):

    @mock.patch.object(_deployers, 'get_external_subnet')
    def test_true_when_both_subnets_same_network(self, get_subnet):
        get_subnet.side_effect = [
            {'id': 'v4', 'network_id': 'net-1'},
            {'id': 'v6', 'network_id': 'net-1'},
        ]
        self.assertTrue(_deployers.has_dual_stack_external_network())

    @mock.patch.object(_deployers, 'get_external_subnet')
    def test_false_when_no_ipv4_subnet(self, get_subnet):
        get_subnet.return_value = None
        self.assertFalse(_deployers.has_dual_stack_external_network())
        get_subnet.assert_called_once_with(4)

    @mock.patch.object(_deployers, 'get_external_subnet')
    def test_false_when_no_ipv6_subnet(self, get_subnet):
        get_subnet.side_effect = [
            {'id': 'v4', 'network_id': 'net-1'},
            None,
        ]
        self.assertFalse(_deployers.has_dual_stack_external_network())

    @mock.patch.object(_deployers, 'get_external_subnet')
    def test_false_when_subnets_on_different_networks(self, get_subnet):
        get_subnet.side_effect = [
            {'id': 'v4', 'network_id': 'net-1'},
            {'id': 'v6', 'network_id': 'net-2'},
        ]
        self.assertFalse(_deployers.has_dual_stack_external_network())


class EnsureDualStackOvnLoadBalancerTest(testtools.TestCase):

    @mock.patch.object(_deployers, '_create_dual_stack_ovn_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_creates_when_lb_missing(self, find_lb, create_lb):
        find_lb.return_value = None
        create_lb.return_value = SimpleNamespace(id='new-lb')
        result = _deployers.ensure_dual_stack_ovn_load_balancer(
            'dual-lb', 'ovn')
        self.assertEqual(result, create_lb.return_value)
        create_lb.assert_called_once_with('dual-lb', 'ovn')

    @mock.patch.object(_client, 'find_ipv6_vip_on_load_balancer')
    @mock.patch.object(_deployers.octavia, 'get_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_reuses_lb_with_ipv6_vip(
            self, find_lb, get_lb, find_vip):
        find_lb.return_value = SimpleNamespace(id='lb-1')
        lb = SimpleNamespace(id='lb-1', additional_vips=[
            {'ip_address': '2001:db8::1'},
        ])
        get_lb.return_value = lb
        find_vip.return_value = '2001:db8::1'
        result = _deployers.ensure_dual_stack_ovn_load_balancer(
            'dual-lb', 'ovn')
        self.assertEqual(result, lb)

    @mock.patch.object(_waiters, 'wait_for_ipv6_additional_vip')
    @mock.patch.object(_client, 'find_ipv6_vip_on_load_balancer')
    @mock.patch.object(_deployers.octavia, 'get_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_waits_when_existing_lb_has_no_ipv6_vip_yet(
            self, find_lb, get_lb, find_vip, wait_ipv6):
        find_lb.return_value = SimpleNamespace(id='lb-1')
        stale_lb = SimpleNamespace(
            id='lb-1',
            additional_vips=None,
            provisioning_status='ACTIVE',
        )
        ready_lb = SimpleNamespace(
            id='lb-1',
            additional_vips=[{'ip_address': '2001:db8::1'}],
            provisioning_status='ACTIVE',
        )
        get_lb.return_value = stale_lb
        find_vip.return_value = None
        wait_ipv6.return_value = ready_lb
        result = _deployers.ensure_dual_stack_ovn_load_balancer(
            'dual-lb', 'ovn')
        self.assertEqual(result, ready_lb)
        wait_ipv6.assert_called_once_with('lb-1')

    @mock.patch.object(_deployers, '_create_dual_stack_ovn_load_balancer')
    @mock.patch.object(_waiters, 'wait_for_ipv6_additional_vip')
    @mock.patch.object(_client, 'find_ipv6_vip_on_load_balancer')
    @mock.patch.object(_deployers.octavia, 'get_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_fails_when_existing_lb_has_no_ipv6_vip_after_wait(
            self, find_lb, get_lb, find_vip, wait_ipv6, create_lb):
        find_lb.return_value = SimpleNamespace(id='lb-1')
        stale_lb = SimpleNamespace(
            id='lb-1',
            additional_vips=None,
            provisioning_status='ACTIVE',
        )
        get_lb.return_value = stale_lb
        find_vip.return_value = None
        wait_ipv6.return_value = None
        ex = self.assertRaises(
            tobiko.FailureException,
            _deployers.ensure_dual_stack_ovn_load_balancer,
            'dual-lb', 'ovn')
        self.assertIn('no IPv6 additional VIP after waiting', str(ex))
        wait_ipv6.assert_called_once_with('lb-1')
        create_lb.assert_not_called()


class Ipv6VipFromLoadBalancerTest(testtools.TestCase):

    @mock.patch.object(_client, 'find_ipv6_vip_on_load_balancer')
    def test_delegates_to_find(self, find_vip):
        find_vip.return_value = '2001:db8::1'
        lb = SimpleNamespace()
        self.assertEqual(
            _deployers.ipv6_vip_from_load_balancer(lb),
            '2001:db8::1')
        find_vip.assert_called_once_with(lb)

    @mock.patch.object(_client, 'find_ipv6_vip_on_load_balancer')
    def test_none_additional_vips_returns_none(self, find_vip):
        find_vip.return_value = None
        lb = SimpleNamespace(additional_vips=None)
        self.assertIsNone(_deployers.ipv6_vip_from_load_balancer(lb))

    @mock.patch.object(_client, 'find_ipv6_vip_on_load_balancer')
    def test_empty_additional_vips_returns_none(self, find_vip):
        find_vip.return_value = None
        lb = SimpleNamespace(additional_vips=[])
        self.assertIsNone(_deployers.ipv6_vip_from_load_balancer(lb))
