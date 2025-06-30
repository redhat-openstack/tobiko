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

from datetime import datetime
import math
import random
import re
import socket
import time
import urllib.parse

import netaddr
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import glance
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import stacks
from tobiko.openstack import tests
from tobiko.openstack import topology
from tobiko.tests.faults.ha import test_cloud_recovery
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.tripleo import containers
from tobiko.tripleo import pacemaker
from tobiko.tripleo import topology as tripleo_topology
from tobiko import tripleo


CONF = config.CONF
LOG = log.getLogger(__name__)

network_disruption = """
 sudo iptables-save > ~/working.iptables.rules &&
 sudo iptables -I INPUT 1 -m state --state RELATED,ESTABLISHED -j ACCEPT &&
 sudo iptables -I INPUT 2 -p tcp -m state --state NEW -m tcp --dport 22 -j \
 ACCEPT &&
 sudo iptables -I INPUT 3 ! -i lo -j DROP &&
 sudo iptables -I OUTPUT 1 -p tcp --sport 22 -j ACCEPT &&
 sudo iptables -I OUTPUT 2 ! -o lo -j DROP
"""

network_disruption_ipv6 = network_disruption.replace('iptables', 'ip6tables')

undisrupt_network = """
 sudo iptables-restore ~/working.iptables.rules
"""

undisrupt_network_ipv6 = undisrupt_network.replace('iptables', 'ip6tables')

# TODO(eolivare): run ovn_db_pcs_resource_restart using
# run_pcs_resource_operation
# Now it is not possible because it is executed with
# ssh_client.connect().exec_command and run_pcs_resource_operation only
# supports sh.execute
OVN_DB_PCS_RESOURCE_RESTART = (f"sudo pcs resource restart "
                               f"{pacemaker.OVN_DBS_RESOURCE}")
KILL_RABBIT = "sudo pkill -9 beam.smp"
REMOVE_GRASTATE = "sudo rm -rf /var/lib/mysql/grastate.dat"
CHECK_BOOTSTRAP = """ps -eo lstart,cmd | grep -v grep|
grep wsrep-cluster-address=gcomm://"""
GALERA_SST_REQUEST = """sudo grep 'wsrep_sst_rsync.*'
/var/log/containers/mysql/mysqld.log"""
KILL_MYSQLD = "sudo pkill -9 mysqld"
KILL_MARIADBD = "sudo pkill -9 mariadbd"
STOP_TRIPLEO = "sudo systemctl stop 'tripleo_*'"
PODMAN_PS = "sudo podman ps"


class PcsDisableException(tobiko.TobikoException):
    message = "pcs disable didn't shut down the resource"


class PcsEnableException(tobiko.TobikoException):
    message = "pcs enable didn't start the resource"


class GaleraBoostrapException(tobiko.TobikoException):
    message = "Bootstrap has not been activated"


class TimestampException(tobiko.TobikoException):
    message = "Timestamp mismatch: sst was requested before grastate removal"


class PodmanContainersException(tobiko.TobikoException):
    message = "Services are still running in podman"


def network_disrupt_node(node_name, disrupt_method=network_disruption):
    disrupt_node(node_name, disrupt_method=disrupt_method)


def network_undisrupt_node(node_name, disrupt_method=undisrupt_network):
    disrupt_node(node_name, disrupt_method=disrupt_method)


def disrupt_node(node_name, disrupt_method=network_disruption):
    # reboot all controllers and wait for ssh Up on them
    # hard reset is simultaneous while soft is sequential
    # method : method of disruption to use : network_disruption |
    # container_restart

    start_time = tobiko.time()
    # using ssh_client.connect we use a fire and forget reboot method
    node = tripleo_topology.get_node(node_name)
    node.ssh_client.connect().exec_command(disrupt_method)
    LOG.info('disrupt exec: {} on server: {}'.format(disrupt_method,
                                                     node.name))

    if isinstance(disrupt_method, sh.RebootHostMethod) \
            or is_network_disruption(disrupt_method):
        check_overcloud_node_uptime(node.ssh_client, start_time)
    else:
        check_overcloud_node_responsive(node)


def check_overcloud_node_uptime(ssh_client, start_time):
    for attempt in tobiko.retry(timeout=600., interval=10.):
        try:
            uptime = sh.get_uptime(ssh_client=ssh_client, timeout=15.)
        except sh.UptimeError:
            LOG.exception('uptime command failed')
            uptime = None

        if uptime and uptime < (tobiko.time() - start_time):
            LOG.debug('Reboot has been completed')
            break
        else:
            attempt.check_limits()


def reboot_node(node_name, wait=True, reboot_method=sh.hard_reset_method):

    # reboot a node and wait for ssh Up on them
    # hard reset is simultaneous while soft is sequential
    # method : method of disruption to use : reset | network_disruption

    # using ssh_client.connect we use a fire and forget reboot method
    node = tripleo_topology.get_node(node_name)
    sh.reboot_host(ssh_client=node.ssh_client, wait=wait, method=reboot_method)
    LOG.info('disrupt exec: {} on server: {}'.format(reboot_method,
                                                     node.name))


