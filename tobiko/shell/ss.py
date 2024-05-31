# Copyright (c) 2022 Red Hat, Inc.
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

import netaddr
from oslo_log import log
import typing  # noqa

import tobiko
from tobiko.shell import sh
from tobiko.shell import ssh


class SocketLookupError(tobiko.TobikoException):
    message = ('ss command "{cmd}" failed with the error "{err}"')


class SockHeader():

    def __init__(self, header_str: str):
        self.header_str = header_str
        self.header: typing.List[str] = []
        self._parse_header()

    def _parse_header(self):
        if 'Netid' in self.header_str:
            self.header.append('protocol')
        if 'State' in self.header_str:
            self.header.append('state')
        if 'Recv-Q' in self.header_str:
            self.header.append('recv_q')
        if 'Send-Q' in self.header_str:
            self.header.append('send_q')
        if 'Local Address:Port' in self.header_str:
            self.header.append('local')
        if 'Peer Address:Port' in self.header_str:
            self.header.append('remote')
        if 'Process' in self.header_str:
            self.header.append('process')

    def extend_ports(self):
        """Add ports as separate header columns

        It might be useful while collecting information about unix sockets
        as unlke regular network sockets there are no ':' symbol between
        address and port. But the ' ' (space) symbol is used instead.
        """
        try:
            idx = self.header.index('local')
            self.header.pop(idx)
            self.header.insert(idx, 'local_addr')
            self.header.insert(idx+1, 'local_port')
        except ValueError:
            pass
        try:
            idx = self.header.index('remote')
            self.header.pop(idx)
            self.header.insert(idx, 'remote_addr')
            self.header.insert(idx+1, 'remote_port')
        except ValueError:
            pass

    def __len__(self):
        return len(self.header)

    def __iter__(self):
        yield from self.header


class SockLine(str):
    """Single line from the output of ss command line tool

    It should match with the corresponding table header that is presented by
    object of SockHeader class
    """


class SockData(dict):
    """A single socket information parsed from output of ss command line tool

    Output of ss command line tool should be parsed and stored in the dict
    with keys are items of the SockHeader object. In most of the cases it
    should contain the following keys:

    - protocol (optional)
    - state (optional)
    - recv_q
    - send_q
    - local_addr (IP or filename)
    - local_port
    - remote_addr (IP or filename)
    - remote_port
    - process (list of processes names)
    """


LOG = log.getLogger(__name__)


def _ss(params: str = '',
        ssh_client: ssh.SSHClientFixture = None,
        table_header: SockHeader = None,
        parser: typing.Callable[[SockHeader, SockLine], SockData] = None,
        **execute_params) -> typing.List[SockData]:
    execute_params.update({'sudo': True})
    sockets = []
    headers = None
    if table_header:
        # Predefined header might be necessary if the command is expected to
        # be executed in any kind of environments. Old versrions of `ss`
        # command line tool do not have 'Processes' column in header
        parsed_header = True
        headers = table_header
        command_line = "ss -Hnp {}".format(params)
    else:
        parsed_header = False
        command_line = "ss -np {}".format(params)
    try:
        stdout = sh.execute(command_line,
                            ssh_client=ssh_client,
                            **execute_params).stdout
    except sh.ShellCommandFailed as ex:
        if ex.stdout.startswith('Error'):
            raise SocketLookupError(cmd=command_line, err=ex.stderr) from ex
        if ex.exit_status > 0:
            raise
    for line in stdout.splitlines():
        if not parsed_header:
            headers = SockHeader(line)
            parsed_header = True
            continue
        sock_info = SockLine(line.strip())
        if parser and headers:
            try:
                sockets.append(parser(headers, sock_info))
            except ValueError as ex:
                LOG.error(str(ex))
                continue
        else:
            sockets.append(SockData({'raw_data': sock_info}))
    return sockets


def get_processes(processes: str) -> typing.List[str]:
    """Parse processes names from ss output

    The simpliest example of the proccesses suffix in ss output:

        users:(("httpd",pid=735448,fd=11))

    But it can be a bit more complex

        users:(("httpd",pid=4969,fd=53),("httpd",pid=3328,fd=53))

    Function return the list of all processes names ['httpd', 'httpd']
    """
    stack = []
    process_list = []
    nested = False
    for idx, symbol in enumerate(processes):
        if symbol == '(':
            stack.append(idx)
            nested = True
        elif symbol == ')' and len(stack) == 1:
            process_list.extend(get_processes(processes[stack[0]+1:idx]))
        elif symbol == ')':
            stack.pop()
    if not nested:
        process_list.append(processes.split('"', 2)[1])
    return process_list


