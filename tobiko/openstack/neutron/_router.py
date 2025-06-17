# Copyright 2019 Red Hat
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
import json

from oslo_log import log

import tobiko
from tobiko.openstack.neutron import _agent
from tobiko.openstack.neutron import _client
from tobiko.openstack.neutron import _network
from tobiko.openstack.neutron import _port
from tobiko.openstack.neutron import _subnet


LOG = log.getLogger(__name__)


RouterType = typing.Dict[str, typing.Any]
RouterIdType = typing.Union[str, RouterType]


def get_router_id(router: RouterIdType) -> str:
    if isinstance(router, str):
        return router
    else:
        return router['id']


def get_router(router: RouterIdType, client=None, **params) -> RouterType:
    router_id = get_router_id(router)
    try:
        return _client.neutron_client(client).show_router(
            router_id, **params)['router']
    except _client.NotFound as ex:
        raise NoSuchRouter(id=router_id) from ex


def create_router(client: _client.NeutronClientType = None,
                  network: _network.NetworkIdType = None,
                  add_cleanup=True,
                  **params) -> RouterType:
    if 'external_gateway_info' not in params:
        if network is None:
            from tobiko.openstack import stacks
            network_id = stacks.get_floating_network_id()
        else:
            network_id = _network.get_network_id(network)
        params['external_gateway_info'] = dict(network_id=network_id)
    router = _client.neutron_client(client).create_router(
        body={'router': params})['router']
    if add_cleanup:
        tobiko.add_cleanup(cleanup_router, router=router, client=client)
    return router


def cleanup_router(router: RouterIdType,
                   client: _client.NeutronClientType = None):
    try:
        delete_router(router=router, client=client)
    except NoSuchRouter:
        pass


def delete_router(router: RouterIdType,
                  client: _client.NeutronClientType = None):
    router_id = get_router_id(router)
    try:
        _client.neutron_client(client).delete_router(router_id)
    except _client.NotFound as ex:
        raise NoSuchRouter(id=router_id) from ex


def wait_for_master_and_backup_agents(
        router: RouterIdType,
        unique_master: bool = True,
        timeout: tobiko.Seconds = None,
        interval: tobiko.Seconds = None) -> \
        typing.Tuple[typing.Dict, typing.List[typing.Dict]]:
    router_id = get_router_id(router)
    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval,
                                default_timeout=300.,
                                default_interval=3.):
        router_agents = _agent.list_l3_agent_hosting_routers(router_id)
        master_agents = router_agents.with_items(ha_state='active')
        if master_agents:
            LOG.debug(
                f"Router '{router_id}' has {len(master_agents)} master "
                "agent(s):\n"
                f"{json.dumps(master_agents, indent=4, sort_keys=True)}")
        backup_agents = router_agents.with_items(ha_state='standby')
        if backup_agents:
            LOG.debug(
                f"Router '{router_id}' has {len(backup_agents)} backup "
                "agent(s)):\n"
                f"{json.dumps(backup_agents, indent=4, sort_keys=True)}")
        other_agents = [agent
                        for agent in router_agents
                        if (agent not in master_agents + backup_agents)]
        if other_agents:
            LOG.debug(
                f"Router '{router_id}' has {len(other_agents)} other "
                "agent(s):\n"
                f"{json.dumps(master_agents, indent=4, sort_keys=True)}")
        try:
            if unique_master:
                master_agent = master_agents.unique
            else:
                master_agent = master_agents.first
        except (tobiko.MultipleObjectsFound, tobiko.ObjectNotFound):
            attempt.check_limits()
        else:
            break
    else:
        raise RuntimeError("tobiko retry loop ended before break?")

    return master_agent, backup_agents


RouterInterfaceType = typing.Dict[str, typing.Any]


def add_router_interface(router: RouterIdType,
                         subnet: _subnet.SubnetIdType = None,
                         port: _port.PortIdType = None,
                         client: _client.NeutronClientType = None,
                         add_cleanup=True,
                         **params) -> RouterInterfaceType:
    router_id = get_router_id(router)
    if 'port_id' not in params and port is not None:
        params['port_id'] = _port.get_port_id(port)
    elif 'subnet_id' not in params and subnet is not None:
        params['subnet_id'] = _subnet.get_subnet_id(subnet)
    interface = _client.neutron_client(client).add_interface_router(
        router=router_id, body=params)
    if add_cleanup:
        tobiko.add_cleanup(cleanup_router_interface, router=router,
                           subnet=subnet, port=port, client=client)
    return interface


def cleanup_router_interface(router: RouterIdType,
                             subnet: _subnet.SubnetIdType = None,
                             port: _port.PortIdType = None,
                             client: _client.NeutronClientType = None,
                             **params):
    try:
        remove_router_interface(router=router, subnet=subnet,
                                port=port, client=client, **params)
    except tobiko.ObjectNotFound:
        pass


def remove_router_interface(router: RouterIdType,
                            subnet: _subnet.SubnetIdType = None,
                            port: _port.PortIdType = None,
                            client: _client.NeutronClientType = None,
                            **params):
    router_id = get_router_id(router)
    if 'port_id' not in params and port is not None:
        params['port_id'] = _port.get_port_id(port)
    elif 'subnet_id' not in params and subnet is not None:
        params['subnet_id'] = _subnet.get_subnet_id(subnet)
    try:
        _client.neutron_client(client).remove_interface_router(
            router=router_id, body=params)
    except _client.NotFound as ex:
        raise tobiko.ObjectNotFound() from ex


def update_router(router: RouterIdType, client=None, **params) -> RouterType:
    router_id = get_router_id(router)
    reply = _client.neutron_client(client).update_router(
        router_id, body={'router': params})
    return reply['router']


class NoSuchRouter(tobiko.ObjectNotFound):
    message = "No such router found for {id!r}"


def get_ovs_router_namespace(router: RouterIdType):
    return f"qrouter-{get_router_id(router)}"