def check_overcloud_node_responsive(node):
    node_checked = sh.execute("hostname",
                              ssh_client=node.ssh_client,
                              expect_exit_status=None).stdout
    LOG.info('{} is up '.format(node_checked))

    tobiko.cleanup_fixture(node.ssh_client)


def network_disrupt_all_controller_nodes(disrupt_method=network_disruption,
                                         exclude_list=None):
    disrupt_all_controller_nodes(disrupt_method=disrupt_method,
                                 exclude_list=exclude_list)


def reset_all_controller_nodes(disrupt_method=sh.hard_reset_method,
                               exclude_list=None):
    disrupt_all_controller_nodes(disrupt_method=disrupt_method,
                                 exclude_list=exclude_list)


def reset_all_controller_nodes_sequentially(
        disrupt_method=sh.hard_reset_method,
        sequentially=True, exclude_list=None):
    disrupt_all_controller_nodes(disrupt_method=disrupt_method,
                                 sequentially=sequentially,
                                 exclude_list=exclude_list)


def disrupt_all_controller_nodes(disrupt_method=sh.hard_reset_method,
                                 sequentially=False, exclude_list=None):
    # TODO(eolivare): join disrupt_all_controller_nodes and
    # reboot_all_controller_nodes methods because they are very similar

    # reboot all controllers and wait for ssh Up on them
    # method : method of disruptino to use : reset | network_disruption
    # hard reset is simultaneous while soft is sequential
    # exclude_list = list of nodes to NOT reset

    controlplane_groups = ['controller', 'messaging', 'database', 'networker']
    actual_controlplane_groups = tripleo_topology.actual_node_groups(
        controlplane_groups)
    nodes = topology.list_openstack_nodes(group=actual_controlplane_groups)

    # remove excluded nodes from reset list
    if exclude_list:
        nodes = [node for node in nodes if node.name not in exclude_list]

    start_time = {}
    for controller in nodes:
        start_time[controller.name] = tobiko.time()
        if isinstance(disrupt_method, sh.RebootHostMethod):
            reboot_node(controller.name, wait=sequentially,
                        reboot_method=disrupt_method)
        else:
            # using ssh_client.connect we use a fire and forget reboot method
            controller.ssh_client.connect().exec_command(disrupt_method)
            LOG.info('disrupt exec: {} on server: {}'.format(disrupt_method,
                                                             controller.name))
            tobiko.cleanup_fixture(controller.ssh_client)
            if sequentially and is_network_disruption(disrupt_method):
                check_overcloud_node_uptime(
                    controller.ssh_client, start_time[controller.name])
        if sequentially:
            check_overcloud_node_responsive(controller)

    if not sequentially:
        for controller in nodes:
            if isinstance(disrupt_method, sh.RebootHostMethod) \
                    or is_network_disruption(disrupt_method):
                check_overcloud_node_uptime(
                    controller.ssh_client, start_time[controller.name])
            else:
                check_overcloud_node_responsive(controller)


def reboot_all_controller_nodes(reboot_method=sh.hard_reset_method,
                                sequentially=False, exclude_list=None):
    # reboot all controllers and wait for ssh Up on them
    # method : method of disruptino to use : hard or soft reset
    # hard reset is simultaneous while soft is sequential
    # exclude_list = list of nodes to NOT reset

    controlplane_groups = ['controller', 'messaging', 'database', 'networker']
    actual_controlplane_groups = tripleo_topology.actual_node_groups(
        controlplane_groups)
    nodes = topology.list_openstack_nodes(group=actual_controlplane_groups)

    # remove excluded nodes from reset list
    if exclude_list:
        nodes = [node for node in nodes if node.name not in exclude_list]

    start_time = {}
    for controller in nodes:
        start_time[controller.name] = tobiko.time()
        sh.reboot_host(ssh_client=controller.ssh_client, wait=sequentially,
                       method=reboot_method)
        LOG.info('reboot exec: {} on server: {}'.format(reboot_method,
                                                        controller.name))
        tobiko.cleanup_fixture(controller.ssh_client)
    if not sequentially:
        for controller in nodes:
            check_overcloud_node_uptime(
                controller.ssh_client, start_time[controller.name])


def is_ipv6addr_main_vip():
    """ Return True if main OC vip is ivp6 address. Otherwise return False."""
    main_vip = get_main_vip()
    return not netaddr.valid_ipv4(main_vip) and netaddr.valid_ipv6(main_vip)


