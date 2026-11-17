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


SUBNETS = {'vip_subnet_id': 'tenant-v4',
           'additional_vip_subnet_id': 'tenant-v6'}


def _fake_conf(ipv4_cidr=None, ipv6_cidr=None):
    neutron_conf = SimpleNamespace(ipv4_cidr=ipv4_cidr, ipv6_cidr=ipv6_cidr)
    return SimpleNamespace(tobiko=SimpleNamespace(neutron=neutron_conf))


class HasDualStackTenantNetworkTest(testtools.TestCase):

    def _has_dual_stack(self, **kwargs):
        with mock.patch.object(_deployers, 'CONF', _fake_conf(**kwargs)):
            return _deployers.has_dual_stack_tenant_network()

    def test_true_when_ipv4_and_ipv6_cidrs(self):
        self.assertTrue(self._has_dual_stack(ipv4_cidr='10.100.0.0/16',
                                             ipv6_cidr='fc00::/48'))

    def test_false_when_no_ipv6_cidr(self):
        self.assertFalse(self._has_dual_stack(ipv4_cidr='10.100.0.0/16'))

    def test_false_when_empty_ipv6_cidr(self):
        self.assertFalse(self._has_dual_stack(ipv4_cidr='10.100.0.0/16',
                                              ipv6_cidr=''))

    def test_false_when_no_ipv4_cidr(self):
        self.assertFalse(self._has_dual_stack(ipv6_cidr='fc00::/48'))


class CreateDualStackOvnLoadBalancerTest(testtools.TestCase):

    @mock.patch.object(_deployers, 'get_external_subnet')
    @mock.patch.object(_deployers.octavia, 'wait_for_status')
    @mock.patch.object(_deployers.octavia, 'create_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_vips_on_given_tenant_subnets(self, find_lb, create_lb,
                                          wait_status, get_ext_subnet):
        find_lb.return_value = None
        create_lb.return_value = SimpleNamespace(id='lb-1', name='dual-lb')
        result = _deployers.ensure_dual_stack_ovn_load_balancer(
            'dual-lb', 'ovn', **SUBNETS)
        self.assertEqual(result, create_lb.return_value)
        create_lb.assert_called_once_with({
            'provider': 'ovn',
            'vip_subnet_id': 'tenant-v4',
            'additional_vips': [{'subnet_id': 'tenant-v6'}],
            'name': 'dual-lb',
        })
        wait_status.assert_called_once_with(object_id='lb-1')
        get_ext_subnet.assert_not_called()


class EnsureDualStackOvnLoadBalancerTest(testtools.TestCase):

    @mock.patch.object(_deployers, '_create_dual_stack_ovn_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_creates_when_lb_missing(self, find_lb, create_lb):
        find_lb.return_value = None
        create_lb.return_value = SimpleNamespace(id='new-lb')
        result = _deployers.ensure_dual_stack_ovn_load_balancer(
            'dual-lb', 'ovn', **SUBNETS)
        self.assertEqual(result, create_lb.return_value)
        create_lb.assert_called_once_with('dual-lb', 'ovn', **SUBNETS)

    @mock.patch.object(_client, 'has_dual_stack_vips_on_load_balancer')
    @mock.patch.object(_deployers.octavia, 'get_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_reuses_lb_with_ipv4_and_ipv6_vips(
            self, find_lb, get_lb, has_dual_stack_vips):
        find_lb.return_value = SimpleNamespace(id='lb-1')
        lb = SimpleNamespace(
            id='lb-1', vip_address='2001:db8::1',
            additional_vips=[{'ip_address': '203.0.113.1'}])
        get_lb.return_value = lb
        has_dual_stack_vips.return_value = True
        result = _deployers.ensure_dual_stack_ovn_load_balancer(
            'dual-lb', 'ovn', **SUBNETS)
        self.assertEqual(result, lb)

    @mock.patch.object(_waiters, 'wait_for_dual_stack_vips')
    @mock.patch.object(_client, 'has_dual_stack_vips_on_load_balancer')
    @mock.patch.object(_deployers.octavia, 'get_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_waits_when_existing_lb_has_no_dual_stack_vips_yet(
            self, find_lb, get_lb, has_dual_stack_vips, wait_dual_stack):
        find_lb.return_value = SimpleNamespace(id='lb-1')
        stale_lb = SimpleNamespace(
            id='lb-1',
            additional_vips=None,
            provisioning_status='ACTIVE',
        )
        ready_lb = SimpleNamespace(
            id='lb-1', vip_address='2001:db8::1',
            additional_vips=[{'ip_address': '203.0.113.1'}],
            provisioning_status='ACTIVE')
        get_lb.return_value = stale_lb
        has_dual_stack_vips.return_value = False
        wait_dual_stack.return_value = ready_lb
        result = _deployers.ensure_dual_stack_ovn_load_balancer(
            'dual-lb', 'ovn', **SUBNETS)
        self.assertEqual(result, ready_lb)
        wait_dual_stack.assert_called_once_with('lb-1')

    @mock.patch.object(_deployers, '_create_dual_stack_ovn_load_balancer')
    @mock.patch.object(_waiters, 'wait_for_dual_stack_vips')
    @mock.patch.object(_client, 'has_dual_stack_vips_on_load_balancer')
    @mock.patch.object(_deployers.octavia, 'get_load_balancer')
    @mock.patch.object(_deployers.octavia, 'find_load_balancer')
    def test_fails_when_existing_lb_has_no_dual_stack_vips_after_wait(
            self, find_lb, get_lb, has_dual_stack_vips, wait_dual_stack,
            create_lb):
        find_lb.return_value = SimpleNamespace(id='lb-1')
        stale_lb = SimpleNamespace(
            id='lb-1',
            additional_vips=None,
            provisioning_status='ACTIVE',
        )
        get_lb.return_value = stale_lb
        has_dual_stack_vips.return_value = False
        wait_dual_stack.return_value = None
        ex = self.assertRaises(
            tobiko.FailureException,
            _deployers.ensure_dual_stack_ovn_load_balancer,
            'dual-lb', 'ovn', **SUBNETS)
        self.assertIn('not have both IPv4 and IPv6 VIPs after waiting',
                      str(ex))
        wait_dual_stack.assert_called_once_with('lb-1')
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
