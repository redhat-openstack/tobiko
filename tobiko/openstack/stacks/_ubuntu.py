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

import typing

import tobiko
from tobiko import config
from tobiko.openstack import glance
from tobiko.openstack import topology
from tobiko.openstack.stacks import _nova
from tobiko.openstack.stacks import _vlan
from tobiko.shell import sh


CONF = config.CONF


class UbuntuMinimalImageFixture(glance.FileGlanceImageFixture):
    image_name = CONF.tobiko.ubuntu.image_name
    image_file = CONF.tobiko.ubuntu.image_file
    disk_format = CONF.tobiko.ubuntu.disk_format or "qcow2"
    container_format = CONF.tobiko.ubuntu.container_format or "bare"
    username = CONF.tobiko.ubuntu.username or 'ubuntu'
    password = CONF.tobiko.ubuntu.password or 'ubuntu'
    connection_timeout = CONF.tobiko.nova.ubuntu_connection_timeout
    disabled_algorithms = CONF.tobiko.ubuntu.disabled_algorithms
    is_reachable_timeout = CONF.tobiko.nova.ubuntu_is_reachable_timeout


IPERF3_SERVICE_FILE = """
[Unit]
Description=iperf3 server on port %i
After=syslog.target network.target

[Service]
ExecStart=/usr/bin/iperf3 -s -p %i
Restart=always
User=root

[Install]
WantedBy=multi-user.target
DefaultInstance=5201
"""


class UbuntuImageFixture(UbuntuMinimalImageFixture,
                         glance.CustomizedGlanceImageFixture):
    """Ubuntu server image running an HTTP server

    The server has additional installed packages compared to
    the minimal one:

    - iperf3
    - ping
    - ncat
    - nginx
    - vlan

    The image will also have below running services:

    - nginx HTTP server listening on TCP port 80
    - iperf3 server listening on TCP port 5201
    """

    def __init__(self,
                 ethernet_devide: str = None,
                 **kwargs):
        super().__init__(**kwargs)
        self._ethernet_device = ethernet_devide

    @property
    def firstboot_commands(self) -> typing.List[str]:
        return super().firstboot_commands + [
            'sh -c "hostname > /var/www/html/id"']

    @property
    def install_packages(self) -> typing.List[str]:
        return super().install_packages + ['iperf3',
                                           'iputils-ping',
                                           'nano',
                                           'ncat',
                                           'nginx',
                                           'vlan']

    # port of running HTTP server
    http_port = 80

    # port of running Iperf3 server
    iperf3_port = 5201

    @property
    def iperf3_service_name(self) -> str:
        return f"iperf3-server@{self.iperf3_port}.service"

    @property
    def run_commands(self) -> typing.List[str]:
        run_commands = super().run_commands
        run_commands.append(
            f'echo "{IPERF3_SERVICE_FILE}" '
            '> /etc/systemd/system/iperf3-server@.service')
        run_commands.append(
            f"systemctl enable iperf3-server@{self.iperf3_port}")
        run_commands.append('echo "8021q" >> /etc/modules')
        return run_commands

    @property
    def ethernet_device(self) -> str:
        if self._ethernet_device is None:
            self._ethernet_device = self._get_ethernet_device()
        return self._ethernet_device

    @staticmethod
    def _get_ethernet_device() -> str:
        """From OSP17 and above, Ubuntu stack should use a different interface name.
        This method returns the interface name, depending on the OSP version.
        """
        if_name = CONF.tobiko.ubuntu.interface_name
        if if_name is not None:
            return if_name
        from tobiko import tripleo
        if tripleo.has_overcloud(min_version='17.0'):
            return 'enp3s0'
        else:
            return 'ens3'

    def _get_customized_suffix(self) -> str:
        return f'{super()._get_customized_suffix()}-{self.ethernet_device}'

    @property
    def vlan_id(self) -> int:
        return tobiko.tobiko_config().neutron.vlan_id

    @property
    def vlan_device(self) -> str:
        return f'vlan{self.vlan_id}'

    @property
    def vlan_config(self) -> typing.Dict[str, typing.Any]:
        return {
            'network': {
                'version': 2,
                'vlans': {
                    self.vlan_device: {
                        'link': self.ethernet_device,
                        'dhcp4': True,
                        'dhcp4-overrides': {
                            'use-routes': False
                        },
                        'dhcp6': True,
                        'dhcp6-overrides': {
                            'use-routes': False
                        },
                        'id': self.vlan_id,
                    }
                }
            }
        }

    @property
    def write_files(self) -> typing.Dict[str, str]:
        write_files = super().write_files
        write_files['/etc/netplan/75-tobiko-vlan.yaml'] = tobiko.dump_yaml(
            self.vlan_config)
        return write_files


class UbuntuFlavorStackFixture(_nova.FlavorStackFixture):
    ram = 256
    swap = 512


class UbuntuMinimalServerStackFixture(_nova.CloudInitServerStackFixture):

    #: Glance image used to create a Nova server instance
    image_fixture = tobiko.required_fixture(UbuntuMinimalImageFixture)

    #: Flavor used to create a Nova server instance
    flavor_stack = tobiko.required_fixture(UbuntuFlavorStackFixture)


class UbuntuServerStackFixture(UbuntuMinimalServerStackFixture,
                               _vlan.VlanServerStackFixture):
    """Ubuntu server running an HTTP server

    The server has additional commands compared to the minimal one:

    - iperf3
    - ping
    """

    #: Glance image used to create a Nova server instance
    image_fixture = tobiko.required_fixture(UbuntuImageFixture)

    @property
    def is_reachable_timeout(self) -> tobiko.Seconds:
        return self.image_fixture.is_reachable_timeout

    # port of running HTTP server
    @property
    def http_port(self) -> int:
        return self.image_fixture.http_port

    @property
    def iperf3_port(self) -> int:
        return self.image_fixture.iperf3_port

    @property
    def iperf3_service_name(self) -> str:
        return self.image_fixture.iperf3_service_name

    def wait_for_iperf3_server(self,
                               timeout: tobiko.Seconds = None,
                               interval: tobiko.Seconds = None):
        return sh.wait_for_active_systemd_units(self.iperf3_service_name,
                                                timeout=timeout,
                                                interval=interval,
                                                ssh_client=self.ssh_client)

    @property
    def vlan_id(self) -> int:
        return self.image_fixture.vlan_id

    @property
    def vlan_device(self) -> str:
        return self.image_fixture.vlan_device


@topology.skip_unless_osp_version('17.0', lower=True)
class UbuntuExternalServerStackFixture(UbuntuServerStackFixture,
                                       _nova.ExternalServerStackFixture):
    """Ubuntu server with port on special external network
    """