def get_main_vip():
    """return the ip of the overcloud main vip.
    Retreive an ip address (ipv4/ipv6) from the auth_url."""
    auth_url = keystone.default_keystone_credentials().auth_url
    auth_url_parsed = urllib.parse.urlsplit(auth_url)
    main_vip = auth_url_parsed.hostname

    if not (netaddr.valid_ipv4(main_vip) or netaddr.valid_ipv6(main_vip)):
        try:
            # socket.gethostbyname translates hostname to IPv4 - it fails when
            # no IPv4 address is available
            main_vip = socket.gethostbyname(main_vip)
        except socket.gaierror:
            # the following method obtains an IPv6 from a hostname
            main_vip = socket.getaddrinfo(
                main_vip, None, socket.AF_INET6)[0][4][0]

    return main_vip


def get_main_vip_controller(main_vip):
    """return the controller hostname ,
    which is holding the main_vip pacemaker resource"""
    # when the main_vip is ipv6, the pacemaker command output replaces : by .
    # we need to adapt the value accordingly
    main_vim_controller = pacemaker.get_overcloud_nodes_running_pcs_resource(
        resource=f"ip-{main_vip.replace(':', '.')}")[0]
    return main_vim_controller


def delete_evacuable_tagged_image():
    # delete evacuable tagged image because it prevents
    # non tagged evacuations if exists
    for img in glance.list_images():
        if 'evacuable' in img['tags']:
            glance.delete_image(img.id)


def disrupt_controller_main_vip(disrupt_method=sh.hard_reset_method,
                                inverse=False):

    # reset the controller holding the main vip (os_auth_url)
    # ip resource (managed via pacemaker)
    # find main vip by getting it from
    main_vip = get_main_vip()

    # find the node holding that resource via :

    main_vip_controller = get_main_vip_controller(main_vip)

    if isinstance(disrupt_method, sh.RebootHostMethod):
        if inverse:
            reboot_all_controller_nodes(reboot_method=disrupt_method,
                                        exclude_list=[main_vip_controller])
        else:
            reboot_node(main_vip_controller, reboot_method=disrupt_method)
    else:
        if inverse:
            # inverse the nodes reset selection
            disrupt_all_controller_nodes(disrupt_method=disrupt_method,
                                         exclude_list=[main_vip_controller])
        else:
            # get that node's ssh_client and reset it
            disrupt_node(main_vip_controller, disrupt_method=disrupt_method)


def disrupt_controller_galera_main_vip(disrupt_method=sh.soft_reset_method):
    # This case reboots controller while VM creation is in progress
    # Please refer to RHBZ#2124877 for more info
    # Find the Galera VIP (port name : internal_api_virtual_ip)
    session = tripleo.undercloud_keystone_session()
    uc_neutron_client = neutron.get_neutron_client(session=session)
    try:
        new_port = neutron.find_port(client=uc_neutron_client, unique=False,
                                     name='internal_api_virtual_ip')
    except tobiko.ObjectNotFound as no_internal_api:
        raise tobiko.SkipException(
            'This OSP environment doesnt have an internal_api \
              network, so this test cannot be executed') from no_internal_api

    galera_vip_address = new_port['fixed_ips'][0]['ip_address']
    LOG.info("The Galera VIP address is: %r", galera_vip_address)
    # Find the controller hosting VIP resource
    galera_vip_resource = "ip-"+galera_vip_address
    galera_vip_controller = pacemaker.get_overcloud_nodes_running_pcs_resource(
                               resource=galera_vip_resource)[0]

    ports_before_stack_creation = neutron.list_ports(
        device_owner="compute:nova")
    multi_ip_test_fixture = tobiko.get_fixture(
        stacks.MultiIPCirrosServerStackFixture)
    tobiko.use_fixture(multi_ip_test_fixture)
    time.sleep(10)  # wait until some of the VMs have been created

    # Reboot that controller
    reboot_node(galera_vip_controller, wait=True,
                reboot_method=disrupt_method)

    return multi_ip_test_fixture, ports_before_stack_creation


def get_vms_detailed_info(multi_ip_test_fixture):
    for attempt in tobiko.retry(timeout=300, interval=10):
        # dynamically obtain the status of the VMs
        vms_detailed_info = multi_ip_test_fixture.vms_detailed_info

        vm_status_list = [
            vm.get('status') for vm in vms_detailed_info if vm is not None]
        if 'BUILD' not in vm_status_list:
            LOG.debug("All VMs reached a final status")
            break
        if attempt.is_last:
            LOG.warn("Still some VMs in status BUILD - the test continues...")
            break

    return vms_detailed_info


