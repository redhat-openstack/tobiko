# Copyright (c) 2021 Red Hat
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

from oslo_log import log
import pytest
import testtools

import tobiko
from tobiko import config
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import stacks
from tobiko.shell import ip


CONF = config.CONF
LOG = log.getLogger(__name__)


class RebootTrunkServerStackFixture(stacks.AdvancedServerStackFixture):

    def validate_created_stack(self):
        # (fressi) must wait cloud init to complete Nova
        # server setup before shutting it down so that we ensure all
        # network devices gets persistent after reboots
        stack = super().validate_created_stack()
        nova.activate_server(server=self.server_id)
        self.wait_for_cloud_init_done()
        return stack


@neutron.skip_if_missing_networking_extensions('trunk')
class RebootTrunkTest(testtools.TestCase):
    """Tests trunk functionality"""

    stack = tobiko.required_fixture(RebootTrunkServerStackFixture)

    def test_0_vlan_ip_addresses(self):
        """Check Nova server VLAN port IP addresses"""
        self.stack.ensure_server_status('ACTIVE')
        expected = set(self.stack.list_vlan_fixed_ips())
        for attempt in tobiko.retry(timeout=300, interval=10):
            actual = set(ip.list_ip_addresses(device=self.stack.vlan_device,
                                              ssh_client=self.stack.ssh_client,
                                              scope='global'))
            unexpected = actual - expected
            if unexpected:
                self.fail("Unexpected IP address assigned to VLAN port: "
                          f"{unexpected}")

            missing = expected - actual
            if missing:
                if attempt.is_last:
                    self.fail("IP addresses not assigned to VLAN port: "
                              f"{missing}")
                else:
                    LOG.debug("IP addresses still not assigned to VLAN port: "
                              f"{missing}")
            else:
                break
        else:
            raise RuntimeError("Broken retry loop")
        self.assertEqual(set(expected), set(actual))

    def test_1_ping_vlan_port(self):
        """Check Nova server VLAN port is reachable"""
        self.stack.ensure_server_status('ACTIVE')
        self.stack.assert_vlan_is_reachable()

    @pytest.mark.ovn_migration
    def test_2_ping_vlan_port_after_restart(self):
        """Check Nova server VLAN port is reachable after hard restart"""
        self.stack.ensure_server_status('SHUTOFF')
        self.stack.assert_vlan_is_unreachable()

        self.stack.ensure_server_status('ACTIVE')
        self.stack.assert_vlan_is_reachable()
