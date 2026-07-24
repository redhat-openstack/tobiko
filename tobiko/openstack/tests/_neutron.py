from __future__ import absolute_import

import collections
import json
import re
import threading
import time
import typing

from keystoneauth1 import exceptions
import netaddr
from oslo_log import log

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import topology
from tobiko.shell import ip
from tobiko.shell import sh
from tobiko.shell import ss


LOG = log.getLogger(__name__)


def test_neutron_agents_are_alive(timeout=420., interval=3.) \
        -> tobiko.Selection[neutron.NeutronAgentType]:
    for attempt in tobiko.retry(timeout=timeout, interval=interval):
        LOG.debug("Look for unhealthy Neutron agents...")
        try:
            # get Neutron agent list
            agents = neutron.list_agents()
        except (neutron.ServiceUnavailable,
                neutron.NeutronClientException,
                exceptions.connection.ConnectFailure) as ex:
            if attempt.is_last:
                raise
            else:
                # retry because Neutron server could still be unavailable
                # after a disruption
                LOG.warning(f"Waiting for neutron service... ({ex})")
                continue  # Let retry

        dead_agents = agents.with_items(alive=False)
        if dead_agents:
            dead_agents_details = json.dumps(agents, indent=4, sort_keys=True)
            if attempt.is_last:
                tobiko.fail("Unhealthy agent(s) found:\n"
                            f"{dead_agents_details}\n")
            else:
                # retry because some Neutron agent could still be unavailable
                # after a disruption
                LOG.warning("Waiting for Neutron agents to get alive...\n"
                            f"{dead_agents_details}")
                continue

        if len(agents) == 0:
            message = "neutron returned 0 agents, which is not valid"
            if attempt.is_last:
                tobiko.fail(message)
            else:
                LOG.warning(message + "... retrying...")
                continue

        LOG.debug(f"All {len(agents)} Neutron agents are alive.")
        break
    else:
        raise RuntimeError("Retry loop broken")

    return agents


def test_alive_agents_are_consistent_along_time(retry_timeout=360.,
                                                retry_interval=3.,
                                                consistent_sleep=5.,
                                                consistent_count=5,):
    # the following dict of agents is obtained when:
    # - the list_agents request is replied with 200
    # - the list is not empty
    # - no agents are dead
    alive_agents = {agent['id']: agent
                    for agent in test_neutron_agents_are_alive()}

    for attempt_out in tobiko.retry(timeout=retry_timeout,
                                    interval=retry_interval):
        LOG.debug('trying to obtain a consistent list of alive neutron agents '
                  f'for {consistent_count} times')
        for attempt_in in tobiko.retry(sleep_time=consistent_sleep,
                                       count=consistent_count):
            try:
                agents = neutron.list_agents()
            except (neutron.ServiceUnavailable,
                    neutron.NeutronClientException,
                    exceptions.connection.ConnectFailure):
                LOG.exception('Error obtaining the list of neutron agents')
                # go to the outer loop, if its timeout didn't expire yet
                # the alive_agents reference is the previous list
                break
            actual = {agent['id']: agent for agent in agents}

            # any dead agents? If yes, go to the outer loop
            # the alive_agents reference is the previous list
            dead_agents = agents.with_items(alive=False)
            if len(dead_agents) > 0:
                LOG.warn(f'Some dead agents have been found: {dead_agents}')
                break

            # go to the outer loop if the set of agents changed
            # the alive_agents reference is the new list
            if set(actual) != set(alive_agents):
                LOG.warn("The list of agents has changed\n"
                         f"previous_agent_list:\n{alive_agents}\n"
                         f"new_agent_list:\n{actual}")
                alive_agents = actual
                break

            LOG.debug("The new list of agents matched the previous list "
                      "%d times", attempt_in.number)

            if attempt_in.is_last:
                LOG.info(f"the list of agents obtained for {consistent_count} "
                         "times was consistent - the test passes")
                return

        if attempt_out.is_last:
            tobiko.fail("No consistent neutron agent results obtained")