def check_no_duplicate_ips(vms_detailed_info, ports_before_stack_creation):
    test_case = tobiko.get_test_case()
    # check VM IP addresses are different
    ip4_list = []
    ip6_list = []
    for vm in vms_detailed_info:
        addresses = vm.get('addresses', {}) if vm is not None else {}
        # try to obtain the port associated to a VM from neutron if the VM
        # exists but vms_detailed_info does not show the port
        if not addresses and vm is not None:
            ports = neutron.list_ports(device_id=vm['id'],
                                       device_owner="compute:nova")
            test_case.assertLess(len(ports), 2)
            for port in ports:
                addresses[port['network_id']] = port['fixed_ips']

        for addresses_per_network in addresses.values():
            test_case.assertEqual(len(addresses_per_network), 2)
            for subnet_addr in addresses_per_network:
                # the subnet_addr dict is different depending on how it was
                # obtained: from vms_detailed_info or from neutron.list_ports
                subnet_ip = (subnet_addr.get('addr') or
                             subnet_addr.get('ip_address'))
                if netaddr.valid_ipv4(subnet_ip):
                    ip4_list.append(subnet_ip)
                elif netaddr.valid_ipv6(subnet_ip):
                    ip6_list.append(subnet_ip)

    ip4_set = set(ip4_list)  # this removes duplicate values
    LOG.debug("list of IPv4s from the MultiIPVM group: %r", ip4_list)
    test_case.assertEqual(len(ip4_list), len(ip4_set))

    ip6_set = set(ip6_list)  # this removes duplicate values
    LOG.debug("list of IPv6s from the MultiIPVM group: %r", ip6_list)
    test_case.assertEqual(len(ip6_list), len(ip6_set))

    LOG.debug("list of IPv4 and list of IPv6 addresses "
              "should have the same length")
    test_case.assertEqual(len(ip6_list), len(ip4_list))

    ports_after_reboot = neutron.list_ports(device_owner="compute:nova")
    ports_after_reboot_full = neutron.list_ports()
    LOG.debug(
        "list of compute:nova ports obtained at the begining of this test: %r",
        ports_before_stack_creation)
    LOG.debug(
        "list of compute:nova ports obtained at the end of this test: %r",
        ports_after_reboot)
    LOG.debug("full list of ports obtained at the end of this test: %r",
              ports_after_reboot_full)
    test_case.assertEqual(len(ip6_list), len(ports_after_reboot) - len(
        ports_before_stack_creation))


def reboot_controller_galera_main_vip():
    return disrupt_controller_galera_main_vip(
        disrupt_method=sh.soft_reset_method)


def reset_controller_main_vip():
    disrupt_controller_main_vip(disrupt_method=sh.hard_reset_method)


def reset_controllers_non_main_vip():
    disrupt_controller_main_vip(disrupt_method=sh.hard_reset_method,
                                inverse=True)


def crash_controller_main_vip():
    disrupt_controller_main_vip(disrupt_method=sh.crash_method)


def crash_controllers_non_main_vip():
    disrupt_controller_main_vip(disrupt_method=sh.crash_method,
                                inverse=True)


def network_disrupt_controller_main_vip():
    disrupt_controller_main_vip(disrupt_method=get_network_disruption(
                                is_ipv6addr_main_vip()))
    LOG.info('waiting 60s to avoid race conditions...')
    time.sleep(60.0)


def network_undisrupt_controller_main_vip():
    disrupt_controller_main_vip(disrupt_method=get_undisrupt_network(
                                is_ipv6addr_main_vip()))


def network_disrupt_controllers_non_main_vip():
    disrupt_controller_main_vip(disrupt_method=get_network_disruption(
                                is_ipv6addr_main_vip()),
                                inverse=True)


def network_undisrupt_controllers_non_main_vip():
    disrupt_controller_main_vip(disrupt_method=get_undisrupt_network(
                                is_ipv6addr_main_vip()),
                                inverse=True)


def is_network_disruption(disrupt_method):
    if re.search("ip6?tables", disrupt_method) \
                 and not re.search("restore", disrupt_method):
        return True
    else:
        return False


def get_network_disruption(isIpv6=False):
    """
    Param: isIpv6: boolean
    Return network_disruption(for ipv4) or network_disruption_ipv6 (which are
    iptables or ip6tables rules, correspondingly), according to the
    isIpv6 flag.
    """
    if isIpv6:
        return network_disruption_ipv6
    else:
        return network_disruption


def get_undisrupt_network(isIpv6=False):
    """
    Return undisrupt_network(for ipv4) or undisrupt_network_ipv6 method,
    according to the isIpv6 flag.
    """
    if isIpv6:
        return undisrupt_network_ipv6
    else:
        return undisrupt_network


def reset_all_compute_nodes(hard_reset=False, sequentially=False):

    # reboot all computes and wait for ssh Up on them
    if hard_reset:
        reset_method = sh.hard_reset_method
    else:
        reset_method = sh.soft_reset_method

    nodes = topology.list_openstack_nodes(group='compute')
    compute_reboot_operation_list = []
    for compute in nodes:
        # using ssh_client.connect we use a fire and forget reboot method
        # if sequentially, then wait and check uptime has changed
        # else, do not wait (uptime will be checked later)
        reboot_operation = sh.reboot_host(ssh_client=compute.ssh_client,
                                          wait=sequentially,
                                          method=reset_method)
        compute_reboot_operation_list.append(reboot_operation)
        LOG.info('reboot exec:  {} on server: {}'.format(reset_method,
                                                         compute.name))

    if not sequentially:
        for reboot_operation in compute_reboot_operation_list:
            # checking uptime on each compute - it should have been updated
            # after the reboot is done
            reboot_operation.wait_for_operation()
            LOG.info(f'{reboot_operation.hostname} is up')


