# Copyright 2021 Red Hat
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
import json
import typing

import tobiko
from tobiko.openstack.topology import _topology
from tobiko.shell import ip


def get_hosts_namespaces(hostnames: typing.Iterable[str] = None,
                         **params) \
        -> typing.Dict[str, typing.List[str]]:
    if isinstance(hostnames, str):
        hostnames = [hostnames]
    namespaces = collections.defaultdict(list)
    nodes = _topology.list_openstack_nodes(hostnames=hostnames,
                                           **params)
    for node in nodes:
        for namespace in ip.list_network_namespaces(
                ssh_client=node.ssh_client):
            namespaces[namespace].append(node.hostname)
    return namespaces


def wait_for_namespace_in_hosts(*namespaces: str,
                                hostnames: typing.Iterable[str] = None,
                                timeout: tobiko.Seconds = None,
                                count: int = None,
                                interval: tobiko.Seconds = None,
                                present=True,
                                **params):
    for attempt in tobiko.retry(timeout=timeout,
                                count=count,
                                interval=interval,
                                default_timeout=60.,
                                default_interval=3.):
        try:
            if present:
                assert_namespace_in_hosts(*namespaces,
                                          hostnames=hostnames,
                                          **params)
            else:
                assert_namespace_not_in_hosts(*namespaces,
                                              hostnames=hostnames,
                                              **params)
        except tobiko.FailureException:  # type: ignore
            if attempt.is_last:
                raise
        else:
            break


def assert_namespace_in_hosts(*namespaces: str,
                              hostnames: typing.Iterable[str] = None,
                              **params):
    actual_namespaces = get_hosts_namespaces(hostnames=hostnames,
                                             **params)
    missing = set(namespaces) - set(actual_namespaces)
    if missing:
        actual_hostnames = sorted(set(
            _hostname
            for _hostnames in actual_namespaces.values()
            for _hostname in _hostnames))
        tobiko.fail(f"Network namespace(s) {sorted(missing)} missing in "
                    f"host(s) {actual_hostnames!r}")


def assert_namespace_not_in_hosts(*namespaces: str,
                                  hostnames: typing.Iterable[str] = None,
                                  **params):
    unexpected_namespaces = collections.defaultdict(list)
    actual_namespaces = get_hosts_namespaces(hostnames=hostnames, **params)
    for namespace, hostnames in actual_namespaces.items():
        if namespace in sorted(set(namespaces)):
            for hostname in hostnames:
                unexpected_namespaces[hostname].append(namespace)
    if unexpected_namespaces:
        dump = json.dumps(unexpected_namespaces, indent=4, sort_keys=True)
        tobiko.fail(f"Unexpected network namespace(s) found in "
                    f"host(s):\n{dump}")
