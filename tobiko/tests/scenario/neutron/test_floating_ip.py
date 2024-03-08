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

import typing

from oslo_log import log
import pytest
import testtools

import tobiko
from tobiko import config
from tobiko.shell import files
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.openstack import neutron
from tobiko.openstack import stacks
from tobiko.openstack import topology
from tobiko.tripleo import undercloud


CONF = config.CONF
LOG = log.getLogger(__name__)


@pytest.mark.minimal
class FloatingIPTest(testtools.TestCase):
    """Tests connectivity via floating IPs"""

    #: Resources stack with floating IP and Nova server
    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    def test_ssh(self):
        """Test SSH connectivity to floating IP address"""
        hostname = sh.ssh_hostname(ssh_client=self.stack.ssh_client)
        self.assertEqual(self.stack.server_name.lower(), hostname)

    def test_ping(self):
        """Test ICMP connectivity to floating IP address"""
        ping.assert_reachable_hosts([self.stack.floating_ip_address])

    # --- test port-security extension ---------------------------------------

    @neutron.skip_if_missing_networking_extensions('port-security')
    def test_port_security_enabled_port_attribute(self):
        """Test port security enabled port attribute"""
        self.assertEqual(self.expected_port_security_enabled,
                         self.observed_port_security_enabled)

    @property
    def expected_port_security_enabled(self):
        """Expected port security enabled value"""
        return self.stack.port_security_enabled

    @property
    def observed_port_security_enabled(self):
        """Actual MTU value for internal network"""
        return self.stack.outputs.port_security_enabled

    # --- test security_group extension --------------------------------------

    @neutron.skip_if_missing_networking_extensions('security-group')
    def test_security_groups_port_attribute(self):
        """Test security groups port attribute"""
        self.assertEqual(self.expected_security_groups,
                         self.observed_security_groups)

    @property
    def expected_security_groups(self):
        """Expected port security groups"""
        return set(self.stack.security_groups)

    @property
    def observed_security_groups(self):
        """Actual port security group"""
        return set(self.stack.outputs.security_groups)

    # --- test net-mtu and net-mtu-writable extensions ------------------------

    @ping.skip_if_missing_fragment_ping_option
    @neutron.skip_if_missing_networking_extensions('net-mtu')
    def test_ping_with_net_mtu(self):
        """Test connectivity to floating IP address with MTU sized packets"""
        # Wait until it can reach remote port with maximum-sized packets
        ping.ping(self.stack.floating_ip_address,
                  until=ping.RECEIVED,
                  packet_size=self.observed_net_mtu,
                  fragmentation=False).assert_replied()

        # Verify it can't reach remote port with over-sized packets
        ping.ping(self.stack.floating_ip_address,
                  packet_size=self.observed_net_mtu + 1,
                  fragmentation=False,
                  count=5,
                  check=False).assert_not_replied()

    @property
    def observed_net_mtu(self):
        """Actual MTU value for internal network"""
        network_stack = self.stack.network_stack
        mtu = network_stack.mtu
        if network_stack.has_gateway:
            mtu = min(mtu, network_stack.gateway_stack.mtu)
        return mtu

    # --- test l3_ha extension ------------------------------------------------

    @neutron.skip_unless_is_ovs()
    @neutron.skip_if_missing_networking_extensions('l3-ha')
    def test_l3_ha(self):
        """Test 'mtu' network attribute"""
        gateway = self.stack.network_stack.gateway_details
        self.assertEqual(self.stack.network_stack.ha,
                         gateway['ha'])


# --- Test with port security enabled -----------------------------------------

@neutron.skip_if_missing_networking_extensions('port-security',
                                               'security-group')
class FloatingIPWithPortSecurityFixture(stacks.CirrosServerStackFixture):
    """Heat stack for testing a floating IP instance with port security"""

    #: Resources stack with security group to allow ping Nova servers
    security_groups_stack = tobiko.required_fixture(
        stacks.SecurityGroupsFixture)

    @property
    def security_groups(self) -> typing.List[str]:
        """List with ICMP security group"""
        return [self.security_groups_stack.ssh_security_group_id]


@neutron.skip_if_missing_networking_extensions('port-security',
                                               'security-group')
class FloatingIPWithPortSecurityTest(FloatingIPTest):
    """Tests connectivity via floating IPs with port security"""

    #: Resources stack with floating IP and Nova server with port security
    stack = tobiko.required_fixture(FloatingIPWithPortSecurityFixture)

    def test_ping(self):
        """Test connectivity to floating IP address"""
        # Wait for server instance to get ready by logging in
        self.stack.ssh_client.connect()

        # Expect port security to throw away ICMP packages
        ping.assert_unreachable_hosts([self.stack.floating_ip_address],
                                      count=5, check=False)

    @ping.skip_if_missing_fragment_ping_option
    @neutron.skip_if_missing_networking_extensions('net-mtu')
    def test_ping_with_net_mtu(self):
        """Test connectivity to floating IP address"""
        # Wait for server instance to get ready by logging in
        tobiko.setup_fixture(self.stack.ssh_client)
        self.stack.ssh_client.connect()

        # Verify it can't reach secured port with maximum-sized packets
        ping.ping(self.stack.floating_ip_address,
                  packet_size=self.observed_net_mtu,
                  fragmentation=False,
                  count=5,
                  check=False).assert_not_replied()

        # Verify it can't reach secured port with over-sized packets
        ping.ping(self.stack.floating_ip_address,
                  packet_size=self.observed_net_mtu + 1,
                  fragmentation=False,
                  count=5,
                  check=False).assert_not_replied()


# --- Test with ICMP security group -------------------------------------------