def parse_tcp_socket(headers: SockHeader,
                     sock_info: SockLine) -> SockData:
    socket_details = SockData()
    sock_data = sock_info.split()
    if len(headers) != len(sock_data):
        msg = 'Unable to parse line: "{}"'.format(sock_info)
        raise ValueError(msg)
    for idx, header in enumerate(headers):
        if not header:
            continue
        if header == 'local' or header == 'remote':
            ip, port = sock_data[idx].strip().rsplit(':', 1)
            if ip == '*':
                ip = '0'
            socket_details['{}_addr'.format(header)] = netaddr.IPAddress(
                    ip.strip(']['))
            socket_details['{}_port'.format(header)] = port
        elif header == 'process':
            try:
                socket_details[header] = get_processes(sock_data[idx])
            except IndexError as ex:
                msg = 'Unable to parse processes part of the line: {}'.format(
                        sock_info)
                raise ValueError(msg) from ex
        else:
            socket_details[header] = sock_data[idx]
    return socket_details


def parse_unix_socket(headers: SockHeader,
                      sock_info: SockLine) -> SockData:
    socket_details = SockData()
    sock_data = sock_info.split()
    if len(headers) != len(sock_data):
        msg = 'Unable to parse line: "{}"'.format(sock_info)
        raise ValueError(msg)
    for idx, header in enumerate(headers):
        if not header:
            continue
        if header == 'process':
            try:
                socket_details[header] = get_processes(sock_data[idx])
            except IndexError as ex:
                msg = 'Unable to parse processes part of the line: {}'.format(
                        sock_info)
                raise ValueError(msg) from ex
        else:
            socket_details[header] = sock_data[idx]
    return socket_details


def tcp_listening(address: str = '',
                  port: str = '',
                  **exec_params) -> typing.List[SockData]:
    """List of tcp sockets in listening state

    Information can be filtered by local address and port and will be returned
    as a list of SockData object where the following keys should exist:

    - protocol (optional)
    - state (optional)
    - recv_q
    - send_q
    - local_addr (netaddr.IPAddress object)
    - local_port
    - remote_addr (netaddr.IPAddress object)
    - remote_port
    - process (list of processes names)
    """
    params = '-t state listening'
    ss_fields = SockHeader('Recv-Q Send-Q Local Address:Port'
                           'Peer Address:Port Process')
    if port:
        params += ' sport {}'.format(port)
    if address:
        params += ' src {}'.format(address)
    return _ss(params=params,
               table_header=ss_fields,
               parser=parse_tcp_socket,
               **exec_params)


def tcp_connected(src_address: str = '',
                  src_port: str = '',
                  dst_address: str = '',
                  dst_port: str = '',
                  **exec_params) -> typing.List[SockData]:
    params = '-t state connected'
    ss_fields = SockHeader('State Recv-Q Send-Q Local Address:Port'
                           'Peer Address:Port Process')
    if src_port:
        params += ' sport {}'.format(src_port)
    if src_address:
        params += ' src {}'.format(src_address)
    if dst_port:
        params += ' dport {}'.format(dst_port)
    if dst_address:
        params += ' dst {}'.format(dst_address)
    return _ss(params=params,
               table_header=ss_fields,
               parser=parse_tcp_socket,
               **exec_params)


def unix_listening(file_name: str = '',
                   **exec_params) -> typing.List[SockData]:
    """List of unix sockets in listening state

    Information can be filtered by file name and will be returned as a list of
    SockData object where the following keys should exist:

    - protocol (optional)
    - state (optional)
    - recv_q
    - send_q
    - local_addr (filename string)
    - local_port (should be ``*``)
    - remote_addr (filename string - should be ``*``)
    - remote_port (should be ``*``)
    - process (list of processes names)
    """
    params = '-x state listening'
    ss_fields = SockHeader('Netid Recv-Q Send-Q Local Address:Port'
                           'Peer Address:Port Process')
    ss_fields.extend_ports()
    if file_name:
        params += ' src {}'.format(file_name)
    return _ss(params=params,
               table_header=ss_fields,
               parser=parse_unix_socket,
               **exec_params)
