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

from oslo_log import log

from tobiko.shell.iperf3 import _parameters
from tobiko.shell import sh


LOG = log.getLogger(__name__)


def get_iperf3_client_command(parameters: _parameters.Iperf3ClientParameters):
    interface = Iperf3Interface()
    return interface.get_iperf3_client_command(parameters)


def get_iperf3_server_command(parameters: _parameters.Iperf3ServerParameters):
    interface = Iperf3Interface()
    return interface.get_iperf3_server_command(parameters)


class Iperf3Interface:

    def get_iperf3_client_command(
            self,
            parameters: _parameters.Iperf3ClientParameters) \
            -> sh.ShellCommand:
        options = self.get_iperf3_client_options(parameters=parameters)
        return sh.shell_command('iperf3') + options

    def get_iperf3_server_command(
            self,
            parameters: _parameters.Iperf3ServerParameters) \
            -> sh.ShellCommand:
        options = self.get_iperf3_server_options(parameters=parameters)
        return sh.shell_command('iperf3') + options

    def get_iperf3_client_options(
            self,
            parameters: _parameters.Iperf3ClientParameters) \
            -> sh.ShellCommand:
        options = sh.ShellCommand(['-J'])
        options += self.get_client_mode_option(parameters.address)
        if parameters.port is not None:
            options += self.get_port_option(parameters.port)
        if parameters.timeout is not None:
            options += self.get_timeout_option(parameters.timeout)
        if parameters.bitrate is not None:
            options += self.get_bitrate_option(parameters.bitrate)
        if parameters.download is not None:
            options += self.get_download_option(parameters.download)
        if parameters.protocol is not None:
            options += self.get_protocol_option(parameters.protocol)
        if parameters.interval is not None:
            options += self.get_interval_option(parameters.interval)
        if parameters.json_stream is not None:
            options += self.get_json_stream_option(parameters.json_stream)
        if parameters.logfile is not None:
            options += self.get_logfile_option(parameters.logfile)
        return options

    def get_iperf3_server_options(
            self,
            parameters: _parameters.Iperf3ServerParameters) \
            -> sh.ShellCommand:
        options = sh.ShellCommand(['-J'])
        options += self.get_server_mode_option()
        if parameters.port is not None:
            options += self.get_port_option(parameters.port)
        if parameters.protocol is not None:
            options += self.get_protocol_option(parameters.protocol)
        return options

    @staticmethod
    def get_bitrate_option(bitrate: int):
        return ['-b', max(0, bitrate)]

    @staticmethod
    def get_client_mode_option(server_address: str):
        return ['-c', server_address]

    @staticmethod
    def get_server_mode_option():
        return ["-s"]

    @staticmethod
    def get_download_option(download: bool):
        if download:
            return ['-R']
        else:
            return []

    @staticmethod
    def get_protocol_option(protocol: str):
        if protocol == 'tcp':
            return []
        elif protocol == 'udp':
            return ['-u']
        else:
            raise ValueError('iperf3 protocol values allowed: [tcp|udp]')

    @staticmethod
    def get_interval_option(interval: int):
        return ['-i', interval]

    @staticmethod
    def get_timeout_option(timeout: int):
        if timeout >= 0:
            return ['-t', timeout]
        else:
            return []

    @staticmethod
    def get_port_option(port):
        return ['-p', port]

    @staticmethod
    def get_json_stream_option(json_stream: bool):
        # NOTE: when iperf3 is run with --json-stream, new json
        # entries are written for every interval
        # This option is supported from iperf3 version 3.17:
        if json_stream:
            return ['--json-stream']
        else:
            return []

    @staticmethod
    def get_logfile_option(logfile):
        return ['--logfile', logfile]
