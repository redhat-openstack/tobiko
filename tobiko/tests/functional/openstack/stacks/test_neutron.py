# Copyright (c) 2019 Red Hat, Inc.
#
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
import testtools

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import stacks


LOG = log.getLogger(__name__)


@keystone.skip_unless_has_keystone_credentials()
class NetworkTest(testtools.TestCase):
    """Tests network creation"""

    #: Stack of resources with a network with a gateway router
    stack = tobiko.required_fixture(stacks.NetworkStackFixture)

    @neutron.skip_if_missing_networking_extensions('port-security')
    def test_port_security_enabled(self):
        self.assertEqual(self.stack.port_security_enabled,
                         self.stack.network_details['port_security_enabled'])
        self.assertEqual(self.stack.port_security_enabled,
                         self.stack.outputs.port_security_enabled)

    @neutron.skip_if_missing_networking_extensions('net-mtu')
    def test_net_mtu(self):
        self.assertEqual(self.stack.network_details['mtu'],
                         self.stack.outputs.mtu)

    def test_ipv4_subnet_cidr(self):
        if not self.stack.has_ipv4:
            tobiko.skip_test(f"Stack {self.stack.stack_name} has no ipv4 "
                             "subnet")

        subnet = neutron.find_subnet(cidr=str(self.stack.ipv4_subnet_cidr))
        self.assertEqual(neutron.get_subnet(self.stack.ipv4_subnet_id), subnet)

    def test_ipv6_subnet_cidr(self):
        if not self.stack.has_ipv6:
            tobiko.skip_test(f"Stack {self.stack.stack_name} has no ipv6 "
                             "subnet")
        subnet = neutron.find_subnet(cidr=str(self.stack.ipv6_subnet_cidr))
        self.assertEqual(neutron.get_subnet(self.stack.ipv6_subnet_id), subnet)

    def test_gateway_network(self):
        if not self.stack.has_gateway:
            tobiko.skip_test(f"Stack {self.stack.stack_name} has no gateway")
        self.assertEqual(
            self.stack.gateway_network_id,
            self.stack.gateway_details['external_gateway_info']['network_id'])

    def test_ipv4_subnet_gateway_ip(self):
        if not self.stack.has_ipv4 or not self.stack.has_gateway:
            tobiko.skip_test(f"Stack {self.stack.stack_name} has no IPv4 "
                             "gateway")
        self.assertIn(
            self.stack.ipv4_subnet_gateway_ip,
            self.stack.ipv4_gateway_addresses)

    def test_ipv6_subnet_gateway_ip(self):
        if not self.stack.has_ipv6 or not self.stack.has_gateway:
            tobiko.skip_test(f"Stack {self.stack.stack_name} has no IPv6 "
                             "gateway")
        self.assertIn(
            self.stack.ipv6_subnet_gateway_ip,
            self.stack.ipv6_gateway_addresses)


@keystone.skip_unless_has_keystone_credentials()
@neutron.skip_if_missing_networking_extensions('net-mtu-write')
class NetworkWithNetMtuWriteTest(NetworkTest):

    #: Stack of resources with a network with a gateway router
    stack = tobiko.required_fixture(
        stacks.NetworkWithNetMtuWriteStackFixture)

    def test_net_mtu_write(self):
        self.assertEqual(self.stack.mtu, self.stack.outputs.mtu)


@keystone.skip_unless_has_keystone_credentials()
@neutron.skip_if_missing_networking_extensions('l3-ha')
@neutron.skip_if_missing_networking_agents(neutron.L3_AGENT, 2)
class L3HaNetworkTest(NetworkTest):

    #: Stack of resources with a network with a gateway router
    stack = tobiko.required_fixture(stacks.L3haNetworkStackFixture)


@keystone.skip_unless_has_keystone_credentials()
@stacks.skip_unless_has_external_network
class ExternalNetworkTest(testtools.TestCase):

    def test_get_external_network(self):
        network = stacks.get_external_network()
        self.assertTrue(network['id'])
        self.assertIs(True, network['router:external'])
        self.assertEqual('ACTIVE', network['status'])
        subnets = neutron.list_subnets(network_id=network['id'])
        self.assertNotEqual([], subnets)

    def test_has_external_network(self):
        self.assertIs(True, stacks.has_external_network())


