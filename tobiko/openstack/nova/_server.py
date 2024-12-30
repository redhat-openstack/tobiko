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

from oslo_log import log
import netaddr

import tobiko
from tobiko.openstack.nova import _client
from tobiko.shell import ssh
from tobiko.shell import ping


LOG = log.getLogger(__name__)


def list_server_ip_addresses(server, network_name=None, ip_version=None,
                             address_type=None, check_connectivity=False,
                             ssh_client=None, count=None):
    ips = tobiko.Selection()
    for _network_name, addresses in server.addresses.items():
        if count and len(ips) == count:
            break

        # check network name
        if network_name and network_name != _network_name:
            continue

        for address in addresses:
            if check_server_ip_address(address,
                                       ip_version=ip_version,
                                       address_type=address_type):
                ips.append(netaddr.IPAddress(address['addr'],
                                             version=address['version']))

    # check ICMP connectivity
    if check_connectivity:
        ips = ping.list_reachable_hosts(ips, ssh_client=ssh_client)

    return ips


def check_server_ip_address(address, ip_version=None, address_type=None):
    if ip_version and ip_version != address['version']:
        return False

    # check IP address type
    if address_type:
        try:
            if address_type != address['OS-EXT-IPS:type']:
                return False
        except KeyError as ex:
            raise ValueError("Unable to get IP type from server address "
                             f"'{address}'") from ex

    return True


def find_server_ip_address(server, unique=False, **kwargs):
    count = unique and 2 or 1
    addresses = list_server_ip_addresses(server=server, count=count, **kwargs)
    return unique and addresses.unique or addresses.first


class HasServerMixin(_client.HasNovaClientMixin):

    @property
    def server_id(self):
        raise NotImplementedError

    @property
    def server(self):
        return _client.get_server(self.server_id)

    @property
    def server_name(self):
        return self.server.name

    @property
    def server_ips(self):
        return self.list_server_ips()

    def list_server_ips(self, **kwargs):
        return list_server_ip_addresses(server=self.server, **kwargs)

    @property
    def server_fixed_ips(self):
        return self.list_server_ips(address_type='fixed', check=True)

    @property
    def server_floating_ip(self):
        floating_ips = self.list_server_ips(address_type='floating', count=1)
        if floating_ips:
            return floating_ips.first
        else:
            return None

    @property
    def has_floating_ip(self):
        return bool(self.server_floating_ip)

    @property
    def server_console_output(self):
        return super(HasServerMixin, self).get_server_console_output(
            server=self.server_id)

    @property
    def server_public_ip(self):
        return self.server_floating_ip or self.server_fixed_ips.first

    @property
    def ssh_client(self):
        return ssh.ssh_client(host=self.server_public_ip,
                              username=self.ssh_username,
                              password=self.ssh_password,
                              proxy_client=self.ssh_proxy_client)

    ssh_proxy_client = None
    ssh_username = None
    ssh_password = None


def get_server_id(server: _client.ServerType) -> str:
    if isinstance(server, str):
        return server
    else:
        return server.id


def action_on_all_instances(action):
    """try to start/stop all instances"""
    if action not in ('active', 'shutoff'):
        tobiko.fail(f'Wrong action on VM instances: {action}')

    client_action_method = (_client.activate_server if action == 'active'
                            else _client.shutoff_server)
    expected_vm_status = 'ACTIVE' if action == 'active' else 'SHUTOFF'

    for instance in _client.list_servers():
        activated_instance = client_action_method(instance)
        instance_info = 'instance {nova_instance} is {state} on {host}'.format(
            nova_instance=activated_instance.name,
            state=activated_instance.status,
            host=activated_instance._info[  # pylint: disable=W0212
                'OS-EXT-SRV-ATTR:hypervisor_hostname'])
        LOG.info(instance_info)
        if activated_instance.status != expected_vm_status:
            tobiko.fail(instance_info)