def ovn_dbs_vip_bindings(test_case):
    ovn_conn_str = neutron.get_ovn_db_connections()
    # ovn db sockets might be centrillized or distributed
    # that depends on the openstack version under test
    sockets_centrallized = topology.verify_osp_version('14.0', lower=True)
    for db in neutron.OVNDBS:
        found_centralized = False
        addrs, port = neutron.parse_ips_from_db_connections(
            ovn_conn_str[db])
        if neutron.is_ovn_using_raft():
            addrs.append(netaddr.IPAddress('0.0.0.0'))
            addrs.append(netaddr.IPAddress('::'))
        for node in topology.list_openstack_nodes(group='controller'):
            socs = ss.tcp_listening(port=port, ssh_client=node.ssh_client)
            if sockets_centrallized and not socs:
                continue
            test_case.assertEqual(1, len(socs))
            test_case.assertIn(socs[0]['local_addr'], addrs)
            test_case.assertEqual(socs[0]['process'][0], 'ovsdb-server')
            if sockets_centrallized:
                test_case.assertFalse(found_centralized)
                found_centralized = True
        if sockets_centrallized:
            test_case.assertTrue(found_centralized)


def ovn_dbs_are_synchronized(test_case):
    """Check that OVN DBs are syncronized across all controller nodes"""
    db_sync_status = neutron.get_ovn_db_sync_status()
    if neutron.is_ovn_using_ha():
        # In Active-Backup service model we expect exactly one active
        # node per database and all others in backup state
        for db in neutron.OVNDBS:
            active_nodes = [
                ctrl for ctrl, state in db_sync_status[db]
                if state == 'active']
            test_case.assertEqual(
                1, len(active_nodes),
                f"Expected exactly 1 active node for {db} DB, "
                f"found {len(active_nodes)}: {active_nodes}")
            LOG.debug("OVN %s DB active node: %s", db, active_nodes[0])
            for controller, state in db_sync_status[db]:
                if controller == active_nodes[0]:
                    test_case.assertEqual('active', state)
                else:
                    test_case.assertEqual('backup', state)
    elif neutron.is_ovn_using_raft():
        # In clustered database service model we expect all databases to be
        # active
        for db in neutron.OVNDBS:
            for _, state in db_sync_status[db]:
                test_case.assertEqual('active', state)
    dumps = neutron.dump_ovn_databases()
    for ovndb in (neutron.NBDB, neutron.SBDB):
        LOG.debug('OVN %s database dump: %s', ovndb, dumps[ovndb])


def test_ovn_dbs_validations():
    if not neutron.has_ovn():
        LOG.debug('OVN not configured. OVN DB sync validations skipped')
        return

    test_case = tobiko.get_test_case()

    ovn_dbs_are_synchronized(test_case)
    ovn_dbs_vip_bindings(test_case)


def test_raft_cluster():
    if not neutron.is_ovn_using_raft():
        return
    test_case = tobiko.get_test_case()
    cluster_ports = neutron.get_raft_ports()
    for db in neutron.OVNDBS:
        cluster_details = neutron.collect_raft_cluster_details(db)
        leader_found = False
        for node_details in cluster_details:
            neutron.check_raft_timers(node_details)
            if node_details['Role'] == 'leader':
                test_case.assertFalse(leader_found)
                leader_found = True
        test_case.assertTrue(leader_found)
        for node in topology.list_openstack_nodes(group='controller'):
            node_ips = ip.list_ip_addresses(ssh_client=node.ssh_client)
            socs = ss.tcp_listening(port=cluster_ports[db],
                                    ssh_client=node.ssh_client)
            test_case.assertEqual(1, len(socs))
            test_case.assertIn(socs[0]['local_addr'], node_ips)
            test_case.assertEqual(socs[0]['process'][0], 'ovsdb-server')


