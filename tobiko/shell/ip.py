# Copyright (c) 2019 Red Hat, Inc.
#
# All Rights Reserved.
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
from tobiko.shell import sh


LOG = log.getLogger(__name__)


class IpError(tobiko.TobikoException):
    message = ("Unable to get IP addresses from host "
               "(exit_status={exit_status!r}): {error!s}")


INETS = {
    4: ['inet'],
    6: ['inet6'],
    None: ['inet', 'inet6']
}


def list_ip_addresses(ip_version: int = None,
                      device: str = None,
                      scope: str = None,
                      **execute_params) -> \
        tobiko.Selection[netaddr.IPAddress]:
    inets = INETS.get(ip_version)
    if inets is None:
        error = "invalid IP version: {!r}".format(ip_version)
        raise IpError(error=error)

    command = ['-o', 'address', 'list']
    if device is not None:
        tobiko.check_valid_type(device, str)
        command.append(device)
    output = execute_ip(command, **execute_params)

    ips: tobiko.Selection[netaddr.IPAddress] = tobiko.Selection()
    if output:
        for line in output.splitlines():
            fields = line.strip().split()
            inet = fields[2]
            if inet not in inets:
                continue  # List only address of selected IP version

            if scope:
                try:
                    scope_index = fields.index('scope')
                    if fields[scope_index + 1] != scope:
                        continue
                except (IndexError, ValueError):
                    continue

            address, _ = parse_ip_address(fields[3])
            ips.append(address)
    return ips


def find_ip_address(ip_version: int = None,
                    device: str = None,
                    scope: str = None,
                    unique: bool = False,
                    **execute_params) -> \
        netaddr.IPAddress:
    ips = list_ip_addresses(ip_version=ip_version,
                            device=device,
                            scope=scope,
                            **execute_params)
    if unique:
        return ips.unique
    else:
        return ips.first


def parse_ip_address(text: str) -> typing.Tuple[netaddr.IPAddress, int]:
    address = text
    if '/' in text:
        # Remove netmask prefix length
        address, prefix_len_text = text.split('/', 1)
        prefix_len = int(prefix_len_text)
    else:
        prefix_len = 0
    return netaddr.IPAddress(address), prefix_len


def list_network_namespaces(**execute_params) -> tobiko.Selection[str]:
    namespaces = tobiko.Selection[str]()
    output = execute_ip(['-o', 'netns', 'list'], **execute_params)
    if output:
        for line in output.splitlines():
            fields = line.strip().split()
            namespace = fields[0]
            namespaces.append(namespace)
    return namespaces


def list_network_interfaces(**execute_params) -> tobiko.Selection[str]:
    interfaces = tobiko.Selection[str]()
    output = execute_ip(['--brief', 'address', 'list'], **execute_params)
    if output:
        for line in output.splitlines():
            fields = line.strip().split()
            interface = fields[0]
            interfaces.append(interface)
    return interfaces


def get_network_main_route_device(dest_ip, **execute_params):
    output = execute_ip(['route', 'get', dest_ip], **execute_params)
    if output:
        for line in output.splitlines():
            fields = line.strip().split()
            device_index = fields.index('dev') + 1
            return fields[device_index]


IP_COMMAND = sh.shell_command(['/sbin/ip'])


def execute_ip(ifconfig_args, ip_command=None, ignore_errors=False,
               **execute_params) -> str:
    if ip_command:
        ip_command = sh.shell_command(ip_command)
    else:
        ip_command = IP_COMMAND
    command = ip_command + ifconfig_args
    result = sh.execute(command, stdin=False, stdout=True, stderr=True,
                        expect_exit_status=None, **execute_params)
    if not ignore_errors and result.exit_status:
        raise IpError(error=result.stderr, exit_status=result.exit_status)
    return result.stdout
