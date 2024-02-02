# Copyright (c) 2019 Red Hat
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

import json
import re
import typing

import netaddr
import pytest
from neutron_lib import constants
from oslo_log import log
import testtools

import tobiko
from tobiko.shell import ping
from tobiko.shell import ip
from tobiko.shell import sh
from tobiko.openstack import neutron
from tobiko.openstack.neutron import neutron_log_reader
from tobiko.openstack import stacks
from tobiko.openstack import topology
from tobiko.tripleo import overcloud


LOG = log.getLogger(__name__)
IPV4 = constants.IP_VERSION_4
IPV6 = constants.IP_VERSION_6


@pytest.mark.minimal
class PortTest(testtools.TestCase):
    """Test Neutron ports"""

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    def test_port_ips(self, ip_version: typing.Optional[int] = None):
        """Checks port IPS has been assigned to server via DHCP protocol"""
        port_ips = set(neutron.list_device_ip_addresses(
            device=self.stack.server_id,
            network=self.stack.network_stack.network_id,
            need_dhcp=self.stack.need_dhcp,
            ip_version=ip_version))
        if port_ips:
            # verify neutron port IPs and VM port IPs match
            # when a VM connected to the external network has been just
            # created, it may need some time to receive its IPv6 address
            for attempt in tobiko.retry(timeout=60., interval=4.):
                server_ips = set(ip.list_ip_addresses(
                    scope='global', ssh_client=self.stack.ssh_client))
                server_ips &= port_ips  # ignore other server IPs
                LOG.debug("Neutron IPs and VM IPs should match...")
                try:
                    self.assertEqual(
                        port_ips, server_ips,
                        f"Server {self.stack.server_id} is missing port "
                        f"IP(s): {port_ips - server_ips}")
                    break
                except self.failureException:
                    attempt.check_limits()
        elif ip_version:
            self.skipTest(f"Server has any port IPv{ip_version} address to be"
                          " tested")
        else:
            self.skipTest("Server has any port IP address to be tested")

    def test_port_network(self):
        self.assertEqual(self.stack.network_stack.network_id,
                         self.stack.port_details['network_id'])

    def test_port_subnets(self):
        """Checks port subnets"""
        port_subnets = [fixed_ip['subnet_id']
                        for fixed_ip in self.stack.port_details['fixed_ips']]
        network_subnets = self.stack.network_stack.network_details['subnets']
        self.assertEqual(set(network_subnets), set(port_subnets))

    def test_ping_subnet_gateways(self):
        """Checks server can ping its gateway IPs"""
        network_id = self.stack.network_stack.network_id
        subnets = neutron.list_subnets(network_id=network_id)
        LOG.debug("Subnets enabled are:\n"
                  f"{json.dumps(subnets, indent=4, sort_keys=True)}")
        gateway_ips = [netaddr.IPAddress(subnet['gateway_ip'])
                       for subnet in subnets]
        LOG.debug(f"Gateway IPs are: {gateway_ips}")
        ping.assert_reachable_hosts(gateway_ips,
                                    ssh_client=self.stack.ssh_client)

    def test_ping_port(self, network_id=None, device_id=None, ip_version=None):
        """Checks server can ping its own port"""
        port_ips = neutron.list_device_ip_addresses(
            device=device_id or self.stack.server_id,
            network=network_id or self.stack.network_stack.network_id,
            need_dhcp=self.stack.need_dhcp,
            ip_version=ip_version)
        if port_ips:
            ping.assert_reachable_hosts(port_ips,
                                        timeout=600.,
                                        ssh_client=self.stack.peer_ssh_client)
        elif ip_version:
            self.skipTest(f"Server has any port IPv{ip_version} address to be"
                          " tested")
        else:
            self.skipTest("Server has any port IP address to be tested")


# --- Test opening ports on external network ----------------------------------

@stacks.skip_unless_has_external_network
class UbuntuExternalPortTest(PortTest):
    """Test Neutron ports"""

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(
        stacks.UbuntuExternalServerStackFixture)


# --- Test la-h3 extension ----------------------------------------------------

