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

from tobiko.rhosp import _topology
from tobiko.tests.unit import _case


class TestIpToHostname(_case.TobikoUnitTest):
    """Tests for ip_to_hostname function.

    The ip_to_hostname function needs to handle IPv6 addresses in different
    formats (canonical/shortened vs full/expanded) and normalize them before
    dictionary lookup.
    """

    def setUp(self):
        super().setUp()
        # Mock get_ip_to_nodes_dict to return a controlled dictionary
        # Keys use canonical IPv6 format (as produced by netaddr.IPAddress)
        self.mock_ip_dict = {
            '192.168.1.1': 'compute-0',
            '10.0.0.1': 'controller-0',
            # Canonical/shortened IPv6 format
            '2620:cf:cf:aaaa::64': 'edpm-compute-0',
            '2620:cf:cf:bbbb::65': 'edpm-compute-1',
        }
        self.mock_get_dict = mock.patch.object(
            _topology, 'get_ip_to_nodes_dict',
            return_value=self.mock_ip_dict
        )
        self.mock_get_dict.start()
        self.addCleanup(self.mock_get_dict.stop)

    def test_ipv4_address(self):
        """Test that IPv4 addresses are looked up correctly."""
        result = _topology.ip_to_hostname('192.168.1.1')
        self.assertEqual('compute-0', result)

    def test_ipv4_address_different_host(self):
        """Test that different IPv4 addresses return different hosts."""
        result = _topology.ip_to_hostname('10.0.0.1')
        self.assertEqual('controller-0', result)

    def test_ipv6_canonical_format(self):
        """Test IPv6 address in canonical/shortened format."""
        result = _topology.ip_to_hostname('2620:cf:cf:aaaa::64')
        self.assertEqual('edpm-compute-0', result)

    def test_ipv6_full_expanded_format(self):
        """Test IPv6 address in full expanded format with leading zeros.

        This is the main bug fix test case. The IPv6 address is provided in
        full expanded format (e.g., from EDPM nodeset YAML), but the dictionary
        keys use canonical format. The function should normalize the address.
        """
        # Full expanded format with leading zeros
        result = _topology.ip_to_hostname(
            '2620:00cf:00cf:aaaa:0000:0000:0000:0064')
        self.assertEqual('edpm-compute-0', result)

    def test_ipv6_mixed_format(self):
        """Test IPv6 address with some leading zeros."""
        # Mixed format - some segments with leading zeros
        result = _topology.ip_to_hostname('2620:00cf:00cf:bbbb::65')
        self.assertEqual('edpm-compute-1', result)

    def test_ipv6_modified_format_with_dots(self):
        """Test IPv6 address with dots instead of colons.

        Some systems store IPv6 addresses with dots instead of colons.
        The function should handle this by replacing dots with colons
        and normalizing.
        """
        # Modified format: dots instead of colons, full expanded
        result = _topology.ip_to_hostname(
            '2620.00cf.00cf.aaaa.0000.0000.0000.0064')
        self.assertEqual('edpm-compute-0', result)

    def test_ipv6_modified_format_with_dots_canonical(self):
        """Test modified IPv6 format that's already canonical after dots."""
        # This format would be canonical after replacing dots with colons
        # Note: this format may not be commonly used in practice
        result = _topology.ip_to_hostname(
            '2620.00cf.00cf.bbbb.0000.0000.0000.0065')
        self.assertEqual('edpm-compute-1', result)

    def test_invalid_ip_raises_error(self):
        """Test that invalid IP addresses cause a failure."""
        self.assertRaises(
            Exception,
            _topology.ip_to_hostname,
            'not-an-ip-address'
        )