def reset_ovndb_pcs_master_resource():
    """restart ovndb pacemaker resource
    this method only restart the resource running on the controller with is
    acting as Master"""
    node = pacemaker.get_overcloud_nodes_running_pcs_resource(
        resource_type='(ocf::ovn:ovndb-servers):', resource_state='Master')[0]
    ovn_db_pcs_master_resource_restart = (OVN_DB_PCS_RESOURCE_RESTART + ' ' +
                                          node)
    disrupt_node(node, disrupt_method=ovn_db_pcs_master_resource_restart)


def reset_ovndb_pcs_resource():
    """restart ovndb pacemaker resource
    this method restart the whole resource, i.e. on all the controller nodes"""
    node = pacemaker.get_overcloud_nodes_running_pcs_resource(
        resource_type='(ocf::ovn:ovndb-servers):', resource_state='Master')[0]
    disrupt_node(node, disrupt_method=OVN_DB_PCS_RESOURCE_RESTART)


def reset_ovndb_master_container():
    """get and restart the ovndb master container
    use of partial name :  resource: ovn-dbs-bundle-0 =>
    container: ovn-dbs-bundle-podman-0"""
    node = pacemaker.get_overcloud_nodes_running_pcs_resource(
        resource_type='(ocf::ovn:ovndb-servers):', resource_state='Master')[0]
    resource = pacemaker.get_overcloud_resource(
        resource_type='(ocf::ovn:ovndb-servers):', resource_state='Master')
    resource = resource[0].rsplit('-', 1)[0]
    containers.action_on_container('restart',
                                   partial_container_name=resource,
                                   container_host=node)


def restart_service_on_all_nodes(service):
    """restart the ovn bgp agent or the frr service from all the nodes where it
    is running and check the cloud is healthy after they are started again"""
    node_names = tripleo.get_overcloud_nodes_running_service(service)
    nodes = topology.list_openstack_nodes(hostnames=node_names)
    restart_service_on_nodes(service, nodes)


def restart_service_on_nodes(service, nodes):
    for node in nodes:
        sh.stop_systemd_units(service, ssh_client=node.ssh_client)
    for node in nodes:
        sh.start_systemd_units(service, ssh_client=node.ssh_client)


def kill_rabbitmq_service():
    """kill a rabbit process on a random controller,
    check in pacemaker it is down"""
    if tripleo_topology.is_composable_roles_env():
        nodes = topology.list_openstack_nodes(group='messaging')
    else:
        nodes = topology.list_openstack_nodes(group='controller')
    node = random.choice(nodes)
    sh.execute(KILL_RABBIT, ssh_client=node.ssh_client)
    LOG.info('kill rabbit: {} on server: {}'.format(KILL_RABBIT,
                                                    node.name))
    retry = tobiko.retry(timeout=30, interval=5)
    for _ in retry:
        if not (pacemaker.PacemakerResourcesStatus().
                rabbitmq_resource_healthy()):
            return


def kill_all_galera_services():
    """kill all galera processes,
    check in pacemaker it is down"""
    if tripleo_topology.is_composable_roles_env():
        nodes = topology.list_openstack_nodes(group='database')
    else:
        nodes = topology.list_openstack_nodes(group='controller')
    for node in nodes:
        if topology.verify_osp_version('17.0', lower=True):
            sh.execute(KILL_MYSQLD, ssh_client=node.ssh_client)
            LOG.info('kill galera: {} on server: {}'.format(KILL_MYSQLD,
                                                            node.name))
        else:
            sh.execute(KILL_MARIADBD, ssh_client=node.ssh_client)
            LOG.info('kill galera: {} on server: {}'.format(KILL_MARIADBD,
                                                            node.name))
    retry = tobiko.retry(timeout=30, interval=5)
    for _ in retry:
        if not (pacemaker.PacemakerResourcesStatus().
                galera_resource_healthy()):
            return


def remove_all_grastate_galera():
    """shut down galera properly,
    remove all grastate"""
    if tripleo_topology.is_composable_roles_env():
        nodes = topology.list_openstack_nodes(group='database')
    else:
        nodes = topology.list_openstack_nodes(group='controller')
    LOG.info('shut down {} on all servers: {}'.format(
        pacemaker.GALERA_RESOURCE, nodes))
    if f"resource '{pacemaker.GALERA_RESOURCE}' is not running on any node" \
            not in pacemaker.run_pcs_resource_operation(
                pacemaker.GALERA_RESOURCE,
                pacemaker.DISABLE,
                nodes[0].ssh_client):
        raise PcsDisableException()
    for node in nodes:
        sh.execute(REMOVE_GRASTATE, ssh_client=node.ssh_client)

    LOG.info('enable back {} on all servers: {}'.format(
        pacemaker.GALERA_RESOURCE, nodes))
    if topology.verify_osp_version('17.0', lower=True):
        promoted = "master"
    else:
        promoted = "promoted"
    if f"resource '{pacemaker.GALERA_RESOURCE}' is {promoted} on node" not in \
            pacemaker.run_pcs_resource_operation(pacemaker.GALERA_RESOURCE,
                                                 pacemaker.ENABLE,
                                                 nodes[0].ssh_client,
                                                 operation_wait=90):
        raise PcsEnableException()


