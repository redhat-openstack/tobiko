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
