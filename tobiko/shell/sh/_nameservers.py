# Copyright 2020 Red Hat
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

from oslo_log import log
import netaddr

import tobiko
from tobiko.shell import sh
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


class ListNameserversFixture(tobiko.SharedFixture):

    ssh_client: typing.Optional[ssh.SSHClientFixture] = None
    filenames: typing.Optional[typing.Sequence[str]] = None

    nameservers: typing.Optional[tobiko.Selection[netaddr.IPAddress]] = None

    def __init__(self,
                 ssh_client: typing.Optional[ssh.SSHClientFixture] = None,
                 filenames: typing.Optional[typing.Iterable[str]] = None,
                 **execute_params):
        super(ListNameserversFixture, self).__init__()
        if ssh_client is not None:
            self.ssh_client = ssh_client
        if filenames is not None:
            self.filenames = list(filenames)
        self.execute_params = execute_params

    def setup_fixture(self):
        self.nameservers = list_nameservers(ssh_client=self.ssh_client,
                                            filenames=self.filenames,
                                            **self.execute_params)


def list_nameservers(ssh_client: typing.Optional[ssh.SSHClientFixture] = None,
                     filenames: typing.Optional[typing.Iterable[str]] = None,
                     ip_version: typing.Optional[int] = None,
                     **execute_params) -> \
        tobiko.Selection[netaddr.IPAddress]:
    if filenames is None:
        filenames = ['/etc/resolv.conf']

    nameservers: tobiko.Selection[netaddr.IPAddress] = tobiko.Selection()
    # obtain nameservers from the resolv.conf file
    for filename in filenames:
        nameservers.extend(parse_resolv_conf_file(ssh_client=ssh_client,
                                                  filename=filename,
                                                  **execute_params))

    # obtain nameservers from nmcli, if available
    try:
        sh.find_command('nmcli', ssh_client=ssh_client)
    except sh.CommandNotFound:
        msg = 'nmcli command not available'
        if ssh_client:
            msg += f' on {ssh_client.host}'
        LOG.debug(msg)
    else:
        nameservers.extend(parse_dns_nmcli(ssh_client=ssh_client))

    if ip_version:
        nameservers = nameservers.with_attributes(version=ip_version)
    return nameservers


def parse_resolv_conf_file(
        filename: str,
        ssh_client: typing.Optional[ssh.SSHClientFixture] = None,
        **execute_params) -> typing.Generator[netaddr.IPAddress, None, None]:
    lines: typing.List[str] = \
        sh.execute(f"cat '{filename}'",
                   ssh_client=ssh_client,
                   **execute_params).stdout.splitlines()
    for line in lines:
        for comment_sep in [';', '#']:
            if comment_sep in line:
                # Filter out comments
                line, _ = line.split(comment_sep, 1)
        # Filter out heading and trailing white spaces
        line = line.strip().lower()
        if not line:
            # Skip empty lines
            continue
        fields = line.split()
        if fields[0] == 'nameserver':
            for nameserver in fields[1:]:
                try:
                    yield netaddr.IPAddress(nameserver)
                except netaddr.AddrFormatError:
                    LOG.exception(f"Invalid nameserver address: {nameserver}")


def parse_dns_nmcli(
        ssh_client: typing.Optional[ssh.SSHClientFixture] = None) -> \
        typing.Generator[netaddr.IPAddress, None, None]:
    connections = sh.get_nm_connection_ids(ssh_client=ssh_client)
    for connection in connections:
        nameservers = sh.get_nm_connection_values(connection,
                                                  'IP4.DNS,IP6.DNS',
                                                  ssh_client=ssh_client)
        for nameserver in nameservers:
            try:
                yield netaddr.IPAddress(nameserver)
            except netaddr.AddrFormatError:
                LOG.exception(f"Invalid nameserver address: {nameserver}")
