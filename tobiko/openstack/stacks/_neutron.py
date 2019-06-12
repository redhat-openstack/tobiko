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


import tobiko
from tobiko import config
from tobiko.openstack import heat
from tobiko.openstack import neutron
from tobiko.openstack.stacks import _hot
from tobiko.openstack.stacks import _nova
from tobiko.shell import ssh


CONF = config.CONF


@neutron.skip_if_missing_networking_extensions('port-security')
class NetworkStackFixture(heat.HeatStackFixture):
    """Heat stack for creating internal network with a router to external"""

    #: Heat template file
    template = _hot.heat_template_file('neutron/network.yaml')

    #: Disable port security by default for new network ports
    port_security_enabled = False

    #: Default IPv4 sub-net CIDR
    ipv4_cidr = '190.40.2.0/24'

    @property
    def has_ipv4(self):
        """Whenever to setup IPv4 subnet"""
        return bool(self.ipv4_cidr)

    #: IPv6 sub-net CIDR
    ipv6_cidr = '2001:db8:1:2::/64'

    @property
    def has_ipv6(self):
        """Whenever to setup IPv6 subnet"""
        return bool(self.ipv6_cidr)

    #: Floating IP network where the Neutron floating IPs are created
    gateway_network = CONF.tobiko.neutron.floating_network

    @property
    def has_gateway(self):
        """Whenever to setup gateway router"""
        return bool(self.gateway_network)

    # Whenever cat obtain network MTU value
    has_net_mtu = neutron.has_networking_extensions('net-mtu')

    @property
    def network_details(self):
        return neutron.show_network(self.network_id)

    @property
    def ipv4_subnet_details(self):
        return neutron.show_subnet(self.ipv4_subnet_id)

    @property
    def gateway_details(self):
        return neutron.show_router(self.gateway_id)

    @property
    def gateway_network_id(self):
        return neutron.find_network(self.gateway_network)['id']

    @property
    def gateway_network_details(self):
        return neutron.show_network(self.gateway_network_id)


@neutron.skip_if_missing_networking_extensions('net-mtu-writable')
class NetworkWithNetMtuWriteStackFixture(NetworkStackFixture):

    # Whenever cat obtain network MTU value
    has_net_mtu = True

    #: Value for maximum transfer unit on the internal network
    mtu = 1000

    def setup_parameters(self):
        """Setup Heat template parameters"""
        super(NetworkWithNetMtuWriteStackFixture, self).setup_parameters()
        if self.mtu:
            self.setup_net_mtu_writable()

    @neutron.skip_if_missing_networking_extensions('net-mtu-writable')
    def setup_net_mtu_writable(self):
        """Setup maximum transfer unit size for the network"""
        self.parameters.setdefault('value_specs', {}).update(mtu=self.mtu)


@neutron.skip_if_missing_networking_extensions('security-group')
class SecurityGroupsFixture(heat.HeatStackFixture):
    """Heat stack with some security groups

    """
    #: Heat template file
    template = _hot.heat_template_file('neutron/security_groups.yaml')


@neutron.skip_if_missing_networking_extensions('port-security')
class FloatingIpServerStackFixture(heat.HeatStackFixture):

    #: Heat template file
    template = _hot.heat_template_file('neutron/floating_ip_server.yaml')

    #: stack with the key pair for the server instance
    key_pair_stack = tobiko.required_setup_fixture(
        _nova.KeyPairStackFixture)

    #: stack with the internal where the server port is created
    network_stack = tobiko.required_setup_fixture(NetworkStackFixture)

    #: Glance image used to create a Nova server instance
    image = CONF.tobiko.nova.image

    #: Nova flavor used to create a Nova server instance
    flavor = CONF.tobiko.nova.flavor

    #: username used to login to a Nova server instance
    username = CONF.tobiko.nova.username

    #: password used to login to a Nova server instance
    password = CONF.tobiko.nova.password

    #: Whenever port security on internal network is enable
    port_security_enabled = False

    #: Security groups to be associated to network ports
    security_groups = []

    @property
    def key_name(self):
        return self.key_pair_stack.key_name

    @property
    def network(self):
        return self.network_stack.network_id

    #: Floating IP network where the Neutron floating IP is created
    floating_network = CONF.tobiko.neutron.floating_network

    @property
    def has_floating_ip(self):
        return bool(self.floating_network)

    @property
    def ssh_client(self):
        return ssh.ssh_client(
            host=self.floating_ip_address,
            username=self.username,
            password=self.password)

    @property
    def ssh_command(self):
        return ssh.ssh_command(
            host=self.floating_ip_address,
            username=self.username)
