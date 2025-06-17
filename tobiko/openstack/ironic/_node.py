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

import typing

import ironicclient.v1.client
from oslo_log import log

import tobiko
from tobiko.openstack.ironic import _client


LOG = log.getLogger(__name__)

IronicNode = typing.Union[ironicclient.v1.node.Node]
IronicNodeType = typing.Union[str, IronicNode]


def get_node_id(node: typing.Optional[IronicNodeType] = None,
                node_id: typing.Optional[str] = None) -> str:
    if node_id is None:
        if isinstance(node, str):
            node_id = node
        else:
            assert node is not None
            node_id = node.uuid
    return node_id


def get_node(node: typing.Optional[IronicNodeType] = None,
             node_id: typing.Optional[str] = None,
             client: _client.IronicClientType = None,
             **params) -> IronicNode:
    node_id = get_node_id(node=node, node_id=node_id)
    return _client.ironic_client(client).node.get(node_id, **params)


class WaitForNodePowerStateError(tobiko.TobikoException):
    message = ("Node {node_id} not changing power state from "
               "{node_power_state} to {power_state}")


class WaitForNodePowerStateTimeout(WaitForNodePowerStateError):
    message = ("Node {node_id} didn't change its state from "
               "{node_power_state} to {power_state} state after "
               "{timeout} seconds")


IRONIC_NODE_TRANSIENT_POWER_STATES: typing.Dict[str, typing.List[str]] = {
    'power on': ['power off'],
    'power off': ['power on'],
}


def wait_for_node_power_state(
        node: IronicNodeType,
        power_state: str,
        client: _client.IronicClientType = None,
        timeout: tobiko.Seconds = None,
        sleep_time: tobiko.Seconds = None,
        transient_status: typing.Optional[typing.List[str]] = None) -> \
            IronicNode:
    if transient_status is None:
        transient_status = IRONIC_NODE_TRANSIENT_POWER_STATES.get(
            power_state) or []
    node_id = get_node_id(node)
    for attempt in tobiko.retry(timeout=timeout,
                                interval=sleep_time,
                                default_timeout=300.,
                                default_interval=3.):
        _node = get_node(node_id=node_id, client=client)
        if _node.power_state == power_state:
            break
        if _node.power_state not in transient_status:
            raise WaitForNodePowerStateError(
                node_id=node_id,
                node_power_state=_node.power_state,
                power_state=power_state)
        if attempt.is_last:
            raise WaitForNodePowerStateTimeout(
                node_id=node_id,
                node_power_state=_node.power_state,
                power_state=power_state,
                timeout=timeout)

        LOG.debug(f"Waiting for Ironic node '{node_id}' power state to get "
                  f"from {_node.power_state} to {power_state}...")
    else:
        raise RuntimeError("Retry look break before timing out")

    return _node


def power_off_node(node: IronicNodeType,
                   soft=False,
                   client: _client.IronicClientType = None,
                   timeout: tobiko.Seconds = None,
                   sleep_time: tobiko.Seconds = None) \
        -> IronicNode:
    client = _client.ironic_client(client)
    node = get_node(node=node, client=client)
    if node.power_state == 'power off':
        return node

    LOG.info(f"Power off baremetal node '{node.uuid}' "
             f"(power state = '{node.power_state}').")
    client.node.set_power_state(node.uuid,
                                state='off',
                                soft=soft)
    return wait_for_node_power_state(node=node.uuid,
                                     power_state='power off',
                                     client=client,
                                     timeout=timeout,
                                     sleep_time=sleep_time)


def power_on_node(node: IronicNodeType,
                  client: _client.IronicClientType = None,
                  timeout: tobiko.Seconds = None,
                  sleep_time: tobiko.Seconds = None) -> \
        IronicNode:
    client = _client.ironic_client(client)
    node = get_node(node=node, client=client)
    if node.power_state == 'power on':
        return node

    LOG.info(f"Power on baremetal node '{node.uuid}' "
             f"(power_state='{node.power_state}').")
    client.node.set_power_state(node_id=node.uuid,
                                state='on')
    return wait_for_node_power_state(node=node.uuid,
                                     power_state='power on',
                                     client=client,
                                     timeout=timeout,
                                     sleep_time=sleep_time)
