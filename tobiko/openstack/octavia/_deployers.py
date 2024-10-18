# Copyright (c) 2023 Red Hat
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

import tobiko
from tobiko import config
from tobiko.openstack import octavia
from tobiko.openstack import neutron
from tobiko.openstack.octavia import _constants

CONF = config.CONF
LOG = log.getLogger(__name__)


def get_external_subnet(ip_version=4):
    kw = {'router:external': True}
    if len(neutron.list_networks(**{'router:external': True})) > 1:
        kw['name'] = CONF.tobiko.neutron.external_network

    try:
        ext_subnet_list = neutron.find_network(**kw)['subnets']
    except tobiko.ObjectNotFound:
        LOG.warning('External network not found')
        return None

    for ext_subnet_id in ext_subnet_list:
        try:
            subnet = neutron.find_subnet(id=ext_subnet_id,
                                         ip_version=ip_version)
        except tobiko.ObjectNotFound:
            continue
        else:
            return subnet

    LOG.warning('External subnet with IP version %d not found', ip_version)


def deploy_ipv4_lb(provider: str,
                   protocol: str,
                   protocol_port: int,
                   lb_algorithm: str,
                   servers_stacks=None):
    """Deploy a populated ipv4 LB

    :param provider: the loadbalancer provider. For example: amphora
    :param protocol: the listener & pool protocol. For example: HTTP
    :param protocol_port: the load balancer protocol port
    :param lb_algorithm: the pool load balancing protocol. For example:
        ROUND_ROBIN
    :param servers_stacks: a list of server stacks (until we remove heat
        entirely)
    :return: all Octavia resources it has created (LB, listener, and pool)
    """
    lb_name = octavia.OCTAVIA_PROVIDERS_NAMES['lb'][provider]
    lb = octavia.find_load_balancer(lb_name)
    if lb:
        LOG.debug(f'Loadbalancer {lb.id} already exists. Skipping its'
                  ' creation')
    else:
        subnet = get_external_subnet()
        if subnet is None:
            tobiko.skip_test('Replacing heat networking resources for '
                             'octavia in tobiko wasn\'t implemented yet')
        lb_kwargs = {
            'provider': provider,
            'vip_subnet_id': subnet['id'],
            'name': lb_name
        }
        lb = octavia.create_load_balancer(lb_kwargs)
        octavia.wait_for_status(object_id=lb.id)
        LOG.debug(f'Loadbalancer {lb.name} was deployed successfully '
                  f'with id {lb.id}')

    listener_name = octavia.OCTAVIA_PROVIDERS_NAMES['listener'][provider]
    listener = octavia.find_listener(listener_name)
    if listener:
        LOG.debug(f'Listener {listener.id} already exists. Skipping'
                  ' its creation')
    else:
        listener_kwargs = {
            'protocol': protocol,
            'protocol_port': protocol_port,
            'loadbalancer_id': lb.id,
            'name': listener_name
        }
        listener = octavia.create_listener(listener_kwargs)
        octavia.wait_for_status(object_id=lb.id)
        LOG.debug(f'Listener {listener.name} was deployed '
                  f'successfully with id {listener.id}')

    pool_name = octavia.OCTAVIA_PROVIDERS_NAMES['pool'][provider]
    pool = octavia.find_pool(pool_name)
    if pool:
        LOG.debug(f'Pool {pool.id} already exists. Skipping its '
                  f'creation')
    else:
        pool_kwargs = {
            'listener_id': listener.id,
            'lb_algorithm': lb_algorithm,
            'protocol': protocol,
            'name': pool_name
        }

        pool = octavia.create_pool(pool_kwargs)
        octavia.wait_for_status(object_id=lb.id)
        LOG.debug(f'Pool {pool.name} was deployed successfully with'
                  f' id {pool.id}')

    if servers_stacks:
        for idx, server_stack in enumerate(servers_stacks):
            member_name_prefix = octavia.OCTAVIA_PROVIDERS_NAMES['member'][
                provider]
            member_name = member_name_prefix + str(idx)
            member = octavia.find_member(member_name=member_name,
                                         pool=pool.id)
            if member:
                LOG.debug(f'Member {member.id} already exists. Skipping its '
                          f'creation')
            else:
                member_kwargs = {
                    'address': str(server_stack.fixed_ipv4),
                    'protocol_port': protocol_port,
                    'name': member_name,
                    'subnet_id': server_stack.network_stack.ipv4_subnet_id,
                    'pool': pool.id
                }

                member = octavia.create_member(member_kwargs)
                octavia.wait_for_status(object_id=lb.id)
                LOG.debug(f'Member {member.name} was deployed successfully '
                          f'with id {member.id}')

    return lb, listener, pool


def deploy_ipv4_amphora_lb(protocol: str = _constants.PROTOCOL_HTTP,
                           protocol_port: int = 80,
                           lb_algorithm: str = (
                                   _constants.LB_ALGORITHM_ROUND_ROBIN),
                           servers_stacks=None):
    """Deploy a populated ipv4 amphora provider LB with HTTP resources

    This deployer method deploys the following resources:
        * An IPv4 amphora provider LB
        * An HTTP listener
        * An HTTP pool with Round Robin LB algorithm
        * Octavia members (a member per each nova vm it receives from the
            caller)

    :param protocol: the listener & pool protocol. For example: HTTP
    :param protocol_port: the load balancer protocol port
    :param lb_algorithm: the pool load balancing protocol. For example:
        ROUND_ROBIN
    :param servers_stacks: a list of server stacks (until we remove heat
        entirely)
    :return: all Octavia resources it has created (LB, listener, and pool)
    """
    return deploy_ipv4_lb(provider=octavia.AMPHORA_PROVIDER,
                          protocol=protocol,
                          protocol_port=protocol_port,
                          lb_algorithm=lb_algorithm,
                          servers_stacks=servers_stacks)


def deploy_ipv4_ovn_lb(protocol: str = _constants.PROTOCOL_TCP,
                       protocol_port: int = 80,
                       lb_algorithm: str = (
                               _constants.LB_ALGORITHM_SOURCE_IP_PORT),
                       servers_stacks=None):
    """Deploy a populated ipv4 OVN provider LB with TCP resources

    This deployer method deploys the following resources:
        * An IPv4 ovn provider LB
        * An TCP listener
        * An TCP pool with Source Ip Port LB algorithm
        * Octavia members (a member per each nova vm it receives from the
            caller)

    :param protocol: the listener & pool protocol. For example: TCP
    :param protocol_port: the load balancer protocol port
    :param lb_algorithm: the pool load balancing protocol. For example:
        SOURCE_IP_PORT
    :param servers_stacks: a list of server stacks (until we remove heat
        entirely)
    :return: all Octavia resources it has created (LB, listener, and pool)
    """
    return deploy_ipv4_lb(provider=octavia.OVN_PROVIDER,
                          protocol=protocol,
                          protocol_port=protocol_port,
                          lb_algorithm=lb_algorithm,
                          servers_stacks=servers_stacks)
