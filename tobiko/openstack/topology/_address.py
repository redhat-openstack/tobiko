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

from collections import abc
import functools
import socket
import typing

import netaddr
from oslo_log import log

import tobiko


LOG = log.getLogger(__name__)


def list_addresses(obj,
                   ip_version: typing.Optional[int] = None,
                   port: typing.Union[int, str, None] = None,
                   ssh_config: bool = False) -> \
        tobiko.Selection[netaddr.IPAddress]:
    if isinstance(obj, tobiko.Selection):
        addresses = obj
    elif isinstance(obj, netaddr.IPAddress):
        addresses = tobiko.select([obj])
    elif isinstance(obj, str):
        addresses = tobiko.select(
            list_host_addresses(obj,
                                ip_version=ip_version,
                                port=port,
                                ssh_config=ssh_config))
    elif isinstance(obj, abc.Sequence):
        addresses = tobiko.Selection()
        for item in iter(obj):
            addresses.extend(list_addresses(item))
    else:
        raise TypeError(f'{obj} object is not of a valid address(es) type')

    if addresses and ip_version is not None:
        addresses = addresses.with_attributes(version=ip_version)
    return addresses


@functools.lru_cache()
def list_host_addresses(host: str,
                        ip_version: typing.Optional[int] = None,
                        port: typing.Union[int, str, None] = None,
                        ssh_config: bool = False) -> \
        tobiko.Selection[netaddr.IPAddress]:

    if not port:
        if ssh_config:
            port = 22  # use the default port for SSH protocol
        else:
            port = 0

    addresses: tobiko.Selection[netaddr.IPAddress] = tobiko.Selection()
    hosts = [host]
    resolved = set()
    while hosts:
        host = hosts.pop()
        if host in resolved:
            LOG.debug(f"Cyclic address resolution detected for host {host}")
            continue  # already resolved

        resolved.add(host)  # avoid resolving it again
        address = parse_ip_address(host)
        if address:
            addresses.append(address)
            continue

        # use socket host address resolution to get IP addresses
        addresses.extend(resolv_host_addresses(host=host,
                                               port=port,
                                               ip_version=ip_version))

    if [host] != [str(address) for address in addresses]:
        LOG.debug(f"Host '{host}' addresses resolved as: {addresses}")
    return addresses


def parse_ip_address(host: str) -> typing.Optional[netaddr.IPAddress]:
    try:
        return netaddr.IPAddress(host)
    except (netaddr.AddrFormatError, ValueError):
        return None


ADDRESS_FAMILIES = {
    4: socket.AF_INET,
    6: socket.AF_INET6,
    None: socket.AF_UNSPEC
}


# pylint: disable=no-member
AddressFamily = socket.AddressFamily
# pylint: enable=no-member


def get_address_family(ip_version: typing.Optional[int] = None) -> \
        AddressFamily:
    try:
        return ADDRESS_FAMILIES[ip_version]
    except KeyError:
        pass
    raise ValueError(f"{ip_version!r} is an invalid value for getting address "
                     "family")


IP_VERSIONS = {
    socket.AF_INET: 4,
    socket.AF_INET6: 6,
}


def resolv_host_addresses(host: str,
                          port: typing.Union[int, str] = 0,
                          ip_version: typing.Optional[int] = None) -> \
        typing.List[netaddr.IPAddress]:

    family = get_address_family(ip_version)
    proto = socket.AI_CANONNAME | socket.IPPROTO_TCP
    LOG.debug(f"Resolve IP addresses for host '{host}' "
              f"(port={port}, family={family}, proto={proto})'...")
    try:
        addrinfo = socket.getaddrinfo(host, port, family=family, proto=proto)
    except socket.gaierror as ex:
        LOG.debug(f"Can't resolve IP addresses for host '{host}': {ex}")
        return []

    addresses = []
    for _family, _, _, canonical_name, sockaddr in addrinfo:
        if family != socket.AF_UNSPEC and family != _family:
            LOG.error(f"Resolved address family '{_family}' 'of address "
                      f"'{sockaddr}' is not {family} "
                      f"(canonical_name={canonical_name}")
            continue

        address = parse_ip_address(sockaddr[0])
        if address is None:
            LOG.error(f"Resolved address '{sockaddr[0]}' is not a valid IP "
                      f"address (canonical_name={canonical_name})")
            continue

        if ip_version and ip_version != address.version:
            LOG.error(f"Resolved IP address version '{address.version}' of "
                      f"'{address}' is not {ip_version} "
                      f"(canonical_name={canonical_name})")
            continue

        addresses.append(address)
        LOG.debug(f"IP address for host '{host}' has been resolved as "
                  f"'{address}' (canonical_name={canonical_name})")

    if not addresses:
        LOG.debug(f"Host name '{host}' resolved to any IP address.")

    return addresses
