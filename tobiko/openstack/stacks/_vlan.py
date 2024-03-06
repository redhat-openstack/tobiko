# Copyright (c) 2021 Red Hat, Inc.
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

import abc
import typing

import netaddr

import tobiko
from tobiko import config
from tobiko.shell import ping
from tobiko.shell import ssh
from tobiko.openstack import neutron
from tobiko.openstack.stacks import _cirros
from tobiko.openstack.stacks import _neutron
from tobiko.openstack.stacks import _nova


CONF = config.CONF


class VlanNetworkStackFixture(_neutron.NetworkBaseStackFixture):
    @tobiko.interworker_synched('create_vlan_network_stack')
    def setup_stack(self):
        super().setup_stack()


class VlanProxyServerStackFixture(_cirros.CirrosServerStackFixture):
    network_stack = tobiko.required_fixture(VlanNetworkStackFixture)


class VlanServerStackFixture(_nova.ServerStackFixture, abc.ABC):

    @property
    def has_vlan(self) -> bool:
        return neutron.has_networking_extensions('trunk')

    #: stack with the newtwork where the trunk support is attached
    vlan_network_stack = tobiko.required_fixture(VlanNetworkStackFixture)

    @property
    def vlan_id(self) -> int:
        return CONF.tobiko.neutron.vlan_id

    @property
    def vlan_network(self) -> str:
        return self.vlan_network_stack.network_id

    @property
    def vlan_fixed_ipv4(self):
        return self.find_vlan_fixed_ip(ip_version=4)

    @property
    def vlan_fixed_ipv6(self):
        return self.find_vlan_fixed_ip(ip_version=6)

    def find_vlan_fixed_ip(self,
                           ip_version: int = None,
                           unique=False) -> netaddr.IPAddress:
        vlan_ips = self.list_vlan_fixed_ips(ip_version=ip_version)
        if unique:
            return vlan_ips.unique
        else:
            return vlan_ips.first

    def list_vlan_fixed_ips(self,
                            ip_version: int = None) \
            -> tobiko.Selection[netaddr.IPAddress]:
        fixed_ips = tobiko.Selection[netaddr.IPAddress]()
        if self.vlan_fixed_ips:
            fixed_ips.extend(netaddr.IPAddress(fixed_ip['ip_address'])
                             for fixed_ip in self.vlan_fixed_ips)
            if ip_version is not None and fixed_ips:
                fixed_ips = fixed_ips.with_attributes(version=ip_version)
        return fixed_ips

    @property
    def vlan_ssh_proxy_client(self) -> ssh.SSHClientType:
        return tobiko.setup_fixture(VlanProxyServerStackFixture).ssh_client

    def assert_vlan_is_reachable(self,
                                 ip_version: int = None,
                                 timeout: tobiko.Seconds = None,
                                 ssh_client: ssh.SSHClientType = None):
        fixed_ips = self.list_vlan_fixed_ips(ip_version=ip_version)
        if fixed_ips:
            if timeout is None:
                timeout = self.is_reachable_timeout
            if ssh_client is None:
                ssh_client = self.vlan_ssh_proxy_client
            ping.assert_reachable_hosts(fixed_ips,
                                        ssh_client=ssh_client,
                                        timeout=timeout)
        else:
            tobiko.fail(f'Server {self.stack_name} has any IP on VLAN port')

    def assert_vlan_is_unreachable(self,
                                   ip_version: int = None,
                                   timeout: tobiko.Seconds = None,
                                   ssh_client: ssh.SSHClientType = None):
        fixed_ips = self.list_vlan_fixed_ips(ip_version=ip_version)
        if fixed_ips:
            if ssh_client is None:
                ssh_client = self.vlan_ssh_proxy_client
            ping.assert_unreachable_hosts(fixed_ips,
                                          ssh_client=ssh_client,
                                          timeout=timeout)
        else:
            tobiko.fail(f'Server {self.stack_name} has any IP on VLAN port')

    @property
    def neutron_required_quota_set(self) -> typing.Dict[str, int]:
        requirements = super().neutron_required_quota_set
        if self.has_vlan:
            requirements['trunk'] += 1
            requirements['port'] += 1
        return requirements
