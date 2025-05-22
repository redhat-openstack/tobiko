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

import netaddr

import tobiko


class Iperf3ClientParameters(typing.NamedTuple):
    address: str
    bitrate: typing.Optional[int] = None
    download: typing.Optional[bool] = None
    port: typing.Optional[int] = None
    protocol: typing.Optional[str] = None
    timeout: typing.Optional[int] = None
    interval: typing.Optional[int] = None
    json_stream: typing.Optional[bool] = None
    logfile: typing.Optional[str] = None


class Iperf3ServerParameters(typing.NamedTuple):
    port: typing.Optional[int] = None
    protocol: typing.Optional[str] = None


def iperf3_client_parameters(
        address: typing.Union[str, netaddr.IPAddress],
        bitrate: int = None,
        download: bool = None,
        port: int = None,
        protocol: str = None,
        timeout: int = None,
        interval: int = None,
        json_stream: bool = None,
        logfile: str = None):
    """Get iperf3 client parameters
    mode allowed values: client or server
    ip is only needed for client mode
    """
    config = tobiko.tobiko_config().iperf3
    if isinstance(address, netaddr.IPAddress):
        address = str(address)
    if bitrate is None:
        bitrate = config.bitrate
    if download is None:
        download = config.download
    if port is None:
        port = config.port
    if protocol is None:
        protocol = config.protocol
    if timeout is None:
        timeout = config.timeout
    if interval is None:
        interval = config.interval
    return Iperf3ClientParameters(address=address,
                                  bitrate=bitrate,
                                  download=download,
                                  port=port,
                                  protocol=protocol,
                                  timeout=timeout,
                                  interval=interval,
                                  json_stream=json_stream,
                                  logfile=logfile)


def iperf3_server_parameters(
        port: int = None, protocol: str = None) -> Iperf3ServerParameters:
    """Get iperf3 server parameters
    """
    config = tobiko.tobiko_config().iperf3
    if port is None:
        port = config.port
    if protocol is None:
        protocol = config.protocol
    return Iperf3ServerParameters(port=port,
                                  protocol=protocol)