def remove_one_grastate_galera():
    """shut down galera properly,
    delete /var/lib/mysql/grastate.dat in a random node,
    check that bootstrap is done from a node with grastate"""
    if tripleo_topology.is_composable_roles_env():
        nodes = topology.list_openstack_nodes(group='database')
    else:
        nodes = topology.list_openstack_nodes(group='controller')
    node = random.choice(nodes)

    pcs_haproxy = pacemaker.HAPROXY_RESOURCE
    pcs_galera = pacemaker.GALERA_RESOURCE

    if not CONF.tobiko.rhosp.has_external_load_balancer:
        LOG.info(f'disable {pcs_haproxy}')
        if f"resource '{pcs_haproxy}' is not running on any node" not in \
                pacemaker.run_pcs_resource_operation(
                    pcs_haproxy,
                    pacemaker.DISABLE,
                    node.ssh_client,
                    operation_wait=30):
            raise PcsDisableException()
    else:
        LOG.debug(f'With Ext LB setups, {pcs_haproxy} is not deployed')

    LOG.info('shut down {} on all servers: {}'.format(pcs_galera, nodes))
    if f"resource '{pcs_galera}' is not running on any node" not in \
            pacemaker.run_pcs_resource_operation(
                pcs_galera,
                pacemaker.DISABLE,
                node.ssh_client):
        raise PcsDisableException()
    LOG.info('remove grastate: {} on server: {}'.format(REMOVE_GRASTATE,
                                                        node.name))
    sh.execute(REMOVE_GRASTATE, ssh_client=node.ssh_client)

    LOG.info('enable back {} on all servers: {}'.format(pcs_galera, nodes))
    if topology.verify_osp_version('17.0', lower=True):
        promoted = "master"
    else:
        promoted = "promoted"
    if f"resource '{pcs_galera}' is {promoted} on node" not in \
            pacemaker.run_pcs_resource_operation(
                pcs_galera, pacemaker.ENABLE, node.ssh_client,
                operation_wait=90):
        raise PcsEnableException()

    if not CONF.tobiko.rhosp.has_external_load_balancer:
        LOG.info(f'enable {pcs_haproxy}')
        if f"resource '{pcs_haproxy}' is running on node" not in \
                pacemaker.run_pcs_resource_operation(pcs_haproxy,
                                                     pacemaker.ENABLE,
                                                     node.ssh_client):
            raise PcsEnableException()
    else:
        LOG.debug(f'With Ext LB setups, {pcs_haproxy} is not deployed')

    # gcomm:// without args means that bootstrap is done from this node
    bootstrap = sh.execute(CHECK_BOOTSTRAP, ssh_client=node.ssh_client).stdout
    if re.search('wsrep-cluster-address=gcomm://', bootstrap) is None:
        raise GaleraBoostrapException()
    lastDate = re.findall(r"\w{,3}\s*\w{,3}\s*\d{,2}\s*\d{,2}:\d{,2}:\d{,2}\s*"
                          r"\d{4}", bootstrap)[-1]
    return node, lastDate


def request_galera_sst():
    """remove_one_grastate_galera,
    check that sst is requested by a node with grastate"""
    node, date = remove_one_grastate_galera()
    bootstrapDate = datetime.strptime(date, '%a %b %d %H:%M:%S %Y')
    retry = tobiko.retry(timeout=30, interval=5)
    for _ in retry:
        sst_req = sh.execute(GALERA_SST_REQUEST,
                             ssh_client=node.ssh_client).stdout
        if sst_req:
            break
    sstDate = datetime.strptime(re.findall
                                (r"\d{4}-\d{,2}-\d{,2}\s*\d{,2}:\d{,2}:\d{,2}",
                                 sst_req)[-1], '%Y-%m-%d %H:%M:%S')
    if bootstrapDate > sstDate:
        raise TimestampException


def evac_failover_compute(compute_host, failover_type=sh.hard_reset_method):
    """disrupt a compute, to trigger it's instance-HA evacuation
    failover_type=hard_reset_method etc.."""
    if failover_type in (sh.hard_reset_method, sh.soft_reset_method):
        reboot_node(compute_host, reboot_method=failover_type)
    else:
        disrupt_node(compute_host, disrupt_method=failover_type)


