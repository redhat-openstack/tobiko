# Copyright 2019 Red Hat
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

from tobiko.openstack.neutron import _agent
from tobiko.openstack.neutron import _client
from tobiko.openstack.neutron import _extension
from tobiko.openstack.neutron import _floating_ip
from tobiko.openstack.neutron import _port
from tobiko.openstack.neutron import _quota_set
from tobiko.openstack.neutron import _network
from tobiko.openstack.neutron import _router
from tobiko.openstack.neutron import _security_group
from tobiko.openstack.neutron import _subnet
from tobiko.openstack.neutron import _subnet_pool


SERVER = 'neutron-server'
METADATA_IPv4 = '169.254.169.254'
DHCP_AGENT = _agent.DHCP_AGENT
L3_AGENT = _agent.L3_AGENT
METADATA_AGENT = _agent.METADATA_AGENT
OPENVSWITCH_AGENT = _agent.OPENVSWITCH_AGENT
OVN_CONTROLLER = _agent.OVN_CONTROLLER
OVN_METADATA_AGENT = _agent.OVN_METADATA_AGENT
NEUTRON_OVN_METADATA_AGENT = _agent.NEUTRON_OVN_METADATA_AGENT
OVN_BGP_AGENT = _agent.OVN_BGP_AGENT
FRR = _agent.FRR
NEUTRON = _agent.NEUTRON
DEFAULT_SG_NAME = _security_group.DEFAULT_SG_NAME
STATEFUL_OVN_ACTION = _security_group.STATEFUL_OVN_ACTION
STATELESS_OVN_ACTION = _security_group.STATELESS_OVN_ACTION

AgentNotFoundOnHost = _agent.AgentNotFoundOnHost
NotFound = _client.NotFound
NeutronAgentType = _agent.NeutronAgentType
SecurityGroupType = _security_group.SecurityGroupType
SecurityGroupIdOrNameType = _security_group.SecurityGroupIdOrNameType
get_l3_agent_mode = _agent.get_l3_agent_mode
find_l3_agent_hosting_router = _agent.find_l3_agent_hosting_router
list_agents = _agent.list_agents
list_dhcp_agent_hosting_network = _agent.list_dhcp_agent_hosting_network
list_l3_agent_hosting_routers = _agent.list_l3_agent_hosting_routers
list_networking_agents = _agent.list_networking_agents
skip_if_missing_networking_agents = _agent.skip_if_missing_networking_agents
skip_unless_is_ovn = _agent.skip_unless_is_ovn
skip_unless_is_ovs = _agent.skip_unless_is_ovs
skip_if_is_old_ovn = _agent.skip_if_is_old_ovn
has_ovn = _agent.has_ovn
has_ovs = _agent.has_ovs

NeutronClientFixture = _client.NeutronClientFixture
ServiceUnavailable = _client.ServiceUnavailable
NeutronClient = _client.NeutronClient
NeutronClientException = _client.NeutronClientException
NeutronClientType = _client.NeutronClientType
neutron_client = _client.neutron_client
get_neutron_client = _client.get_neutron_client

get_networking_extensions = _extension.get_networking_extensions
missing_networking_extensions = _extension.missing_networking_extensions
has_networking_extensions = _extension.has_networking_extensions
skip_if_missing_networking_extensions = (
    _extension.skip_if_missing_networking_extensions)

create_floating_ip = _floating_ip.create_floating_ip
delete_floating_ip = _floating_ip.delete_floating_ip
get_floating_ip = _floating_ip.get_floating_ip
get_floating_ip_id = _floating_ip.get_floating_ip_id
find_floating_ip = _floating_ip.find_floating_ip
list_floating_ips = _floating_ip.list_floating_ips
update_floating_ip = _floating_ip.update_floating_ip
FloatingIpType = _floating_ip.FloatingIpType
FloatingIpIdType = _floating_ip.FloatingIpIdType
NoSuchFloatingIp = _floating_ip.NoSuchFloatingIp

create_port = _port.create_port
delete_port = _port.delete_port
get_port = _port.get_port
get_port_id = _port.get_port_id
find_device_ip_address = _port.find_device_ip_address
find_port = _port.find_port
find_port_ip_address = _port.find_port_ip_address
list_ports = _port.list_ports
list_port_ip_addresses = _port.list_port_ip_addresses
list_device_ip_addresses = _port.list_device_ip_addresses
update_port = _port.update_port
PortType = _port.PortType
PortIdType = _port.PortIdType
NoSuchPort = _port.NoSuchPort

get_neutron_quota_set = _quota_set.get_neutron_quota_set
set_neutron_quota_set = _quota_set.set_neutron_quota_set
ensure_neutron_quota_limits = _quota_set.ensure_neutron_quota_limits
EnsureNeutronQuotaLimitsError = _quota_set.EnsureNeutronQuotaLimitsError

create_network = _network.create_network
delete_network = _network.delete_network
get_network = _network.get_network
get_network_id = _network.get_network_id
find_network = _network.find_network
list_networks = _network.list_networks
list_network_nameservers = _network.list_network_nameservers
NoSuchNetwork = _network.NoSuchNetwork
NetworkType = _network.NetworkType
NetworkIdType = _network.NetworkIdType

add_router_interface = _router.add_router_interface
create_router = _router.create_router
delete_router = _router.delete_router
get_ovs_router_namespace = _router.get_ovs_router_namespace
get_router = _router.get_router
get_router_id = _router.get_router_id
remove_router_interface = _router.remove_router_interface
wait_for_master_and_backup_agents = _router.wait_for_master_and_backup_agents
update_router = _router.update_router
RouterType = _router.RouterType
RouterIdType = _router.RouterIdType
NoSuchRouter = _router.NoSuchRouter

create_subnet = _subnet.create_subnet
delete_subnet = _subnet.delete_subnet
ensure_subnet_gateway = _subnet.ensure_subnet_gateway
get_subnet = _subnet.get_subnet
get_subnet_id = _subnet.get_subnet_id
find_subnet = _subnet.find_subnet
list_subnets = _subnet.list_subnets
SubnetType = _subnet.SubnetType
SubnetIdType = _subnet.SubnetIdType
NoSuchSubnet = _subnet.NoSuchSubnet

SubnetPoolType = _subnet_pool.SubnetPoolType
SubnetPoolIdType = _subnet_pool.SubnetPoolIdType
NoSuchSubnetPool = _subnet_pool.NoSuchSubnetPool
get_subnet_pool = _subnet_pool.get_subnet_pool
create_subnet_pool = _subnet_pool.create_subnet_pool
delete_subnet_pool = _subnet_pool.delete_subnet_pool
find_subnet_pool = _subnet_pool.find_subnet_pool
list_subnet_pools = _subnet_pool.list_subnet_pools

list_security_groups = _security_group.list_security_groups
get_security_group = _security_group.get_security_group
get_default_security_group = _security_group.get_default_security_group
create_security_group = _security_group.create_security_group
update_security_group = _security_group.update_security_group
delete_security_group = _security_group.delete_security_group
create_security_group_rule = _security_group.create_security_group_rule
