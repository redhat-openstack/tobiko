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

import collections
import typing

import netaddr
from oslo_log import log


LOG = log.getLogger(__name__)

PingAddressType = typing.Union[str, netaddr.IPAddress]


class PingParameters(collections.namedtuple('PingParameters',
                                            ['host',
                                             'count',
                                             'deadline',
                                             'fragmentation',
                                             'interval',
                                             'ip_version',
                                             'packet_size',
                                             'source',
                                             'timeout',
                                             'network_namespace'])):
    """Recollect parameters to be used to format ping command line

    PingParameters class is a data model recollecting parameters used to
    create a ping command line. It provides the feature of copying default
    values from another instance of PingParameters passed using constructor
    parameter 'default'.
    """


PING_PARAMETERS_NAMES = PingParameters._fields


def get_ping_parameters(default=None, **ping_params):
    """Get ping parameters eventually merging them with given extra parameters

    The only difference with init_parameters function is that in case
    default parameter is not None not any extra parameters is given, then
    it simply return given default instance, without performing any validation.
    """
    if default and not ping_params:
        return default
    else:
        return ping_parameters(default=default, **ping_params)


def ping_parameters(default=None, count=None, deadline=None,
                    fragmentation=None,
                    host: typing.Optional[PingAddressType] = None,
                    interval=None, ip_version=None, packet_size=None,
                    source=None, timeout=None, network_namespace=None):
    """Validate parameters and initialize a new PingParameters instance

    :param default: (PingParameters or None) instance from where to take
        default values when other value is not provided. If None (that is the
        default value) it will copy default parameters from
        DEFAULT_PING_PARAMETERS
    :param count: (int or None) number of ping ICMP message expecting to be
        received before having a success. Default value can be configured using
        'count' option in [ping] config section.
    :param host: (str or None) IP address or host name to send ICMP
        messages to. It is required to format a valid ping command, therefore
        no default value exists for this parameter.
    :param deadline: (int or None) positive number representing the maximum
        number of seconds ping command can send ICMP messages before stop
        executing. Default value can be configured using 'deadline' option in
        [ping] config section.
    :param fragmentation: (bool or None) when False this would tell ping
        to forbid ICMP messages fragmentation. Default value can be configured
        using 'fragmentation' option in [ping] config section. Fragmentation
        can't be disabled when using ping provided by BusyBox (IE with CirrOS
        images).
    :param interval: (int or None) interval of time before sending following
        ICMP message. Default value can be configured using 'interval' option
        in [ping] config section.
    :param ip_version: (4, 6 or None) If not None it makes sure it will
        use specified IP version for sending ICMP packages.
    :param packet_size: (int or None) if not None, it specifies the total ICMP
        message size (headers + payload).
    :param source: (str or None) IP address or interface name from where
        to send ICMP message.
    :param timeout: (int or None) time in seconds after which ping operation
        would raise PingFailed exception.
    :raises TypeError: in case some parameter cannot be converted to right
        expected type
    :raises ValueError: in case some parameter has an unexpected value
    """

    if default is None:
        default = default_ping_parameters()

    return PingParameters(
        count=get_positive_integer('count', count, default),
        host=get_address('host', host, default),
        deadline=get_positive_integer('deadline', deadline, default),
        fragmentation=get_boolean('fragmentation', fragmentation, default),
        interval=get_positive_integer('interval', interval, default),
        ip_version=get_positive_integer('ip_version', ip_version, default),
        packet_size=get_positive_integer('packet_size', packet_size, default),
        source=get_address('source', source, default),
        timeout=get_positive_integer('timeout', timeout, default),
        network_namespace=get_string('network_namespace', network_namespace,
                                     default))


def default_ping_parameters():
    from tobiko import config
    CONF = config.CONF
    return ping_parameters(default=False,
                           count=CONF.tobiko.ping.count,
                           deadline=CONF.tobiko.ping.deadline,
                           fragmentation=CONF.tobiko.ping.fragmentation,
                           interval=CONF.tobiko.ping.interval,
                           packet_size=CONF.tobiko.ping.packet_size,
                           timeout=CONF.tobiko.ping.timeout)


def get_ping_ip_version(parameters):
    ip_version = parameters.ip_version
    if ip_version is not None:
        ip_version = int(ip_version)
        if ip_version not in [4, 6]:
            message = "Invalid IP version: {!r}".format(ip_version)
            raise ValueError(message)
    for address in [parameters.host, parameters.source]:
        if isinstance(address, netaddr.IPAddress):
            if ip_version != address.version:
                if ip_version:
                    meassage = ("{!s} address IP version is not {!r}"
                                ).format(address, ip_version)
                    raise ValueError(meassage)
                ip_version = address.version
    return ip_version


def get_ping_payload_size(parameters):
    packet_size = parameters.packet_size
    if packet_size is None:
        return None

    header_size = get_ping_header_size(parameters)
    if packet_size < header_size:
        message = ("packet size {packet_size!s} can't be smaller than "
                   "header size {header_size!s}").format(
                       packet_size=packet_size,
                       header_size=header_size)
        raise ValueError(message)
    return packet_size - header_size


def get_positive_integer(name, value, default=None):
    if value is None and default:
        return get_positive_integer(name, getattr(default, name))
    if value is not None:
        value = int(value)
        if value < 0:
            message = "{!r} value must be zero or greater: {!r}".format(
                name, value)
            raise ValueError(message)
    return value


def get_boolean(name, value, default=None):
    if value is None and default:
        return get_boolean(name, getattr(default, name))
    if value is not None:
        value = bool(value)
    return value


def get_address(name: str, value: typing.Optional[PingAddressType],
                default=None) -> typing.Optional[PingAddressType]:
    if value is None:
        if default:
            return get_address(name, getattr(default, name))
        else:
            return None
    if isinstance(value, netaddr.IPAddress):
        return value
    elif isinstance(value, str):
        try:
            return netaddr.IPAddress(value)
        except netaddr.core.AddrFormatError:
            # NOTE: value may be an host name so this is fine
            return value
    else:
        raise TypeError(f"Object '{value}' is not a valid address")


def get_string(name, value, default=None):
    if value is None and default:
        return get_string(name, getattr(default, name))
    if value is not None:
        value = str(value)
    return value


IP_HEADER_SIZE = {4: 20, 6: 40}
ICMP_HEADER_SIZE = {4: 8, 6: 4}


def get_ping_header_size(parameters):
    ip_version = get_ping_ip_version(parameters)
    if ip_version is None:
        message = "can't get ICMP header size without knowing IP version"
        raise ValueError(message)

    if ip_version not in IP_HEADER_SIZE or ip_version not in ICMP_HEADER_SIZE:
        message = "Invalid IP version: {!r}".format(ip_version)
        raise ValueError(message)

    return IP_HEADER_SIZE[ip_version] + ICMP_HEADER_SIZE[ip_version]