class FloatingIPWithICMPSecurityGroupFixture(
        FloatingIPWithPortSecurityFixture):
    """Heat stack for testing a floating IP instance with security groups"""

    @property
    def security_groups(self):
        """List with ICMP security group"""
        return [self.security_groups_stack.ssh_security_group_id,
                self.security_groups_stack.icmp_security_group_id]


@neutron.skip_if_missing_networking_extensions('port-security',
                                               'security-group')
class FloatingIPWithICMPSecurityGroupTest(FloatingIPTest):
    """Tests connectivity via floating IP with security ICMP security group"""
    #: Resources stack with floating IP and Nova server to ping
    stack = tobiko.required_fixture(
        FloatingIPWithICMPSecurityGroupFixture)


# --- Test net-mtu-write extension --------------------------------------------

@neutron.skip_if_missing_networking_extensions('net-mtu-writable')
class FloatingIPWithNetMtuWritableFixture(stacks.CirrosServerStackFixture):
    """Heat stack for testing floating IP with a custom MTU network value"""

    #: Heat stack for creating internal network with custom MTU value
    network_stack = tobiko.required_fixture(
        stacks.NetworkWithNetMtuWriteStackFixture)


@neutron.skip_if_missing_networking_extensions('net-mtu-writable')
class FloatingIpWithMtuWritableTest(FloatingIPTest):
    """Tests connectivity via floating IP with a custom MTU value"""

    #: Resources stack with floating IP and Nova server
    stack = tobiko.required_fixture(FloatingIPWithNetMtuWritableFixture)

    def test_net_mtu_write(self):
        """Test 'mtu' network attribute"""
        self.assertEqual(self.expected_net_mtu,
                         self.stack.network_stack.mtu)

    @property
    def expected_net_mtu(self):
        """Expected MTU value for internal network"""
        return self.stack.network_stack.custom_mtu_size


# --- Test la-h3 extension ----------------------------------------------------

@neutron.skip_if_missing_networking_extensions('l3-ha')
@neutron.skip_if_missing_networking_agents(binary='neutron-l3-agent',
                                           count=2)
class FloatingIpWithL3HATest(FloatingIPTest):
    #: Resources stack with floating IP and Nova server
    stack = tobiko.required_fixture(stacks.L3haServerStackFixture)


@undercloud.skip_if_missing_undercloud
@topology.skip_unless_osp_version('16.1', higher=True)
class TestFloatingIPLogging(testtools.TestCase):

    stack = tobiko.required_fixture(stacks.NetworkStackFixture)

    def setUp(self):
        super(TestFloatingIPLogging, self).setUp()
        self.port = neutron.create_port(network_id=self.stack.network_id)
        self.fip = neutron.create_floating_ip()
        # TODO(eolivare): adapt the following path to non-tripleo setups and
        # remove the skip_if_missing_undercloud decorator
        log_filename = '/var/log/containers/neutron/server.log'
        self.log_digger = files.MultihostLogFileDigger(filename=log_filename,
                                                       sudo=True)
        for node in topology.list_openstack_nodes(group='controller'):
            self.log_digger.add_host(hostname=node.hostname,
                                     ssh_client=node.ssh_client)

    def test_fip_attach_log(self):
        '''Test log that FIP is attached to VM'''
        pattern = f'{self.fip["id"]}.*associated'
        self.log_digger.find_lines(pattern=pattern)
        neutron.update_floating_ip(
                self.fip['id'], **{'port_id': self.port['id']})
        new_logs = self.log_digger.find_new_lines(pattern=pattern)
        self.assertEqual(len(new_logs), 1)
        self.assertIn(self.port['id'], new_logs[0][1])
        self.assertIn(self.fip['floating_ip_address'], new_logs[0][1])

    def test_fip_detach_log(self):
        '''Test log that FIP is dettached from VM'''
        neutron.update_floating_ip(
                self.fip['id'], **{'port_id': self.port['id']})
        pattern = f'{self.fip["id"]}.*disassociated'
        self.log_digger.find_lines(pattern=pattern)
        neutron.update_floating_ip(self.fip['id'], **{'port_id': None})
        new_logs = self.log_digger.find_new_lines(pattern=pattern)
        self.assertEqual(len(new_logs), 1)
        self.assertIn(self.port['id'], new_logs[0][1])
        self.assertIn(self.fip['floating_ip_address'], new_logs[0][1])

    def test_fip_delete_detach_log(self):
        '''Test log that FIP is dettached from VM if FIP is deleted'''
        neutron.update_floating_ip(
                self.fip['id'], **{'port_id': self.port['id']})
        pattern = f'{self.fip["id"]}.*disassociated'
        self.log_digger.find_lines(pattern=pattern)
        neutron.delete_floating_ip(self.fip['id'])
        new_logs = self.log_digger.find_new_lines(pattern=pattern)
        self.assertEqual(len(new_logs), 1)
        self.assertIn(self.port['id'], new_logs[0][1])
        self.assertIn(self.fip['floating_ip_address'], new_logs[0][1])

    def test_port_delete_fip_detach_log(self):
        '''Test log that FIP is dettached from port if port is deleted'''
        neutron.update_floating_ip(
                self.fip['id'], **{'port_id': self.port['id']})
        pattern = f'{self.fip["id"]}.*disassociated'
        self.log_digger.find_lines(pattern=pattern)
        neutron.delete_port(self.port['id'])
        new_logs = self.log_digger.find_new_lines(pattern=pattern)
        self.assertEqual(len(new_logs), 1)
        self.assertIn(self.port['id'], new_logs[0][1])
        self.assertIn(self.fip['floating_ip_address'], new_logs[0][1])
