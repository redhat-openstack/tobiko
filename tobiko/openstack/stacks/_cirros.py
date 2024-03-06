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

import io
import typing

from paramiko import sftp_file

import tobiko
from tobiko import config
from tobiko.openstack import glance
from tobiko.openstack import neutron
from tobiko.openstack import heat
from tobiko.openstack.stacks import _neutron
from tobiko.openstack.stacks import _nova
from tobiko.shell import sh
from tobiko.shell import ssh
import tobiko.tripleo
from tobiko.openstack.stacks import _hot

CONF = config.CONF

CIRROS_IMAGE_VERSION = '0.5.2'

CIRROS_IMAGE_URL = (
    'http://download.cirros-cloud.net/{version}/'
    'cirros-{version}-x86_64-disk.img').format(
    version=CIRROS_IMAGE_VERSION)


class CirrosImageFixture(glance.URLGlanceImageFixture):

    image_url = CONF.tobiko.cirros.image_url or CIRROS_IMAGE_URL
    image_name = CONF.tobiko.cirros.image_name
    image_file = CONF.tobiko.cirros.image_file
    container_format = CONF.tobiko.cirros.container_format or "bare"
    disk_format = CONF.tobiko.cirros.disk_format or "qcow2"
    username = CONF.tobiko.cirros.username or 'cirros'
    password = CONF.tobiko.cirros.password or 'gocubsgo'
    connection_timeout = CONF.tobiko.cirros.connection_timeout or 200.
    disabled_algorithms = CONF.tobiko.cirros.disabled_algorithms or {
        #: disabled_algorithms is required to connect to CirrOS servers
        # when using recent Paramiko versions (>= 2.9.2)
        'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']}


class CirrosFlavorStackFixture(_nova.FlavorStackFixture):
    ram = 128


class CirrosServerStackFixture(_nova.ServerStackFixture):

    #: Glance image used to create a Nova server instance
    image_fixture = tobiko.required_fixture(CirrosImageFixture)

    #: Flavor used to create a Nova server instance
    flavor_stack = tobiko.required_fixture(CirrosFlavorStackFixture)

    #: CirrOS can't get IP addresses from config-drive
    need_dhcp = True

    #: We expect CirrOS based servers to be fast to boot
    is_reachable_timeout: tobiko.Seconds = 300.

    @tobiko.interworker_synched('cirros_server_setup_fixture')
    def setup_fixture(self):
        super(CirrosServerStackFixture, self).setup_fixture()

    @property
    def ssh_client(self) -> ssh.SSHClientFixture:
        ssh_client = super().ssh_client
        connection = sh.shell_connection(ssh_client)
        if not connection.is_cirros:
            connection = CirrosShellConnection(ssh_client=ssh_client)
            sh.register_shell_connection(connection)
        return ssh_client


class CirrosServerWithDefaultSecurityGroupStackFixture(
        CirrosServerStackFixture):

    #: Use "Default" Security Group of the project
    security_groups = [neutron.DEFAULT_SG_NAME]


class CirrosShellConnection(sh.SSHShellConnection):

    @property
    def is_cirros(self) -> bool:
        return True

    def get_file(self, remote_file: str, local_file: str):
        content = self.execute(f"cat '{remote_file}'").stdout
        with io.open(local_file, 'wt') as fd:
            fd.write(content)

    def put_file(self, local_file: str, remote_file: str):
        with io.open(local_file, 'rt') as fd:
            content = fd.read()
        self.execute(f"cat >'{remote_file}'", stdin=content)

    def open_file(self,
                  filename: typing.Union[str, bytes],
                  mode: str,
                  buffering: int = None) -> sftp_file.SFTPFile:
        raise NotImplementedError


class CirrosPeerServerStackFixture(CirrosServerStackFixture,
                                   _nova.PeerServerStackFixture):
    #: Peer server used to reach this one
    peer_stack = tobiko.required_fixture(CirrosServerStackFixture)


class CirrosSameHostServerStackFixture(
        CirrosPeerServerStackFixture, _nova.SameHostServerStackFixture):
    pass


class CirrosDifferentHostServerStackFixture(
        CirrosPeerServerStackFixture, _nova.DifferentHostServerStackFixture):
    pass


class RebootCirrosServerOperation(sh.RebootHostOperation):

    stack = tobiko.required_fixture(CirrosServerStackFixture)

    @property
    def ssh_client(self):
        return self.stack.ssh_client


class EvacuableCirrosImageFixture(CirrosImageFixture):

    tags = ['evacuable']


class EvacuableServerStackFixture(CirrosServerStackFixture):

    #: Glance image used to create a Nova server instance
    image_fixture = tobiko.required_fixture(EvacuableCirrosImageFixture)


class ExtraDhcpOptsCirrosServerStackFixture(CirrosServerStackFixture):
    use_extra_dhcp_opts = True


class CirrosNoFipServerStackFixture(ExtraDhcpOptsCirrosServerStackFixture):
    has_floating_ip = False
    network_stack = tobiko.required_fixture(_neutron.NetworkNoFipStackFixture)


class MultiIPCirrosServerStackFixture(CirrosServerStackFixture):
    template = _hot.heat_template_file('nova/multi_ip_test_stack.yaml')
    expected_creted_status = {heat.CREATE_IN_PROGRESS, heat.CREATE_COMPLETE}
    output_needs_stack_complete = False

    def cleanup_stack(self):
        self.delete_stack()
        # this is skipped for this stack: self.wait_until_stack_deleted()