def test_raft_clients_connected():
    """Verifies that all SBDB readers are connected to active nodes

    Unlike HA environment all operations are allowed to be performed to any
    available node. To have the better performance all heavy write operations
    are done to leader node, but readers are spreaded across all cluster
    controllers
    """
    test_case = tobiko.get_test_case()
    test_case.assertTrue(neutron.is_ovn_using_raft())
    db_con_str = neutron.get_ovn_db_connections()['sb']
    addrs, port = neutron.parse_ips_from_db_connections(db_con_str)
    for node_details in neutron.collect_raft_cluster_details('sb'):
        if node_details['Role'] == 'leader':
            leader_ips, _ = neutron.parse_ips_from_db_connections(
                    node_details['Address'])
            break
    test_case.assertIsNotNone(locals().get('leader_ips'))
    leader_ip = leader_ips[0]

    for node in topology.list_openstack_nodes(group='compute'):
        socs = ss.tcp_connected(dst_port=port, ssh_client=node.ssh_client)
        ovn_controller_found = False
        for soc in socs:
            if soc['process'][0] == 'ovn-controller':
                ovn_controller_found = True
            test_case.assertIn(soc['remote_addr'], addrs)
        test_case.assertTrue(ovn_controller_found)

    ref_processes = {'ovn-controller', 'neutron-server:', 'ovn-northd'}

    # the octavia driver connects to the ovn dbs when the octavia service is
    # configured
    if keystone.has_service(name='octavia'):
        ref_processes.add('octavia-driver-')

    # the ovn-bgp-agent connects to the ovn dbs when the bgp service is
    # configured (but this service cannot be obtained from keystone and does
    # not have any API implemented yet)
    from tobiko.tripleo import containers
    if containers.assert_containers_running(
            group="controller",
            expected_containers=['ovn_bgp_agent'],
            bool_check=True):
        ref_processes.add('ovn-bgp-agent')

    for node in topology.list_openstack_nodes(group='controller'):
        socs = ss.tcp_connected(dst_port=port, ssh_client=node.ssh_client)
        processes = set()
        for soc in socs:
            processes.add(soc['process'][0])
            if soc['process'][0] == 'ovn-northd':
                test_case.assertEqual(soc['remote_addr'], leader_ip)
            else:
                test_case.assertIn(soc['remote_addr'], addrs)
        test_case.assertEqual(processes, ref_processes)


def test_ovs_bridges_mac_table_size():
    test_case = tobiko.get_test_case()
    expected_mac_table_size = '50000'
    get_mac_table_size_cmd = ('ovs-vsctl get bridge {br_name} '
                              'other-config:mac-table-size')
    if neutron.has_ovn():
        get_br_mappings_cmd = ('ovs-vsctl get Open_vSwitch . '
                               'external_ids:ovn-bridge-mappings')
    else:
        get_br_mappings_cmd = (
            'crudini --get /var/lib/config-data/puppet-generated/neutron/'
            'etc/neutron/plugins/ml2/openvswitch_agent.ini '
            'ovs bridge_mappings')
    for node in topology.list_openstack_nodes(group='overcloud'):
        try:
            br_mappings_str = sh.execute(get_br_mappings_cmd,
                                         ssh_client=node.ssh_client,
                                         sudo=True).stdout.splitlines()[0]
        except sh.ShellCommandFailed:
            LOG.debug(f"bridge mappings not configured on node '{node.name}'",
                      exc_info=1)
            continue
        br_list = [br_mapping.split(':')[1] for br_mapping in
                   br_mappings_str.replace('"', '').split(',')]
        for br_name in br_list:
            mac_table_size = sh.execute(
                get_mac_table_size_cmd.format(br_name=br_name),
                ssh_client=node.ssh_client, sudo=True).stdout.splitlines()[0]
            test_case.assertEqual(mac_table_size.replace('"', ''),
                                  expected_mac_table_size)


OPENSTACK_NODE_GROUP = re.compile(r'(compute|controller|overcloud)')
OVS_NAMESPACE = re.compile(r'(qrouter.*|qdhcp.*|snat.*|fip.*)')


def test_ovs_namespaces_are_absent(
        group: typing.Pattern[str] = OPENSTACK_NODE_GROUP,
        namespace: typing.Pattern[str] = OVS_NAMESPACE):
    nodes = topology.list_openstack_nodes(group=group)

    namespaces: typing.Dict[str, typing.List[str]] = (
        collections.defaultdict(list))
    for node in nodes:
        for node_namespace in ip.list_network_namespaces(
                ssh_client=node.ssh_client, sudo=True):
            if namespace.match(node_namespace):
                namespaces[node.name].append(node_namespace)
    namespaces = dict(namespaces)

    test_case = tobiko.get_test_case()
    test_case.assertEqual(
        {}, dict(namespaces),
        f"OVS namespace(s) found on OpenStack nodes: {namespaces}")


