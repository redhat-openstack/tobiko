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

from tobiko.openstack.topology import _assert
from tobiko.openstack.topology import _config
from tobiko.openstack.topology import _exception
from tobiko.openstack.topology import _namespace
from tobiko.openstack.topology import _topology
from tobiko.openstack.topology import _sh

assert_reachable_nodes = _assert.assert_reachable_nodes
assert_unreachable_nodes = _assert.assert_unreachable_nodes

NoSuchOpenStackTopologyNodeGroup = _exception.NoSuchOpenStackTopologyNodeGroup
NoSuchOpenStackTopologyNode = _exception.NoSuchOpenStackTopologyNode

get_hosts_namespaces = _namespace.get_hosts_namespaces
assert_namespace_in_hosts = _namespace.assert_namespace_in_hosts
assert_namespace_not_in_hosts = _namespace.assert_namespace_not_in_hosts
wait_for_namespace_in_hosts = _namespace.wait_for_namespace_in_hosts

list_nodes_processes = _sh.list_nodes_processes

UnknowOpenStackContainerNameError = _topology.UnknowOpenStackContainerNameError
UnknowOpenStackServiceNameError = _topology.UnknowOpenStackServiceNameError
UnknownOpenStackConfigurationFile = _topology.UnknownOpenStackConfigurationFile
get_agent_service_name = _topology.get_agent_service_name
get_agent_container_name = _topology.get_agent_container_name
get_config_file_path = _topology.get_config_file_path
get_l3_agent_mode = _topology.get_l3_agent_mode
get_log_file_digger = _topology.get_log_file_digger
get_openstack_topology = _topology.get_openstack_topology
get_openstack_node = _topology.get_openstack_node
get_openstack_version = _topology.get_openstack_version
skip_unless_osp_version = _topology.skip_unless_osp_version
check_systemd_monitors_agent = _topology.check_systemd_monitors_agent
find_openstack_node = _topology.find_openstack_node
get_default_openstack_topology_class = (
    _topology.get_default_openstack_topology_class)
list_openstack_nodes = _topology.list_openstack_nodes
list_openstack_node_groups = _topology.list_openstack_node_groups
OpenStackTopology = _topology.OpenStackTopology
OpenStackTopologyNode = _topology.OpenStackTopologyNode
set_default_openstack_topology_class = (
    _topology.set_default_openstack_topology_class)
verify_osp_version = _topology.verify_osp_version
get_config_setting = _topology.get_config_setting
node_name_from_hostname = _topology.node_name_from_hostname
remove_duplications = _topology.remove_duplications
OpenstackGroupNamesType = _topology.OpenstackGroupNamesType

OpenStackTopologyConfig = _config.OpenStackTopologyConfig
