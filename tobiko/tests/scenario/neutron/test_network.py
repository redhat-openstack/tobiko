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
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.tripleo import undercloud
from tobiko.tripleo import nova as tripleo_nova


@pytest.mark.minimal
class NetworkTest(testtools.TestCase):

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosPeerServerStackFixture)

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
@undercloud.skip_if_missing_undercloud
class BackgroundProcessTest(NetworkTest):

    def test_check_background_vm_ping(self):
        """ Tests that are designed to run in the background ,
            then collect results.
            Logic: checks if process exists, if so stop the process,
            then execute some check logic i.e. a check function.
            if the process by name isn't running,
            start a separate process i.e a background function"""
        tripleo_nova.check_or_start_background_vm_ping()


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