def get_random_compute_with_vms():
    for compute in nova.list_hypervisors():
        param = {'OS-EXT-SRV-ATTR:hypervisor_hostname':
                 compute.hypervisor_hostname}
        vm_list_per_compute = nova.list_servers(**param)
        if len(vm_list_per_compute) > 0:
            return compute.hypervisor_hostname


def iha_maintenance():
    """performing maintenance on overcloud with instanceha"""
    controllers = topology.list_openstack_nodes(group='controller')
    computes = topology.list_openstack_nodes(group='compute')
    servers = create_shutoff_vms()
    computes_stonith = disable_computes(computes)
    power_off_nodes(computes)
    podman_not_empty = stop_cluster(controllers)
    power_off_nodes(controllers)
    power_on_nodes(controllers)
    power_on_nodes(computes)
    enable_computes(computes, computes_stonith)
    cleanup()
    ping_delete_servers(servers)
    if podman_not_empty:
        raise PodmanContainersException


def create_shutoff_vms():
    LOG.info('create 2 vms')
    servers = tests.test_servers_creation(number_of_servers=2)
    nova.action_on_all_instances('shutoff')
    return servers


def disable_computes(computes):
    for compute in computes:
        LOG.info(f"disable {compute.name}")
        pacemaker.run_pcs_resource_operation(compute.name, pacemaker.DISABLE)
    stonith_status = pacemaker.execute_pcs(['stonith', 'status'], sudo=True)
    computes_stonith = pair_compute_stonith(stonith_status)
    for stonith in computes_stonith:
        LOG.info(f"pcs stonith disable {stonith}")
        pacemaker.execute_pcs(['stonith', 'disable', stonith], sudo=True)
    return computes_stonith


def power_off_nodes(nodes):
    for node in nodes:
        LOG.info(f"power off {node}")
        node.power_off_node()


def power_on_nodes(nodes):
    for node in nodes:
        LOG.info(f"power on {node}")
        node.power_on_node()


def stop_cluster(controllers):
    podman_not_empty = False
    LOG.info("pcs cluster stop --all")
    pacemaker.execute_pcs(['cluster', 'stop', '--all'],
                          sudo=True, timeout=70)
    for controller in controllers:
        LOG.info(f"sudo systemctl stop 'tripleo_*' {controller}")
        sh.execute(STOP_TRIPLEO, ssh_client=controller.ssh_client)
        # checks podman doesn't run anything
        # (stdout = headlines = 80 characters)
        if len(sh.execute(PODMAN_PS, ssh_client=controller.ssh_client).stdout
               ) > 100:
            podman_not_empty = True
    return podman_not_empty


def enable_computes(computes, computes_stonith):
    for compute in computes:
        LOG.info(f"execute pcs stonith confirm {compute.name} --force")
        pacemaker.execute_pcs(['stonith', 'confirm', compute.name,
                               '--force'], sudo=True)
    for stonith in computes_stonith:
        LOG.info(f"execute pcs stonith enable {stonith}")
        pacemaker.execute_pcs(['stonith', 'enable', stonith], sudo=True)
    for compute in computes:
        LOG.info(f"enable {compute.name}")
        pacemaker.run_pcs_resource_operation(compute.name, pacemaker.ENABLE,
                                             operation_wait=800)


def cleanup():
    LOG.info("execute pcs resource cleanup")
    pacemaker.execute_pcs(['resource', 'cleanup'], sudo=True)


def ping_delete_servers(servers):
    nova.action_on_all_instances('active')
    LOG.info("ping servers and delete")
    for server in servers:
        server.assert_is_reachable()
        server.delete_stack()


def pair_compute_stonith(stonith_status):
    """ From the following input, it ouputs only computes fence:
  * stonith-fence_ipmilan-525400793eae	(stonith:fence_ipmilan):
  * stonith-fence_compute-fence-nova	(stonith:fence_compute):
  * stonith-fence_ipmilan-5254000a18c9	(stonith:fence_ipmilan):
  * stonith-fence_ipmilan-525400fa6fc8	(stonith:fence_ipmilan):
Fencing Levels:
 Target: compute-0
   Level1- stonith-fence_ipmilan-525400fa6fc8,stonith-fence_compute-fence-nova
 Target: compute-1
   Level1- stonith-fence_ipmilan-5254000a18c9,stonith-fence_compute-fence-nova
 Target: controller-0
   Level1- stonith-fence_ipmilan-525400793eae
leads to
['stonith-fence_ipmilan-525400fa6fc8', 'stonith-fence_ipmilan-5254000a18c9']
"""
    lines = stonith_status.splitlines()
    compute_stonith = []
    current_target = None
    for line in lines:
        target_match = re.match(r"^\s*Target:\s+(compute-\d+)", line)
        if target_match:
            current_target = target_match.group(1)
            continue
        elif re.match(r"^\s*Target:\s+(controller-\d+)", line):
            current_target = None
            continue
        if current_target:
            stonith_matches = re.findall(r"stonith-fence_ipmilan-[\da-f]+",
                                         line)
            if stonith_matches:
                compute_stonith.extend(stonith_matches)
    return compute_stonith