@keystone.skip_unless_has_keystone_credentials()
@stacks.skip_unless_has_floating_network
class RouterTest(testtools.TestCase):

    def test_get_floating_network(self):
        network = stacks.get_floating_network()
        self.assertTrue(network['id'])
        self.assertIs(True, network['router:external'])
        self.assertEqual('ACTIVE', network['status'])

    def test_has_floating_network(self):
        self.assertTrue(stacks.has_floating_network())

    def test_get_router(self):
        router = stacks.get_router()
        self.assertIsNotNone(router)
        self.assertEqual(
            stacks.get_floating_network_id(),
            router['external_gateway_info']['network_id'])

    def test_has_router(self):
        self.assertTrue(stacks.has_router())


class RouterInterfaceTestRouter(stacks.RouterStackFixture):
    pass


class RouterInterfaceTestNetwork(stacks.NetworkBaseStackFixture):
    @tobiko.interworker_synched('create_router_interface_network_stack')
    def setup_stack(self):
        super().setup_stack()


@keystone.skip_unless_has_keystone_credentials()
@stacks.skip_unless_has_floating_network
class RouterInterfaceTest(testtools.TestCase):

    router_stack = tobiko.required_fixture(RouterInterfaceTestRouter)
    network_stack = tobiko.required_fixture(RouterInterfaceTestNetwork)

    required_fixtures = [router_stack, network_stack]

    subnet_index = 201

    @classmethod
    def tearDownClass(cls) -> None:
        for fixture in cls.required_fixtures:
            try:
                tobiko.cleanup_fixture(fixture.fixture)
            except Exception:
                LOG.exception(f'Error cleaning up fixture: {fixture.fixture}')

    def _get_subnet_pool(self, ip_version=4):
        if ip_version == 4:
            subnet_pool_range = f"172.168.{self.subnet_index}.0/24"
            subnet_pool_default_prefixlen = 26
        elif ip_version == 6:
            subnet_pool_range = f"2003:{self.subnet_index}::/64"
            subnet_pool_default_prefixlen = 68
        else:
            raise ValueError

        subnet_pool = neutron.create_subnet_pool(
            name=self.id(),
            prefixes=[subnet_pool_range],
            default_prefixlen=subnet_pool_default_prefixlen)

        self.subnet_index += 1
        return subnet_pool

    def test_ensure_router_interface_with_subnet(self,
                                                 ip_version=4):
        network = neutron.create_network()
        subnet_pool = self._get_subnet_pool(ip_version)
        subnet = neutron.create_subnet(network=network,
                                       subnetpool_id=subnet_pool['id'],
                                       ip_version=ip_version)
        self._test_ensure_router(subnet=subnet)

    def test_ensure_router_interface_with_ipv6_subnet(self):
        self.test_ensure_router_interface_with_subnet(ip_version=6)

    def test_ensure_router_interface_with_routed_ipv4_subnet(self):
        self._test_ensure_router(subnet=self.network_stack.ipv4_subnet_id)

    def test_ensure_router_interface_with_routed_ipv6_subnet(self):
        self._test_ensure_router(subnet=self.network_stack.ipv6_subnet_id)

    def test_ensure_router_interface_with_network(self):
        network = neutron.create_network()
        subnet_pool = self._get_subnet_pool()
        neutron.create_subnet(network=network, subnetpool_id=subnet_pool['id'])
        self._test_ensure_router(network=network)

    def test_ensure_router_interface_with_routed_network(self):
        self._test_ensure_router(network=self.network_stack.network_id)

    def _test_ensure_router(self,
                            network: neutron.NetworkIdType = None,
                            subnet: neutron.SubnetIdType = None):
        router = self.router_stack.router_details
        self.assertRaises(tobiko.ObjectNotFound,
                          neutron.find_port,
                          device=router,
                          subnet=subnet,
                          network=network)
        port = stacks.ensure_router_interface(router=router,
                                              network=network,
                                              subnet=subnet,
                                              add_cleanup=True)
        self.assertEqual(router['id'], port['device_id'])
        self.assertEqual(neutron.find_port(device=router,
                                           network=network,
                                           subnet=subnet)['id'],
                         port['id'])
        self.assertEqual(port['id'],
                         stacks.ensure_router_interface(
                             router=router,
                             network=network,
                             subnet=subnet,
                             add_cleanup=True)['id'])
        return port