OVS_INTERFACE = re.compile(r'(qvo.*|qvb.*|qbr.*|qr.*|qg.*|fg.*|sg.*)')


def test_ovs_interfaces_are_absent(
        group: typing.Pattern[str] = OPENSTACK_NODE_GROUP,
        interface: typing.Pattern[str] = OVS_INTERFACE):
    nodes = topology.list_openstack_nodes(group=group)

    interfaces: typing.Dict[str, typing.List[str]] = (
        collections.defaultdict(list))
    for node in nodes:
        for node_interface in ip.list_network_interfaces(
                ssh_client=node.ssh_client, sudo=True):
            if interface.match(node_interface):
                interfaces[node.name].append(node_interface)
    interfaces = dict(interfaces)

    test_case = tobiko.get_test_case()
    test_case.assertEqual(
        {}, interfaces,
        f"OVS interface(s) found on OpenStack nodes: {interfaces}")


def cleanup_ports_network(port_count):
    # This function cleans up the ports and the created network
    for _ in range(port_count):
        port_name = f'tobiko_ovn_leader_test_port-{_}'
        try:
            port = neutron.find_port(name=port_name)
            neutron.delete_port(port=port['id'])
            LOG.debug("Port deleted: %s", port_name)
        except (neutron.NoSuchPort, tobiko.ObjectNotFound):
            LOG.debug("No Such port found: %s", port_name)
    network = neutron.find_network(name='tobiko_ovn_leader_test_network')
    neutron.delete_network(network=network)


def find_port_retries(port_name, timeout=30., interval=3.):
    for attempt in tobiko.retry(timeout=timeout, interval=interval):
        try:
            port = neutron.find_port(name=port_name)
        except (neutron.NoSuchPort, tobiko.ObjectNotFound):
            if attempt.is_last:
                LOG.debug(
                    "Port %s not found after %f seconds", port_name, timeout)
                return None
            else:
                continue
        return port


def check_port_created(port_count):
    # This function checks the number of ports created
    test_case = tobiko.get_test_case()
    port_count_created = 0
    for _ in range(port_count):
        port_name = f'tobiko_ovn_leader_test_port-{_}'
        port = find_port_retries(port_name)
        if port is not None:
            port_count_created += 1
            LOG.debug("Port found: %s", port_name)
        else:
            LOG.debug("No Such port found: %s", port_name)
    test_case.assertEqual(port_count_created, port_count)


def create_multiple_port_network(port_count):
    # This function is run in threading mode
    session = keystone.get_keystone_session(shared=False)
    client = neutron.get_neutron_client(session=session)
    network = neutron.create_network(client=client, add_cleanup=False,
                                     name='tobiko_ovn_leader_test_network')
    for _ in range(port_count):
        # different clients are needed for the requests that are sent in
        # parallel processes running in background
        # with a common client, an SSLError exception is raised
        session = keystone.get_keystone_session(shared=False)
        client = neutron.get_neutron_client(session=session)
        # Multiple requests are sent in background mode to save time
        # and not to wait till the control returns
        sh.start_background_process(bg_function=neutron.create_port,
                                    bg_process_name=f"create_port-{_}",
                                    client=client, network=network,
                                    add_cleanup=False,
                                    name=f'tobiko_ovn_leader_test_port-{_}')
    LOG.debug("Finished creating %r ports", port_count)


def test_ovsdb_transactions():
    # Set the number of ports to be created for test
    port_count = 20
    cluster_details = neutron.get_leader_ovsdb()
    thread_create_ports = threading.Thread(target=create_multiple_port_network,
                                           args=(port_count,))
    # Start the thread to create ports
    thread_create_ports.start()
    LOG.debug("Start to create 20 multiple ports")
    # Add cleanup of ports and network
    tobiko.add_cleanup(cleanup_ports_network, port_count=port_count)
    # Wait for some port creation request to reach neutron
    time.sleep(7)
    LOG.debug("Start the ovsdb leadership change")
    neutron.transfer_leadership_ovsdb(cluster_details)
    # Wait for the port creation to complete
    thread_create_ports.join()
    check_port_created(port_count)
