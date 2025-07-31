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

import typing

import netaddr
from oslo_log import log

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack import topology
from tobiko.podified import _edpm
from tobiko.podified import _openshift
from tobiko.podified import containers
from tobiko import rhosp
from tobiko.shell import iperf3
from tobiko.shell import http_ping
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.shell import ssh

LOG = log.getLogger(__name__)


skip_if_not_podified = tobiko.skip_unless(
    "Podified deployment not configured", _openshift.has_podified_cp
)
skip_if_podified = tobiko.skip_if(
    "This test cannot run on a Podified deployment", _openshift.has_podified_cp
)

# In Podified topology there are groups like 'edpm-compute', 'edpm-networker'
# and 'edpm-other' but we need to provide also "virtual" group which will
# contain all of those "sub groups"
COMPUTE_GROUPS = [
    _openshift.EDPM_COMPUTE_GROUP,
    _openshift.EDPM_NETWORKER_GROUP,
    _openshift.EDPM_OTHER_GROUP
]
ALL_COMPUTES_GROUP_NAME = 'compute'
OCP_WORKER = 'ocp_worker'
EDPM_NODE = 'edpm_node'


class PodifiedTopology(rhosp.RhospTopology):

    # NOTE(slaweq): those service names are only valid for the EDPM nodes
    agent_to_service_name_mappings = {
        neutron.DHCP_AGENT: 'edpm_neutron_dhcp',
        neutron.L3_AGENT:  'edpm_neutron_l3_agent',
        neutron.OPENVSWITCH_AGENT: 'edpm_neutron_ovs_agent',
        neutron.METADATA_AGENT: 'edpm_neutron_metadata_agent',
        neutron.OVN_METADATA_AGENT: 'edpm_ovn_metadata_agent',
        neutron.NEUTRON_OVN_METADATA_AGENT: 'edpm_ovn_metadata_agent',
        neutron.NEUTRON_OVN_AGENT: 'edpm_ovn_agent',
        neutron.OVN_CONTROLLER: 'edpm_ovn_controller',
        neutron.OVN_BGP_AGENT: 'edpm_ovn_bgp_agent',
        neutron.FRR: 'edpm_frr'
    }

    # NOTE(slaweq): those container names are only valid for the EDPM nodes
    agent_to_container_name_mappings = {
        neutron.DHCP_AGENT: 'neutron_dhcp',
        neutron.L3_AGENT:  'neutron_l3_agent',
        neutron.OPENVSWITCH_AGENT: 'neutron_ovs_agent',
        neutron.METADATA_AGENT: 'neutron_metadata_agent',
        neutron.OVN_METADATA_AGENT: 'ovn_metadata_agent',
        neutron.NEUTRON_OVN_METADATA_AGENT: 'ovn_metadata_agent',
        neutron.NEUTRON_OVN_AGENT: 'ovn_agent',
        neutron.OVN_CONTROLLER: 'ovn_controller',
        neutron.OVN_BGP_AGENT: 'ovn_bgp_agent',
        neutron.FRR: 'frr'
    }

    sidecar_container_list = [
        'neutron-haproxy-ovnmeta',
        'neutron-dnsmasq-qdhcp'
    ]

    @property
    def ignore_containers_list(self):
        return self.sidecar_container_list

    def assert_containers_running(self, expected_containers,
                                  group=None,
                                  full_name=True, bool_check=False,
                                  nodenames=None):
        group = group or ALL_COMPUTES_GROUP_NAME
        return containers.assert_containers_running(
            group=group,
            expected_containers=expected_containers,
            full_name=full_name,
            bool_check=bool_check,
            nodenames=nodenames)

    def list_containers_df(self, group=None):
        return containers.list_containers_df(group)

    def add_node(self,
                 hostname: typing.Optional[str] = None,
                 address: typing.Optional[str] = None,
                 group: typing.Optional[str] = None,
                 ssh_client: typing.Optional[ssh.SSHClientFixture] = None,
                 **create_params) \
            -> topology.OpenStackTopologyNode:
        node = super(PodifiedTopology, self).add_node(
            hostname=hostname,
            address=address,
            group=group,
            ssh_client=ssh_client,
            **create_params
        )
        # NOTE(slaweq): additionally lets add every edpm node to the "legacy"
        # group named "compute"
        if group and group in COMPUTE_GROUPS:
            group_nodes = self.add_group(group=ALL_COMPUTES_GROUP_NAME)
            if node and node not in group_nodes:
                group_nodes.append(node)
                node.add_group(group=ALL_COMPUTES_GROUP_NAME)
        return node

    def create_node(self, name, ssh_client, **kwargs):
        node_type = kwargs.pop('node_type')
        if node_type == OCP_WORKER:
            return OcpNode(topology=self, name=name, ssh_client=None,
                           **kwargs)
        else:
            return EdpmNode(topology=self, name=name, ssh_client=ssh_client,
                            **kwargs)

    def discover_nodes(self):
        self.discover_ssh_proxy_jump_node()
        self.discover_ocp_worker_nodes()
        self.discover_edpm_nodes()

    def discover_ssh_proxy_jump_node(self):
        pass

    def discover_ocp_worker_nodes(self):
        # NOTE(slaweq): For now this will only discover nodes but there will be
        # no ssh_client created to ssh to those nodes. Getting
        # ssh_client to those nodes may be implemented in the future if that
        # will be needed, but this may be hard e.g. for the CRC environments as
        # in that case internal OCP worker's IP address is not accessible from
        # outside at all
        for worker_data in _openshift.list_ocp_workers():
            node = self._add_node(
                addresses=worker_data['addresses'],
                hostname=worker_data['hostname'],
                ssh_client=None,
                create_ssh_client=False,
                node_type=OCP_WORKER)
            group_nodes = self.add_group(group='controller')
            if node not in group_nodes:
                group_nodes.append(node)
                node.add_group(group='controller')

    def discover_edpm_nodes(self):
        for node in _openshift.list_edpm_nodes():
            LOG.debug(f"Found EDPM node {node['hostname']} "
                      f"(IP: {node['host']})")
            group = node.pop('group')
            host_config = _edpm.edpm_host_config(node)
            ssh_client = _edpm.edpm_ssh_client(host_config=host_config)
            node = self.add_node(address=host_config.host,
                                 group=group,
                                 ssh_client=ssh_client,
                                 node_type=EDPM_NODE)
            assert isinstance(node, EdpmNode)

    def check_or_start_background_vm_ping(
            self,
            server_ip: typing.Union[str, netaddr.IPAddress],
            ssh_client: ssh.SSHClientType = None):
        if not ssh_client:
            _openshift.check_or_start_tobiko_ping_command(
                server_ip=server_ip
            )
        else:
            sh.check_or_start_external_process(
                start_function=ping.execute_ping_in_background,
                check_function=ping.check_ping_results,
                liveness_function=ping.ping_alive,
                stop_function=ping.stop_ping,
                address=server_ip,
                ssh_client=ssh_client)

    def check_or_start_background_iperf_connection(
            self,
            server_ip: typing.Union[str, netaddr.IPAddress],
            port: int,
            protocol: str,
            ssh_client: ssh.SSHClientType = None,
            iperf3_server_ssh_client: ssh.SSHClientType = None):

        kwargs = {
            'address': server_ip,
            'port': port,
            'protocol': protocol,
            'ssh_client': ssh_client,
            'iperf3_server_ssh_client': iperf3_server_ssh_client,
            'check_function': iperf3.check_iperf3_client_results
        }
        if not ssh_client:
            kwargs['start_function'] = _openshift.start_iperf3
            kwargs['liveness_function'] = _openshift.iperf3_pod_alive
            kwargs['stop_function'] = _openshift.stop_iperf3_client
        else:
            kwargs['start_function'] = \
                iperf3.execute_iperf3_client_in_background
            kwargs['liveness_function'] = iperf3.iperf3_client_alive
            kwargs['stop_function'] = iperf3.stop_iperf3_client

        sh.check_or_start_external_process(**kwargs)

    def check_or_start_background_http_ping(
            self,
            server_ip: typing.Union[str, netaddr.IPAddress],  # noqa; pylint: disable=W0613
            ssh_client: ssh.SSHClientType = None):  # noqa; pylint: disable=W0613
        if not ssh_client:
            _openshift.check_or_start_tobiko_http_ping_command(
                server_ip=server_ip
            )
        else:
            sh.check_or_start_external_process(
                start_function=http_ping.start_http_ping_process,
                stop_function=http_ping.stop_http_ping_process,
                liveness_function=http_ping.http_ping_process_alive,
                check_function=http_ping.check_http_ping_results,
                server_ip=server_ip,
                ssh_client=ssh_client)


