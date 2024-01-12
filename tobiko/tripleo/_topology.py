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

import re
import typing

import metalsmith
import netaddr
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import topology
from tobiko import rhosp
from tobiko.shell import files
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.tripleo import _overcloud
from tobiko.tripleo import _undercloud
from tobiko.tripleo import containers

CONF = config.CONF
LOG = log.getLogger(__name__)


class TripleoTopology(rhosp.RhospTopology):

    agent_to_service_name_mappings = {
        neutron.DHCP_AGENT: 'tripleo_neutron_dhcp',
        neutron.L3_AGENT:  'tripleo_neutron_l3_agent',
        neutron.OPENVSWITCH_AGENT: 'tripleo_neutron_ovs_agent',
        neutron.METADATA_AGENT: 'tripleo_neutron_metadata_agent',
        neutron.OVN_METADATA_AGENT: 'tripleo_ovn_metadata_agent',
        neutron.NEUTRON_OVN_METADATA_AGENT: 'tripleo_ovn_metadata_agent',
        neutron.OVN_CONTROLLER: 'tripleo_ovn_controller',
        neutron.OVN_BGP_AGENT: 'tripleo_ovn_bgp_agent',
        neutron.FRR: 'tripleo_frr',
        neutron.NEUTRON: 'tripleo_neutron_api'
    }

    agent_to_container_name_mappings = {
        neutron.DHCP_AGENT: 'neutron_dhcp',
        neutron.L3_AGENT:  'neutron_l3_agent',
        neutron.OPENVSWITCH_AGENT: 'neutron_ovs_agent',
        neutron.METADATA_AGENT: 'neutron_metadata_agent',
        neutron.OVN_METADATA_AGENT: 'ovn_metadata_agent',
        neutron.NEUTRON_OVN_METADATA_AGENT: 'ovn_metadata_agent',
        neutron.OVN_CONTROLLER: 'ovn_controller',
        neutron.OVN_BGP_AGENT: 'ovn_bgp_agent',
        neutron.FRR: 'frr'
    }

    config_file_mappings = {
        'ml2_conf.ini': '/var/lib/config-data/puppet-generated/neutron'
                        '/etc/neutron/plugins/ml2/ml2_conf.ini',
        'bgp-agent.conf': '/var/lib/config-data/ansible-generated/'
                          'ovn-bgp-agent/etc/ovn-bgp-agent/bgp-agent.conf'
    }

    # TODO: add more known subgrups here
    known_subgroups: typing.List[str] = ['controller', 'compute']

    # In TripleO we need to parse log files directly
    file_digger_class = files.LogFileDigger

    # This is dict which handles mapping of the log file and systemd_unit (if
    # needed) for the OpenStack services
    # Format of this dict is like below:
    # service_name: (log_filename, systemd_unit_name)
    log_names_mappings = {
        neutron.SERVER: '/var/log/containers/neutron/server.log*',
    }

    _container_runtime_cmd = None

    pcs_resource_list = ['haproxy', 'galera', 'redis', 'ovn-dbs', 'cinder',
                         'rabbitmq', 'manila', 'ceph', 'pacemaker']

    sidecar_container_list = [
        'neutron-haproxy-ovnmeta', 'neutron-haproxy-qrouter',
        'neutron-dnsmasq-qdhcp', 'neutron-keepalived-qrouter', 'neutron-radvd']

    @property
    def container_runtime_cmd(self):
        if self._container_runtime_cmd is None:
            self._container_runtime_cmd = \
                    containers.get_container_runtime_name()
        return self._container_runtime_cmd

    @property
    def ignore_containers_list(self):
        return self.pcs_resource_list + self.sidecar_container_list

    def create_node(self, name, ssh_client, **kwargs):
        return TripleoTopologyNode(topology=self,
                                   name=name,
                                   ssh_client=ssh_client,
                                   **kwargs)

    def assert_containers_running(self, expected_containers,
                                  group=None,
                                  full_name=True, bool_check=False,
                                  nodenames=None):
        group = group or 'overcloud'
        return containers.assert_containers_running(
            group=group,
            expected_containers=expected_containers,
            full_name=full_name,
            bool_check=bool_check,
            nodenames=nodenames)

    def list_containers_df(self, group=None):
        return containers.list_containers_df(group)

    def discover_nodes(self):
        self.discover_ssh_proxy_jump_node()
        self.discover_undercloud_nodes()
        self.discover_overcloud_nodes()

    def discover_undercloud_nodes(self):
        if _undercloud.has_undercloud():
            uc_config = _undercloud.undercloud_host_config()
            ssh_client = _undercloud.undercloud_ssh_client()
            self.add_node(address=uc_config.hostname,
                          group='undercloud',
                          ssh_client=ssh_client)

    def discover_overcloud_nodes(self):
        if _undercloud.has_undercloud():
            for instance in _overcloud.list_overcloud_nodes():
                try:
                    _overcloud.power_on_overcloud_node(instance)
                except Exception:
                    LOG.exception("Error ensuring overcloud node power "
                                  "status is on")
                host_config = _overcloud.overcloud_host_config(
                    instance=instance)
                ssh_client = _overcloud.overcloud_ssh_client(
                    instance=instance,
                    host_config=host_config)
                node = self.add_node(address=host_config.hostname,
                                     group='overcloud',
                                     ssh_client=ssh_client,
                                     overcloud_instance=instance)
                assert isinstance(node, TripleoTopologyNode)
                self.discover_overcloud_node_subgroups(node)

    def discover_overcloud_node_subgroups(self, node):
        # set of subgroups extracted from node name
        subgroups: typing.Set[str] = set()

        oc_groups_dict = CONF.tobiko.tripleo.overcloud_groups_dict
        # extract subgroups names from node name
        subgroups.update(oc_groups_dict.get(subgroup) or subgroup
                         for subgroup in node.name.split('-')
                         if is_valid_overcloud_group_name(group_name=subgroup,
                                                          node_name=node.name))

        # add all those known subgroups names that are contained in
        # the node name (controller, compute, ...)
        subgroups.update(subgroup
                         for subgroup in self.known_subgroups
                         if subgroup in node.name)

        # bind node to discovered subgroups
        if subgroups:
            for subgroup in sorted(subgroups):
                LOG.debug("Add node '%s' to subgroup '%s'", node.name,
                          subgroup)
                self.add_node(hostname=node.name, group=subgroup)
        else:
            LOG.warning("Unable to obtain any node subgroup from node "
                        "name: '%s'", node.name)
        return subgroups


