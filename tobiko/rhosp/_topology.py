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
from tobiko.openstack import nova
from tobiko.openstack import topology
from tobiko.rhosp import _version_utils
from tobiko.shell import ssh

LOG = log.getLogger(__name__)


def get_ip_to_nodes_dict(group, openstack_nodes=None):
    if not openstack_nodes:
        openstack_nodes = topology.list_openstack_nodes(group=group)
    ip_to_nodes_dict = {str(node.public_ip): node.name for node in
                        openstack_nodes}
    return ip_to_nodes_dict


def ip_to_hostname(oc_ip, group=None):
    ip_to_nodes_dict = get_ip_to_nodes_dict(group)
    oc_ipv6 = oc_ip.replace(".", ":")
    if netaddr.valid_ipv4(oc_ip) or netaddr.valid_ipv6(oc_ip):
        return ip_to_nodes_dict[oc_ip]
    elif netaddr.valid_ipv6(oc_ipv6):
        LOG.debug("The provided string was a modified IPv6 address: %s",
                  oc_ip)
        return ip_to_nodes_dict[oc_ipv6]
    else:
        tobiko.fail("wrong IP value provided %s" % oc_ip)


class RhospTopology(topology.OpenStackTopology):

    """Base topology for Red Hat OpenStack deployments.

    This is base topology which represents common parts between Tripleo and
    Podified deployments.
    """

    has_containers = True
    container_runtime_cmd = 'podman'

    @property
    def ignore_containers_list(self):
        return None


class RhospNode(topology.OpenStackTopologyNode):

    """Base RHOSP Node

    This class represents common parts between Overcloud nodes and EDPM nodes
    in Red Hat OpenStack deployments.
    """

    def __init__(self,
                 topology: topology.OpenStackTopology,
                 name: str,
                 ssh_client: ssh.SSHClientFixture,
                 addresses: typing.Iterable[netaddr.IPAddress],
                 hostname: str,
                 rhosp_version: tobiko.Version = None):
        # pylint: disable=redefined-outer-name
        super().__init__(topology=topology,
                         name=name,
                         ssh_client=ssh_client,
                         addresses=addresses,
                         hostname=hostname)
        self._rhosp_version = rhosp_version

    @property
    def rhosp_version(self) -> tobiko.Version:
        if self._rhosp_version is None:
            self._rhosp_version = self._get_rhosp_version()
        return self._rhosp_version

    def _get_rhosp_version(self) -> tobiko.Version:
        return _version_utils.get_rhosp_version(connection=self.connection)

    def power_on_node(self):
        pass

    def power_off_node(self):
        pass

    def reboot_node(self, reactivate_servers=True):
        """Reboot node

        This method reboots a node and may start every Nova
        server which is not in SHUTOFF status before restarting.

        :param reactivate_servers: whether or not to re-start the servers which
            are hosted on the compute node after the reboot
        """

        running_servers: typing.List[nova.NovaServer] = []
        if reactivate_servers:
            running_servers = self.list_running_servers()
            LOG.debug(f'Servers to restart after reboot: {running_servers}')

        self.power_off_node()
        self.power_on_node()

        if running_servers:
            LOG.info(f'Restart servers after rebooting compute node '
                     f'{self.name}...')
            for server in running_servers:
                nova.wait_for_server_status(server=server.id,
                                            status='SHUTOFF')
                LOG.debug(f'Re-activate server {server.name} with ID '
                          f'{server.id}')
                nova.activate_server(server=server)
                LOG.debug(f'Server {server.name} with ID {server.id} has '
                          f'been reactivated')

    def list_running_servers(self) -> typing.List[nova.NovaServer]:
        running_servers = list()
        for server in nova.list_servers():
            if server.status != 'SHUTOFF':
                hypervisor_name = nova.get_server_hypervisor(server,
                                                             short=True)
                if self.name == hypervisor_name:
                    running_servers.append(server)
        return running_servers
