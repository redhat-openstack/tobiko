# Copyright (c) 2021 Red Hat, Inc.
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
from urllib import parse

import netaddr

import tobiko
from tobiko.shell import sh
from tobiko.shell import ssh


CURL_CONNECTION_ERRORS = {
    7,   # Connection refused
    22,  # 404 Not Found
    28,  # Connection timedout
}


def execute_curl(
        hostname: typing.Union[str, netaddr.IPAddress] = None,
        port: int = None,
        path: str = None,
        scheme: str = None,
        ssh_client: ssh.SSHClientType = None,
        connect_timeout: tobiko.Seconds = None,
        fail_silently: bool = True,
        retry_count: int = None,
        retry_timeout: tobiko.Seconds = None,
        retry_interval: tobiko.Seconds = None,
        **execute_params) -> str:
    """Execute curl command

    Returns the command output in case of success,
    raises ShellCommandFailed otherwise.
    """
    netloc = make_netloc(hostname=hostname, port=port)
    url = make_url(scheme=scheme, netloc=netloc, path=path)
    command = sh.shell_command('curl -g')
    if fail_silently:
        command += '-f'
    if connect_timeout is not None:
        command += f'--connect-timeout {int(connect_timeout)}'
    command += url
    for attempt in tobiko.retry(count=retry_count,
                                timeout=retry_timeout,
                                interval=retry_interval,
                                default_count=1,
                                default_timeout=60.,
                                default_interval=1.):
        try:
            return sh.execute(command, ssh_client=ssh_client,
                              **execute_params).stdout
        except sh.ShellCommandFailed as ex:
            if ex.exit_status in CURL_CONNECTION_ERRORS:
                # Retry on connection errors
                attempt.check_limits()
            else:
                raise
    raise RuntimeError('Unexpected failure')


def make_netloc(
        hostname: typing.Union[str, netaddr.IPAddress, None] = None,
        port: typing.Optional[int] = None,
        username: typing.Optional[str] = None,
        password: typing.Optional[str] = None) -> str:
    if not hostname:
        return ''
    try:
        ip_address = netaddr.IPAddress(hostname)
    except netaddr.AddrFormatError:
        tobiko.check_valid_type(hostname, str)
        netloc = hostname
    else:
        if ip_address.version == 6:
            # Add square brackets around IPv6 address to please curl
            netloc = f'[{hostname}]'
        else:
            netloc = str(hostname)
    if port is not None:
        netloc = f'{netloc}:{port}'
    if username is not None:
        if password is not None:
            netloc = f'{username}:{password}@{netloc}'
        else:
            netloc = f'{username}@{netloc}'
    return netloc


def make_url(scheme: typing.Optional[str] = None,
             netloc: typing.Optional[str] = None,
             path: typing.Optional[str] = None) -> str:
    return parse.SplitResult(scheme=(scheme or 'http').lower(),
                             netloc=netloc or '',
                             path=path or '',
                             query='',
                             fragment='').geturl()
