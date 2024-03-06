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

import collections
import json
import re
import typing

import pytest
from oslo_log import log
import testtools

import tobiko
from tobiko import config
from tobiko.shell import ping
from tobiko.shell import ip
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import stacks
from tobiko.openstack import topology


LOG = log.getLogger(__name__)
CONF = config.CONF


@pytest.mark.minimal
class RouterTest(testtools.TestCase):
    """Test Neutron routers"""

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    def setUp(self):
        super(RouterTest, self).setUp()
        if not self.stack.network_stack.has_gateway:
            tobiko.skip_test(
                f"Stack {self.stack.network_stack.stack_name} has no gateway")

    @property
    def router(self):
        return self.stack.network_stack.gateway_details

    @property
    def ipv4_subnet_gateway_ip(self):
        if not self.stack.network_stack.has_ipv4:
            tobiko.skip_test(f"Stack {self.stack.network_stack.stack_name} "
                             "has no ipv4 subnet")
        return self.stack.network_stack.ipv4_subnet_gateway_ip

    @property
    def ipv6_subnet_gateway_ip(self):
        if not self.stack.network_stack.has_ipv6:
            tobiko.skip_test(f"Stack {self.stack.network_stack.stack_name} "
                             "has no ipv6 subnet")
        return self.stack.network_stack.ipv6_subnet_gateway_ip

    @property
    def external_gateway_ips(self):
        return self.stack.network_stack.external_gateway_ips

    @property
    def router_ips(self):
        return tobiko.select([self.ipv4_subnet_gateway_ip,
                              self.ipv6_subnet_gateway_ip] +
                             self.external_gateway_ips)

    @tobiko.retry_test_case(interval=30.)
    def test_internal_router_ipv4_interface_is_reachable(self):
        ping.assert_reachable_hosts([self.ipv4_subnet_gateway_ip],
                                    ssh_client=self.stack.ssh_client)

    @tobiko.retry_test_case(interval=30.)
    def test_internal_router_ipv6_interface_is_reachable(self):
        ping.assert_reachable_hosts([self.ipv6_subnet_gateway_ip],
                                    ssh_client=self.stack.ssh_client)

    def test_ipv4_subnet_gateway_ip(self):
        self.assertEqual(4, self.ipv4_subnet_gateway_ip.version)
        self.assertIn(self.ipv4_subnet_gateway_ip,
                      self.stack.network_stack.ipv4_gateway_addresses)

    def test_ipv6_subnet_gateway_ip(self):
        self.assertEqual(6, self.ipv6_subnet_gateway_ip.version)
        self.assertIn(self.ipv6_subnet_gateway_ip,
                      self.stack.network_stack.ipv6_gateway_addresses)

    @pytest.mark.flaky(reruns=3, reruns_delay=60)
    @neutron.skip_if_missing_networking_extensions('l3_agent_scheduler')
    def test_router_is_scheduled_on_l3_agents(self):
        router = self.router
        if router.get('distributed'):
            # TODO(fressi): check whenever a DVR router can be scheduled
            self.skipTest("Router is distributed")
        router_agent = neutron.find_l3_agent_hosting_router(router['id'],
                                                            unique=True)
        self._check_routers_namespace_on_host(router_agent['host'])

    def _check_routers_namespace_on_host(self, hostname, state="master"):
        namespace_ips = self._get_router_ips_from_namespaces(hostname)
        missing_ips = set(self.router_ips) - set(namespace_ips)
        if state == "master":
            self.assertFalse(missing_ips)
        else:
            self.assertTrue(missing_ips)

    def _get_router_ips_from_namespaces(self, hostname):
        agent_host = topology.get_openstack_node(hostname=hostname)
        router_namespaces = ["qrouter-%s" % self.router['id']]
        if self.router.get('distributed'):
            router_namespaces.append("snat-%s" % self.router['id'])
        host_namespaces = ip.list_network_namespaces(
            ssh_client=agent_host.ssh_client)
        ips = []
        for router_namespace in router_namespaces:
            self.assertIn(router_namespace, host_namespaces)
            ips += ip.list_ip_addresses(
                scope='global', network_namespace=router_namespace,
                ssh_client=agent_host.ssh_client)
        return ips


@neutron.skip_if_missing_networking_extensions('l3-ha')
@neutron.skip_if_missing_networking_agents(binary='neutron-l3-agent',
                                           count=2)
class L3HARouterTest(RouterTest):
    """Test Neutron HA routers"""

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.L3haServerStackFixture)

    @neutron.skip_if_missing_networking_extensions('l3_agent_scheduler')
    def test_router_is_scheduled_on_l3_agents(self):
        master_agent, backup_agents = (
            neutron.wait_for_master_and_backup_agents(self.router['id']))
        self.assertGreaterEqual(len(backup_agents), 1)
        self._check_routers_namespace_on_host(master_agent['host'])
        for backup_agent in backup_agents:
            self._check_routers_namespace_on_host(
                backup_agent['host'], state="backup")


class RouterNamespaceTestBase:

    server_stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    host_groups = ['overcloud', 'compute', 'controller']

    @property
    def hostnames(self) -> typing.List[str]:
        return sorted(
            node.hostname
            for node in topology.list_openstack_nodes(group=self.host_groups))

    @property
    def router_stack(self) -> stacks.RouterStackFixture:
        return self.network_stack.gateway_stack

    @property
    def network_stack(self) -> stacks.NetworkBaseStackFixture:
        return self.server_stack.network_stack

    @property
    def router_id(self) -> str:
        return self.router_stack.router_id

    @property
    def router_details(self) -> neutron.RouterType:
        return self.router_stack.router_details

    @property
    def router_namespace(self) -> str:
        return neutron.get_ovs_router_namespace(self.router_id)


