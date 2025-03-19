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

import socket
import typing
import weakref

import tobiko
from tobiko.shell.sh import _exception
from tobiko.shell.sh import _execute
from tobiko.shell import ssh


class HostnameError(tobiko.TobikoException):
    message = "Unable to get hostname from host: {error}"


HOSTNAMES_CACHE: typing.MutableMapping[typing.Optional[ssh.SSHClientFixture],
                                       str] = weakref.WeakKeyDictionary()
HOSTNAMES_FQDN_CACHE: \
    typing.MutableMapping[typing.Optional[ssh.SSHClientFixture],
                          str] = weakref.WeakKeyDictionary()


def get_hostname(ssh_client: ssh.SSHClientType = None,
                 cached=True,
                 fqdn=False,
                 **execute_params) -> str:
    ssh_client = ssh.ssh_client_fixture(ssh_client)
    if ssh_client is None:
        return socket.gethostname()

    if cached:
        try:
            if not fqdn:
                hostname = HOSTNAMES_CACHE[ssh_client]
            else:
                hostname = HOSTNAMES_FQDN_CACHE[ssh_client]
        except KeyError:
            pass
        else:
            return hostname

    hostname = ssh_hostname(ssh_client=ssh_client,
                            fqdn=fqdn,
                            **execute_params)
    if cached:
        if not fqdn:
            HOSTNAMES_CACHE[ssh_client] = hostname
        else:
            HOSTNAMES_FQDN_CACHE[ssh_client] = hostname
    return hostname


def ssh_hostname(ssh_client: ssh.SSHClientFixture,
                 fqdn=False,
                 **execute_params) \
        -> str:
    tobiko.check_valid_type(ssh_client, ssh.SSHClientFixture)
    command = 'hostname'
    if fqdn:
        command += ' -f'
    try:
        result = _execute.execute(command,
                                  ssh_client=ssh_client,
                                  **execute_params)
    except _exception.ShellCommandFailed as ex:
        raise HostnameError(error=ex.stderr) from ex

    line: str
    for line in result.stdout.splitlines():
        hostname = line.strip()
        if hostname:
            break
    else:
        raise HostnameError(error=f"Invalid result: '{result}'")
    return hostname