def check_iha_evacuation(failover_type=None, vm_type=None):
    """check vms on compute host,disrupt compute host,
    check all vms evacuated and pingable"""
    for iteration in range(2):
        LOG.info(f'Begin IHA tests iteration {iteration}')
        LOG.info('create 2 vms')
        tests.test_servers_creation(number_of_servers=2)
        compute_host = get_random_compute_with_vms()
        vms_starting_state = nova.list_servers(
            **{'OS-EXT-SRV-ATTR:hypervisor_hostname': compute_host})
        if vm_type == 'shutoff':
            nova.action_on_all_instances('shutoff')
        if vm_type == 'evac_image_vm':
            evac_vm_stack = tests.test_evacuable_server_creation()
            evac_vm_id = evac_vm_stack.server_details.id
            old_nova_evac = nova.get_server(server_id=evac_vm_id)
        if not vm_type == 'shutoff':
            nova.check_vms_ping(vms_starting_state)
        LOG.info(f'perform a failover on {compute_host}')
        evac_failover_compute(compute_host, failover_type=failover_type)
        test_cloud_recovery.overcloud_health_checks(passive_checks_only=True)
        if vm_type == 'evac_image_vm':
            nova.check_vm_evacuations(vms_old=old_nova_evac,
                                      compute_host=compute_host,
                                      timeout=600,
                                      check_no_evacuation=True)
            # delete evacuable tagged image because it prevents
            # non tagged evacuations if exists
            delete_evacuable_tagged_image()
            new_nova_evac = nova.get_server(server_id=evac_vm_id)
            nova.check_vm_evacuations(old_nova_evac, new_nova_evac)
        else:
            nova.check_vm_evacuations(vms_old=vms_starting_state,
                                      compute_host=compute_host,
                                      timeout=600)
        LOG.info('check evacuation is Done')
        if not vm_type == 'shutoff':
            nova.check_vms_ping(vms_starting_state)


def check_iha_evacuation_evac_image_vm():
    check_iha_evacuation(failover_type=sh.hard_reset_method,
                         vm_type='evac_image_vm')


def check_iha_evacuation_hard_reset():
    check_iha_evacuation(failover_type=sh.hard_reset_method)


def check_iha_evacuation_network_disruption():
    check_iha_evacuation(failover_type=get_network_disruption(
                         is_ipv6addr_main_vip()))


def check_iha_evacuation_hard_reset_shutoff_instance():
    check_iha_evacuation(failover_type=sh.hard_reset_method, vm_type='shutoff')


def test_controllers_shutdown():
    test_case = tobiko.get_test_case()

    all_nodes = topology.list_openstack_nodes(group='controller')
    if len(all_nodes) < 3:
        tobiko.skip_test('It requires at least three controller nodes')

    all_node_names = [node.name for node in all_nodes]
    LOG.info("Ensure all controller nodes are running: "
             f"{all_node_names}")
    for node in all_nodes:
        node.power_on_node()
    topology.assert_reachable_nodes(all_nodes)

    LOG.debug('Check VM is running while all controllers nodes are on')
    nova_server = tobiko.setup_fixture(stacks.CirrosServerStackFixture)
    nova_server_ip = nova_server.ip_address
    ping.assert_reachable_hosts([nova_server_ip])

    quorum_level = math.ceil(0.5 * len(all_nodes))
    assert quorum_level >= len(all_nodes) - quorum_level
    nodes = random.sample(all_nodes, quorum_level)
    node_names = [node.name for node in nodes]
    LOG.info(f"Power off {quorum_level} random controller nodes: "
             f"{node_names}")
    for node in nodes:
        node.power_off_node()
        test_case.addCleanup(node.power_on_node)
    topology.assert_unreachable_nodes(nodes, retry_count=1)
    topology.assert_reachable_nodes(node
                                    for node in all_nodes
                                    if node not in nodes)

    LOG.debug('Check whenever VM is still running while some "'
              '"controllers nodes are off')
    reachable, unreachable = ping.ping_hosts([nova_server_ip],
                                             count=1)
    if reachable:
        LOG.debug(f"VM ips are reachable: {reachable}")
    if unreachable:
        LOG.debug(f"VM is are unreachable: {unreachable}")
    # TODO what do we expect here: VM reachable or unreachable?

    random.shuffle(nodes)
    LOG.info(f"Power on controller nodes: {node_names}")
    for node in nodes:
        node.power_on_node()

    LOG.debug("Check all controller nodes are running again: "
              f"{all_node_names}")
    topology.assert_reachable_nodes(all_nodes, retry_timeout=600.)

    LOG.debug('Check VM is running while all controllers nodes are on')
    ping.assert_reachable_hosts([nova_server_ip])
