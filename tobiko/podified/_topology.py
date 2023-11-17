# Copyright 2023 Red Hat
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

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack import topology
from tobiko import rhosp
from tobiko.podified import _edpm
from tobiko.podified import _openshift

LOG = log.getLogger(__name__)


skip_if_not_podified = tobiko.skip_unless(
    "Podified deployment not configured", _openshift.has_podified_cp
)


class PodifiedTopology(rhosp.RhospTopology):

    # NOTE(slaweq): those service names are only valid for the EDPM nodes
    agent_to_service_name_mappings = {
        neutron.DHCP_AGENT: 'tripleo_neutron_dhcp',
        neutron.OVN_METADATA_AGENT: 'tripleo_ovn_metadata_agent',
        neutron.NEUTRON_OVN_METADATA_AGENT: 'tripleo_ovn_metadata_agent',
        neutron.OVN_CONTROLLER: 'tripleo_ovn_controller',
        neutron.OVN_BGP_AGENT: 'tripleo_ovn_bgp_agent',
        neutron.FRR: 'tripleo_frr'
    }

    # NOTE(slaweq): those container names are only valid for the EDPM nodes
    agent_to_container_name_mappings = {
        neutron.DHCP_AGENT: 'neutron_dhcp',
        neutron.OVN_METADATA_AGENT: 'ovn_metadata_agent',
        neutron.NEUTRON_OVN_METADATA_AGENT: 'ovn_metadata_agent',
        neutron.OVN_CONTROLLER: 'ovn_controller',
        neutron.OVN_BGP_AGENT: 'ovn_bgp_agent',
        neutron.FRR: 'frr'
    }

    def create_node(self, name, ssh_client, **kwargs):
        return EdpmNode(topology=self,
                        name=name,
                        ssh_client=ssh_client,
                        **kwargs)

    def discover_nodes(self):
        self.discover_ssh_proxy_jump_node()
        self.discover_ocp_worker_nodes()
        self.discover_edpm_nodes()

    def discover_ssh_proxy_jump_node(self):
        pass

    def discover_ocp_worker_nodes(self):
        # TODO(slaweq): discover OCP nodes where OpenStack CP is running
        pass

    def discover_edpm_nodes(self):
        for node in _openshift.list_edpm_nodes():
            LOG.debug(f"Found EDPM node {node['hostname']} "
                      f"(IP: {node['host']})")
            host_config = _edpm.edpm_host_config(node)
            ssh_client = _edpm.edpm_ssh_client(host_config=host_config)
            node = self.add_node(address=host_config.host,
                                 group='compute',
                                 ssh_client=ssh_client)
            assert isinstance(node, EdpmNode)


class EdpmNode(rhosp.RhospNode):

    def power_on_node(self):
        LOG.debug(f"Ensuring EDPM node {self.name} power is on...")

    def power_off_node(self):
        LOG.debug(f"Ensuring EDPM node {self.name} power is off...")


def setup_podified_topology():
    topology.set_default_openstack_topology_class(PodifiedTopology)