@neutron.skip_unless_is_ovs()
class OvsRouterNamespaceTest(RouterNamespaceTestBase, testtools.TestCase):

    def test_router_namespace(self):
        """Check router namespace is being created on cloud hosts

        When A VM running in a compute node is expected to route
        packages to a router, a network namespace is expected to exist on
        compute name that is named after the router ID
        """
        ping.assert_reachable_hosts([self.server_stack.floating_ip_address])
        topology.assert_namespace_in_hosts(self.router_namespace,
                                           hostnames=self.hostnames)


@neutron.skip_if_missing_networking_extensions('dvr')
class DvrRouterStackFixture(stacks.RouterStackFixture):
    distributed = True


class DvrNetworkStackFixture(stacks.NetworkBaseStackFixture):
    gateway_stack = tobiko.required_fixture(DvrRouterStackFixture,
                                            setup=False)

    @tobiko.interworker_synched('create_dvr_network_stack')
    def setup_stack(self):
        super().setup_stack()


class DvrServerStackFixture(stacks.CirrosServerStackFixture):
    network_stack = tobiko.required_fixture(DvrNetworkStackFixture,
                                            setup=False)


L3_AGENT_MODE_DVR = re.compile(r'^dvr_')


def is_l3_agent_mode_dvr(agent_mode: str) -> bool:
    return L3_AGENT_MODE_DVR.match(agent_mode) is not None


@neutron.skip_if_missing_networking_extensions('dvr')
class DvrRouterNamespaceTest(RouterNamespaceTestBase, testtools.TestCase):

    server_stack = tobiko.required_fixture(DvrServerStackFixture, setup=False)

    def setUp(self):
        super().setUp()
        if self.legacy_hostnames:
            self.skipTest(f'Host(s) {self.legacy_hostnames!r} with legacy '
                          'L3 agent mode')

    host_groups = ['compute']

    @property
    def snat_namespace(self) -> str:
        return f'snat-{self.router_id}'

    _agent_modes: typing.Optional[typing.Dict[str, typing.List[str]]] = None

    @property
    def agent_modes(self) \
            -> typing.Dict[str, typing.List[str]]:
        if self._agent_modes is None:
            self._agent_modes = collections.defaultdict(list)
            for node in topology.list_openstack_nodes(
                    hostnames=self.hostnames):
                self._agent_modes[node.l3_agent_mode].append(node.name)
            agent_modes_dump = json.dumps(self._agent_modes,
                                          indent=4, sort_keys=True)
            LOG.info(f"Got L3 agent modes:\n{agent_modes_dump}")
        return self._agent_modes

    @property
    def legacy_hostnames(self) -> typing.List[str]:
        return self.agent_modes['legacy']

    @property
    def dvr_hostnames(self) -> typing.List[str]:
        return self.agent_modes['dvr'] + self.agent_modes['dvr_no_external']

    @property
    def dvr_snat_hostnames(self) -> typing.List[str]:
        return self.agent_modes['dvr_snat']

    @config.skip_if_prevent_create()
    def test_1_dvr_router_without_server(self):
        if self.dvr_hostnames:
            self.cleanup_stacks()
            self.setup_router()
            topology.assert_namespace_not_in_hosts(
                self.router_namespace,
                self.snat_namespace,
                hostnames=self.dvr_hostnames)
        else:
            self.skipTest(f'All hosts {self.hostnames!r} have '
                          'dvr_snat L3 agent mode')

    def test_2_dvr_snat_router_namespaces(self):
        if self.dvr_snat_hostnames:
            self.setup_router()
            topology.wait_for_namespace_in_hosts(
                self.router_namespace,
                self.snat_namespace,
                hostnames=self.dvr_snat_hostnames)
        else:
            self.skipTest(f'Any host {self.hostnames!r} has '
                          'dvr_snat L3 agent mode')

    def test_3_dvr_router_namespace_with_server(self):
        self.setup_server()
        self.wait_for_namespace_in_hypervisor_host()

    def wait_for_namespace_in_hypervisor_host(self):
        hypervisor_hostname = self.server_stack.hypervisor_hostname
        agent_mode = topology.get_l3_agent_mode(hostname=hypervisor_hostname)
        LOG.info(f"Hypervisor host '{hypervisor_hostname}' has DVR agent "
                 f"mode: '{agent_mode}'")
        topology.wait_for_namespace_in_hosts(self.router_namespace,
                                             hostnames=[hypervisor_hostname])

    def test_4_server_is_reachable(self):
        self.setup_server()
        try:
            self.server_stack.assert_is_reachable()
        except ping.PingFailed:
            server_id = self.server_stack.server_id
            server_log = nova.get_console_output(server_id=server_id)
            LOG.exception(f"Unable to reach server {server_id}...\n"
                          f"{server_log}\n")
            self.wait_for_namespace_in_hypervisor_host()
            nova.reboot_server(server=server_id)
            self.server_stack.assert_is_reachable()

    def cleanup_stacks(self):
        for stack in [self.server_stack,
                      self.network_stack,
                      self.router_stack]:
            tobiko.cleanup_fixture(stack)

    def setup_router(self):
        router = tobiko.setup_fixture(self.router_stack).router_details
        router_dump = json.dumps(router, indent=4, sort_keys=True)
        LOG.debug(f"Testing DVR router namespace: {router['id']}:\n"
                  f"{router_dump}\n")
        self.assertTrue(router['distributed'])

    def setup_network(self):
        self.setup_router()
        tobiko.setup_fixture(self.network_stack)

    def setup_server(self):
        self.setup_network()
        tobiko.setup_fixture(self.server_stack)
