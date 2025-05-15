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

import pytest
import testtools

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import stacks
from tobiko.openstack import topology
from tobiko.shell import ping
from tobiko.shell import sh


class BaseNetworkTest(testtools.TestCase):

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosPeerServerStackFixture)


@pytest.mark.minimal
class NetworkTest(BaseNetworkTest):

    def test_stack_create_complete(self):
        self.stack.key_pair_stack.wait_for_create_complete()
        self.stack.network_stack.wait_for_create_complete()
        self.stack.peer_stack.wait_for_create_complete()
        self.stack.wait_for_create_complete()

    def test_ssh(self):
        """Test TCP connectivity to SSH server from VM to VM"""
        hostname = sh.ssh_hostname(ssh_client=self.stack.ssh_client)
        self.assertEqual(self.stack.server_name.lower(), hostname)

    def test_ping(self):
        """Test ICMP connectivity to from VM to VM"""
        ping.assert_reachable_hosts(
            [self.stack.ip_address],
            ssh_client=self.stack.peer_stack.ssh_client)

    # --- test l3_ha extension ------------------------------------------------

    @neutron.skip_unless_is_ovs()
    @neutron.skip_if_missing_networking_extensions('l3-ha')
    def test_l3_ha(self):
        """Test l3-ha network attribute"""
        gateway = self.stack.network_stack.gateway_details
        self.assertEqual(self.stack.network_stack.ha,
                         gateway['ha'])


@pytest.mark.background
class BackgroundProcessTest(BaseNetworkTest):
    """Test designed to run in the background,
    then collect results.
    Logic: checks if process exists, if so stop the process,
    then execute some check logic i.e. a check function.
    if the process by name isn't running,
    start a separate process i.e a background function"""

    stack = tobiko.required_fixture(stacks.AdvancedPeerServerStackFixture)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.topology = topology.get_openstack_topology()
        if not cls.topology.background_tests_supported:
            tobiko.skip_test(
                'Background tests not supported by this topology class.')

    def test_check_background_vm_ping(self):
        """Ping from test machine/container/pod to VM with FIP,
        validating north-south connectivity with SDNAT (source-destination
        NAT)."""
        self.topology.check_or_start_background_vm_ping(
            self.stack.peer_stack.floating_ip_address)

    def test_check_background_vm_ping_snat(self):
        """Ping from a VM without FIP to an external IP,
        validating north-south connectivity with SNAT (source NAT)."""
        # make sure the VM does not have any FIP
        self.assertFalse(self.stack.has_floating_ip)

        try:
            ext_subnet = neutron.list_subnets(
                network=self.stack.network_stack.gateway_network_id,
                ip_version=4)[0]
        except IndexError:
            ext_subnet = neutron.list_subnets(
                network=self.stack.network_stack.gateway_network_id,
                ip_version=6)[0]

        self.topology.check_or_start_background_vm_ping(
            ext_subnet['gateway_ip'],
            ssh_client=self.stack.ssh_client)

    def test_check_background_vm_ping_east_west(self):
        """Pings between VMs conected to the same tenant network,
        validating east-west connectivity."""
        self.topology.check_or_start_background_vm_ping(
            self.stack.fixed_ipv4,
            ssh_client=self.stack.peer_stack.ssh_client)

    def test_east_west_tcp_traffic_background_iperf(self):
        """ Test East-West TCP traffic in the existing flow.

        This test is intended to test TCP traffic with bigger amount of
        data send between two VMs connected to the same tenant network.
        Traffic is send in the single flow using "iperf" tool.
        """

        self.topology.check_or_start_background_iperf_connection(
                self.stack.fixed_ipv4,
                port=5203,
                protocol='tcp',
                ssh_client=self.stack.peer_stack.ssh_client,
                iperf3_server_ssh_client=self.stack.ssh_client)

    def test_north_south_tcp_traffic_background_iperf(self):
        """ Test North-South TCP traffic in the existing flow.

        This test is intended to test TCP traffic with bigger amount of
        data send VM with Floating IP and external world.
        Traffic is send in the single flow using "iperf" tool.
        """

        self.topology.check_or_start_background_iperf_connection(
                self.stack.peer_stack.floating_ip_address,
                port=5204,
                protocol='tcp',
                iperf3_server_ssh_client=self.stack.peer_stack.ssh_client)

    def test_north_south_tcp_new_connections(self):
        self.topology.check_or_start_background_http_ping(
            self.stack.peer_stack.floating_ip_address)

    def test_east_west_tcp_new_connections(self):
        self.topology.check_or_start_background_http_ping(
            self.stack.fixed_ipv4,
            ssh_client=self.stack.peer_stack.ssh_client)


@pytest.mark.migrate_server
class SameHostNetworkTest(NetworkTest):

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(
        stacks.CirrosSameHostServerStackFixture)

    def test_same_host(self):
        sender = self.stack.peer_stack.server_details
        receiver = self.stack.server_details
        self.assertEqual({'same_host': [sender.id]},
                         self.stack.scheduler_hints)
        self.assertEqual(nova.get_server_hypervisor(sender),
                         nova.get_server_hypervisor(receiver))


@pytest.mark.migrate_server
@nova.skip_if_missing_hypervisors(count=2, state='up', status='enabled')
class DifferentHostNetworkTest(NetworkTest):

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(
        stacks.CirrosDifferentHostServerStackFixture)

    def test_different_host(self):
        sender = self.stack.peer_stack.server_details
        receiver = self.stack.server_details
        self.assertEqual({'different_host': [sender.id]},
                         self.stack.scheduler_hints)
        self.assertNotEqual(nova.get_server_hypervisor(sender),
                            nova.get_server_hypervisor(receiver))


# --- l3-ha extension VM to VM scenario ---------------------------------------

@neutron.skip_if_missing_networking_extensions('l3-ha')
@neutron.skip_if_missing_networking_agents(binary='neutron-l3-agent',
                                           count=2)
class L3haNetworkTest(NetworkTest):
    #: Resources stack with floating IP and Nova server
    stack = tobiko.required_fixture(stacks.L3haPeerServerStackFixture)


@neutron.skip_if_missing_networking_extensions('l3-ha')
@neutron.skip_if_missing_networking_agents(binary='neutron-l3-agent',
                                           count=2)
class L3haSameHostNetworkTest(SameHostNetworkTest):
    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(
        stacks.L3haSameHostServerStackFixture)


@neutron.skip_if_missing_networking_extensions('l3-ha')
@neutron.skip_if_missing_networking_agents(binary='neutron-l3-agent',
                                           count=2)
@nova.skip_if_missing_hypervisors(count=2, state='up', status='enabled')
class L3haDifferentHostNetworkTest(DifferentHostNetworkTest):
    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(
        stacks.L3haDifferentHostServerStackFixture)