class EdpmNode(rhosp.RhospNode):

    def power_on_node(self):
        LOG.debug(f"Ensuring EDPM node {self.name} power is on...")
        self.ssh_client.close()
        _openshift.power_on_edpm_node(self.name)
        hostname = sh.get_hostname(ssh_client=self.ssh_client)
        LOG.debug(f"Overcloud node {self.name} power is on ("
                  f"hostname={hostname})")

    def power_off_node(self):
        LOG.debug(f"Ensuring EDPM node {self.name} power is off...")
        self.ssh_client.close()
        _openshift.power_off_edpm_node(self.name)
        LOG.debug(f"EDPM node {self.name} power is off.")


class OcpNode(rhosp.RhospNode):
    def reboot_node(self, reactivate_servers=True):
        start_time = tobiko.time()
        _openshift.reboot_ocp_node(self.name)
        for _ in tobiko.retry(timeout=600, interval=10):
            try:
                uptime = _openshift.get_ocp_node_uptime(self.name)
            except Exception:
                LOG.warning(f"Unable to get uptime from node {self.name}")
            else:
                elapsed_time = tobiko.time() - start_time
                if uptime < elapsed_time:
                    LOG.debug(f"OCP node {self.name} rebooted in "
                              f"{elapsed_time} seconds.")
                    break
                else:
                    LOG.debug(f"OCP node {self.name} still not rebooted "
                              f"{elapsed_time} seconds after reboot operation "
                              f"(uptime={uptime})")


def setup_podified_topology():
    topology.set_default_openstack_topology_class(PodifiedTopology)