class TripleoTopologyNode(rhosp.RhospNode):

    def __init__(self,
                 topology: topology.OpenStackTopology,
                 name: str,
                 ssh_client: ssh.SSHClientFixture,
                 addresses: typing.Iterable[netaddr.IPAddress],
                 hostname: str,
                 overcloud_instance: metalsmith.Instance = None,
                 rhosp_version: tobiko.Version = None):
        # pylint: disable=redefined-outer-name
        super().__init__(topology=topology,
                         name=name,
                         ssh_client=ssh_client,
                         addresses=addresses,
                         hostname=hostname)
        self._overcloud_instance = overcloud_instance
        self._rhosp_version = rhosp_version

    @property
    def overcloud_instance(self) -> typing.Optional[metalsmith.Instance]:
        return self._overcloud_instance

    @property
    def rhosp_version(self) -> tobiko.Version:
        if self._rhosp_version is None:
            self._rhosp_version = self._get_rhosp_version()
        return self._rhosp_version

    l3_agent_conf_path = (
        '/var/lib/config-data/neutron/etc/neutron/l3_agent.ini')

    def list_running_servers(self) -> typing.List[nova.NovaServer]:
        running_servers = list()
        for server in nova.list_servers():
            if server.status != 'SHUTOFF':
                hypervisor_name = nova.get_server_hypervisor(server,
                                                             short=True)
                if self.name == hypervisor_name:
                    running_servers.append(server)
        return running_servers

    def power_on_node(self):
        if self.overcloud_instance is None:
            raise TypeError(f"Node {self.name} is not and Overcloud server")
        self.ssh_client.close()
        LOG.debug(f"Ensuring overcloud node {self.name} power is on...")
        _overcloud.power_on_overcloud_node(instance=self.overcloud_instance)
        hostname = sh.get_hostname(ssh_client=self.ssh_client)
        LOG.debug(f"Overcloud node {self.name} power is on ("
                  f"hostname={hostname})")

    def power_off_node(self):
        if self.overcloud_instance is None:
            raise TypeError(f"Node {self.name} is not and Overcloud server")
        self.ssh_client.close()
        LOG.debug(f"Ensuring overcloud node {self.name} power is off...")
        _overcloud.power_off_overcloud_node(instance=self.overcloud_instance)
        LOG.debug(f"Overcloud server node {self.name} power is off.")


def is_valid_overcloud_group_name(group_name: str, node_name: str = None):
    if not group_name:
        return False
    if group_name in ['overcloud', node_name]:
        return False
    if is_number(group_name):
        return False
    return True


def is_number(text: str):
    try:
        float(text)
    except ValueError:
        return False
    else:
        return True


def setup_tripleo_topology():
    if _undercloud.has_undercloud() or _overcloud.has_overcloud():
        topology.set_default_openstack_topology_class(TripleoTopology)


def str_is_not_ip(check_str):
    letters = re.compile('[A-Za-z]')
    return bool(letters.match(check_str))


def actual_node_groups(groups):
    """return only existing node groups"""
    return set(groups).intersection(topology.list_openstack_node_groups())


def get_node(node_name):
    node_name = node_name.split('.')[0]
    return [node for node in topology.list_openstack_nodes() if
            node.name == node_name][0]


def is_composable_roles_env():
    composable_nodes = ['messaging', 'database', 'networker']
    for nodes in composable_nodes:
        if nodes in topology.list_openstack_node_groups():
            return True
    return False