@neutron.skip_if_missing_networking_extensions('l3-ha')
@neutron.skip_if_missing_networking_agents(binary='neutron-l3-agent',
                                           count=2)
class L3HAPortTest(PortTest):
    #: Resources stack with floating IP and Nova server
    stack = tobiko.required_fixture(stacks.L3haServerStackFixture)


class ExtraDhcpOptsPortTest(PortTest):
    """Test extra-dhcp-options port parameter"""
    stack = tobiko.required_fixture(
        stacks.ExtraDhcpOptsCirrosServerStackFixture)

    def test_extra_dhcp_opts(self):
        port = neutron.get_port(self.stack.port_id)
        for option in port['extra_dhcp_opts']:
            if 'domain-name' == option['opt_name']:
                domain = option['opt_value'].replace('"', '')
                break
        else:
            tobiko.fail('No extra-dhcp-opt found for domain-name')

        vm_resolv_conf = sh.execute('cat /etc/resolv.conf',
                                    ssh_client=self.stack.ssh_client).stdout
        self.assertIsNotNone(
            re.search(r'^search\s+{domain}$'.format(domain=domain),
                      vm_resolv_conf,
                      re.MULTILINE))


@overcloud.skip_unless_ovn_bgp_agent
class NoFipPortTest(ExtraDhcpOptsPortTest):
    stack = tobiko.required_fixture(stacks.CirrosNoFipServerStackFixture)

    def setUp(self):
        super().setUp()

        try:
            node = topology.find_openstack_node(group='networker')
        except topology.NoSuchOpenStackTopologyNodeGroup:
            node = topology.find_openstack_node(group='controller')
        expose_tenant_networks = topology.get_config_setting(
            'bgp-agent.conf', node.ssh_client, 'expose_tenant_networks')
        if expose_tenant_networks is None or (
                expose_tenant_networks.lower() != 'true'):
            tobiko.skip_test('BGP expose_tenant_networks is disabled')


@neutron.skip_unless_is_ovn()
class ExtraDhcpOptsPortLoggingTest(testtools.TestCase):

    stack = tobiko.required_fixture(stacks.NetworkStackFixture)

    def test_extra_dhcp_opts_logs_unsupported_options(self):
        # initialize logs that match the pattern
        neutron_log_reader.assert_ovn_unsupported_dhcp_option_messages()

        wrong_ipv4_option = 'wrong-ipv4-option'
        wrong_ipv6_option = 'bananas'
        a_valid_ipv4_option_used_for_ipv6 = 'log-server'
        extra_dhcp_opts = [
            {'opt_value': '1.1.1.1',
             'opt_name': a_valid_ipv4_option_used_for_ipv6,
             'ip_version': IPV6},
            {'opt_value': 'ipv6.domain',
             'opt_name': 'domain-search',
             'ip_version': IPV6},
            {'opt_value': '1600',
             'opt_name': 'mtu',
             'ip_version': IPV4},
            {'opt_value': 'blablabla',
             'opt_name': wrong_ipv4_option,
             'ip_version': IPV4}]
        # create port with extra-dhcp-opts
        port = neutron.create_port(**{'network_id': self.stack.network_id,
                                      'extra_dhcp_opts': extra_dhcp_opts})
        self.addCleanup(neutron.delete_port, port['id'])
        # find new logs that match the pattern
        invalid_options = [wrong_ipv4_option,
                           a_valid_ipv4_option_used_for_ipv6]
        # assert every invalid dhcp option is logged
        neutron_log_reader.assert_ovn_unsupported_dhcp_option_messages(
            unsupported_options=invalid_options,
            port_uuid=port['id'])

        extra_dhcp_opts.append({'opt_value': '1.1.1.1',
                                'opt_name': wrong_ipv6_option,
                                'ip_version': IPV6})
        # update port with new extra-dhcp-opts
        port = neutron.update_port(port['id'],
                                   **{'extra_dhcp_opts': extra_dhcp_opts})
        invalid_options.append(wrong_ipv6_option)
        # assert every invalid dhcp option is logged
        neutron_log_reader.assert_ovn_unsupported_dhcp_option_messages(
            unsupported_options=invalid_options,
            port_uuid=port['id'])
