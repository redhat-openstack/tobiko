# Copyright (c) 2026 Red Hat
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

import functools
import re
import typing

import netaddr
from oslo_log import log

import tobiko
from tobiko.openstack.neutron import _agent as agent_mod
from tobiko.shell import sh

# NOTE: tobiko.openstack.topology cannot be imported at module level
# because topology._topology references neutron.DHCP_AGENT at
# class-body level, creating a circular import. Use lazy imports
# inside functions instead: from tobiko.openstack import topology

LOG = log.getLogger(__name__)

NBDB = 'nbdb'
SBDB = 'sbdb'

OVNDBS = ('nb', 'sb')
DBNAMES = {'nb': 'OVN_Northbound', 'sb': 'OVN_Southbound'}

OVN_RAFT = 'RAFT'
OVN_HA = 'HA'

_PODIFIED_CTL_PATH = {
    'nb': '/etc/ovn/ovnnb_db.ctl',
    'sb': '/etc/ovn/ovnsb_db.ctl',
}

_PODIFIED_POD_LABEL = {
    'nb': 'ovsdbserver-nb',
    'sb': 'ovsdbserver-sb',
}

_OVN_DB_BINARY = {
    NBDB: 'ovn-nbctl',
    SBDB: 'ovn-sbctl',
}

_PODIFIED_CLUSTER_NAME = {
    NBDB: 'ovndbcluster-nb',
    SBDB: 'ovndbcluster-sb',
}

_ovndb_connections: typing.Dict[str, str] = {}
_cache: typing.Dict[str, typing.Any] = {}


class InvalidDBConnString(tobiko.TobikoException):
    pass


class InvalidDBServiceModel(tobiko.TobikoException):
    pass


class RAFTStatusError(tobiko.TobikoException):
    pass


# --- SSH client and container prefix ---


def get_ovndb_ssh_client():
    """Get an SSH client for an OVN controller host.

    Returns the first SSH-able host running ovn-controller.
    The result is cached for subsequent calls.
    """
    if 'ssh_client' in _cache:
        return _cache['ssh_client']
    from tobiko.openstack import topology
    agents = agent_mod.list_networking_agents(
        binary=agent_mod.OVN_CONTROLLER)
    for agent in agents:
        candidate = topology.get_openstack_node(
            hostname=agent['host']).ssh_client
        if candidate is not None:
            _cache['ssh_client'] = candidate
            return candidate
    return None


def _get_ovn_controller_container_prefix() -> str:
    from tobiko.openstack import topology
    os_topology = topology.get_openstack_topology()
    if os_topology.has_containers:
        runtime = os_topology.container_runtime_cmd
        container = os_topology.get_agent_container_name(
            agent_mod.OVN_CONTROLLER)
        return f"{runtime} exec {container} "
    return ""


# --- OVN DB host abstraction ---


def _run_on_ovn_db_hosts(
        db: str,
        command: str
) -> typing.List[typing.Tuple[str, str]]:
    """Run a command on all OVN DB hosts for the given database.

    For podified: executes inside ovsdbserver-{nb,sb} pods.
    For TripleO/devstack: SSHs into controller nodes.

    :param db: Database short name ('nb' or 'sb').
    :param command: Shell command to execute.
    :returns: List of (host_identifier, stdout) tuples.
    """
    from tobiko import podified
    if podified.has_podified_cp():
        label = _PODIFIED_POD_LABEL[db]
        pod_names = podified.get_pod_names(
            labels={'service': label})
        results = []
        for pod_qname in pod_names:
            pod_name = pod_qname.split('/')[-1]
            result = podified.execute_in_pod(
                pod_name, command)
            results.append((pod_name, result.out()))
        return results
    from tobiko.openstack import topology
    results = []
    for node in topology.list_openstack_nodes(
            group='controller'):
        output = sh.execute(
            command, ssh_client=node.ssh_client,
            sudo=True)
        results.append((node.hostname, output.stdout))
    return results


def _run_on_ovn_db_host(
        host_id: str,
        command: str) -> str:
    """Run a command on a specific OVN DB host.

    :param host_id: Hostname (TripleO/devstack) or pod name (podified).
    :param command: Shell command to execute.
    :returns: stdout string.
    """
    from tobiko import podified
    if podified.has_podified_cp():
        result = podified.execute_in_pod(host_id, command)
        return result.out()
    from tobiko.openstack import topology
    node_ssh = topology.get_openstack_node(
        hostname=host_id).ssh_client
    output = sh.execute(
        command, ssh_client=node_ssh, sudo=True)
    return output.stdout


# --- OVN DB connection resolution ---


def _get_podified_ovndb_connection(ovndb: str) -> str:
    from tobiko import podified
    cluster_name = _PODIFIED_CLUSTER_NAME[ovndb]
    db_address = podified.get_ovndbcluter(
        cluster_name)['status']['dbAddress']
    ssl_params = ''
    if 'ssl' in db_address:
        ssh_client = get_ovndb_ssh_client()
        prefix = _get_ovn_controller_container_prefix()
        command = (f"{prefix}"
                   "ps -o command -C ovn-controller --no-headers -ww")
        command_result = sh.execute(
            command, ssh_client=ssh_client, sudo=True).stdout.strip()
        for param in ('p', 'c', 'C'):
            match = re.search(
                r' -{} [^\s]+'.format(param), command_result)
            if match:
                ssl_params += match.group()
    return db_address + ssl_params


def _get_traditional_ovndb_connection(ovndb: str) -> str:
    ssh_client = get_ovndb_ssh_client()
    if ovndb == NBDB:
        command_result = sh.execute(
            "ovs-vsctl get open . external_ids:ovn-remote | "
            "sed -e 's/\"//g' | sed 's/6642/6641/g'",
            ssh_client=ssh_client, sudo=True)
        if 'ovsdbserver-sb' in command_result.stdout:
            db_address = command_result.stdout.replace(
                'ovsdbserver-sb', 'ovsdbserver-nb')
        else:
            db_address = command_result.stdout
    else:
        command_result = sh.execute(
            "ovs-vsctl get open . external_ids:ovn-remote | "
            "sed -e 's/\"//g'",
            ssh_client=ssh_client, sudo=True)
        db_address = command_result.stdout
    ssl_params = ''
    if 'ssl' in command_result.stdout:
        ssl_params = ' -p {} -c {} -C {} '.format(
            '/etc/pki/tls/private/ovn_controller.key',
            '/etc/pki/tls/certs/ovn_controller.crt',
            '/etc/ipa/ca.crt')
    return db_address.strip() + ssl_params


def _get_ovndb_connection(ovndb: str) -> str:
    if ovndb in _ovndb_connections:
        return _ovndb_connections[ovndb]
    from tobiko import podified
    if podified.has_podified_cp():
        connection = _get_podified_ovndb_connection(ovndb)
    else:
        connection = _get_traditional_ovndb_connection(ovndb)
    _ovndb_connections[ovndb] = connection
    LOG.debug('OVN %s connection: %s', ovndb, connection)
    return connection


# --- OVN DB command building ---


def build_ovndb_command(ovndb: str,
                        query: str,
                        output_format: typing.Optional[str] = None,
                        no_leader_only: bool = True) -> str:
    """Build a complete OVN database command string.

    :param ovndb: Database identifier, either 'nbdb' or 'sbdb'.
    :param query: OVN subcommand and arguments
        (e.g. 'find ACL external_ids:...').
    :param output_format: Output format ('json', 'table', etc.).
        If None, no --format flag is added.
    :param no_leader_only: If True, add --no-leader-only flag.
    :returns: Full command string including container exec prefix
        if applicable.
    """
    if ovndb not in _OVN_DB_BINARY:
        raise ValueError(
            f"Invalid ovndb value '{ovndb}'. "
            f"Must be one of: {', '.join(_OVN_DB_BINARY)}")

    binary = _OVN_DB_BINARY[ovndb]
    connection = _get_ovndb_connection(ovndb)
    prefix = _get_ovn_controller_container_prefix()

    flags = f"--db={connection}"
    if output_format is not None:
        flags = f"--format {output_format} {flags}"
    if no_leader_only:
        flags = f"--no-leader-only {flags}"

    return f"{prefix}{binary} {flags} {query}"


def _parse_ovn_db_show(ovn_db_show_str: str) -> typing.Dict[
        str, typing.List[str]]:
    """Parse ``ovn-nbctl show`` / ``ovn-sbctl show`` text output
    into a dict keyed by section header, with sorted value lists.
    """
    ovn_db_dict: typing.Dict[str, typing.List[str]] = {}
    current_section = ''
    for line in ovn_db_show_str.splitlines():
        if not re.match(r'^\s+', line):
            current_section = line.strip()
            ovn_db_dict[current_section] = []
        else:
            ovn_db_dict[current_section].append(line.strip())
    for section in ovn_db_dict:
        ovn_db_dict[section].sort()
    return ovn_db_dict


def dump_ovn_databases() -> typing.Dict[str, typing.Any]:
    """Dump NB and SB databases."""
    ssh_client = get_ovndb_ssh_client()
    dumps: typing.Dict[str, typing.Any] = {}
    for ovndb in (NBDB, SBDB):
        command = build_ovndb_command(ovndb, 'show')
        LOG.debug('Dump %s database with command: %s',
                  ovndb, command)
        output = sh.execute(
            command, ssh_client=ssh_client, sudo=True)
        dumps[ovndb] = _parse_ovn_db_show(output.stdout)
    return dumps


# --- OVN DB service model detection ---


@functools.lru_cache()
def get_ovn_db_service_model() -> str:
    """Detect the OVN DB service model (RAFT or HA).

    Reads the first bytes of the ovnnb_db.db file to determine the
    database format: CLUSTER header = RAFT, JSON header = HA.

    For podified deployments, executes inside the ovsdbserver-nb pod.
    For TripleO/devstack, SSHs into a controller node.
    """
    from tobiko import podified
    if podified.has_podified_cp():
        pod_names = podified.get_pod_names(
            labels={'service': 'ovsdbserver-nb'})
        if pod_names:
            pod_name = pod_names[0].split('/')[-1]
            result = podified.execute_in_pod(
                pod_name,
                'head -c 16 /etc/ovn/ovnnb_db.db')
            output = result.out().strip()
            if 'CLUSTER' in output:
                return OVN_RAFT
            if 'JSON' in output:
                return OVN_HA

    # For TripleO/devstack the DB file is on the host filesystem
    # (not inside the ovn_controller container).
    from tobiko.openstack import topology
    for node in topology.list_openstack_nodes(
            group='controller'):
        if node.ssh_client is None:
            continue
        cmd = ('sh -c "find /var/ -name ovnnb_db.db 2>/dev/null '
               '| head -1 | xargs head -c 16"')
        output = sh.execute(
            cmd, ssh_client=node.ssh_client,
            sudo=True).stdout.strip()
        if 'CLUSTER' in output:
            return OVN_RAFT
        if 'JSON' in output:
            return OVN_HA

    raise InvalidDBServiceModel(
        reason='Could not determine OVN DB service model')


def is_ovn_using_raft() -> bool:
    try:
        return get_ovn_db_service_model() == OVN_RAFT
    except InvalidDBServiceModel:
        return False


def is_ovn_using_ha() -> bool:
    try:
        return get_ovn_db_service_model() == OVN_HA
    except InvalidDBServiceModel:
        return False


# --- OVN DB connection string helpers ---


def _get_podified_ovn_db_connections() -> typing.Dict[str, str]:
    """Fetch OVN DB connection strings from a neutron pod."""
    from tobiko import podified
    pod_names = podified.get_pod_names(
        labels={'service': 'neutron'})
    if not pod_names:
        tobiko.fail('No neutron pods found')
    pod_name = pod_names[0].split('/')[-1]
    result = podified.execute_in_pod(
        pod_name,
        'grep -rh "^ovn_.*_connection" /etc/neutron')
    con_strs: typing.Dict[str, str] = {}
    for line in result.out().strip().splitlines():
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if key == 'ovn_nb_connection':
            con_strs['nb'] = value
        elif key == 'ovn_sb_connection':
            con_strs['sb'] = value
    LOG.debug('OVN DB connections from neutron pod: %s', con_strs)
    return con_strs


def get_ovn_db_connections() -> typing.Dict[str, str]:
    """Fetch OVN DB connection strings.

    For podified deployments, reads from a neutron pod.
    For TripleO/devstack, reads from ml2_conf.ini via SSH.

    Returns a dict keyed by 'nb' and 'sb'.
    """
    from tobiko import podified
    if podified.has_podified_cp():
        return _get_podified_ovn_db_connections()
    from tobiko.openstack import topology
    ml2_conf = topology.get_config_file_path('ml2_conf.ini')
    ssh_client = get_ovndb_ssh_client()
    con_strs: typing.Dict[str, str] = {}
    for db in OVNDBS:
        cmd = 'crudini --get {} ovn ovn_{}_connection'.format(
            ml2_conf, db)
        output = sh.execute(
            cmd, ssh_client=ssh_client, sudo=True).stdout
        con_strs[db] = output.splitlines()[0]
    LOG.debug('OVN DB connection string fetched from %s: %s',
              ml2_conf, con_strs)
    return con_strs


def parse_ips_from_db_connections(con_str):
    """Parse OVN DB connection string to get IP addresses.

    Returns a tuple of (list of netaddr.IPAddress, port string).
    """
    addrs = []
    ref_port = ''
    ref_protocol = ''
    for substr in con_str.split(','):
        try:
            protocol, con = substr.split(':', 1)
            tmp_addr, port = con.rsplit(':', 1)
        except (ValueError, AttributeError) as ex:
            msg = ('Fail to parse "{}" substring of "{}" OVN DB '
                   'connection string'.format(substr, con_str))
            LOG.error(msg)
            raise InvalidDBConnString(message=msg) from ex
        if not ref_port:
            ref_port = port
        if not ref_protocol:
            ref_protocol = protocol
        if protocol != ref_protocol or port != ref_port:
            msg = ('Ports or protocols are not identical for OVN DB'
                   'connections: {}'.format(con_str))
            LOG.error(msg)
            raise InvalidDBConnString(message=msg)
        try:
            addr = netaddr.IPAddress(tmp_addr.strip(']['))
        except ValueError as ex:
            msg = 'Invalid IP address "{}" in "{}"'.format(
                tmp_addr, con_str)
            LOG.error(msg)
            raise InvalidDBConnString(message=msg) from ex
        addrs.append(addr)
    LOG.debug('Addresses parsed from OVN DB connection string: %s',
              addrs)
    return addrs, ref_port


# --- OVN DB ctl files and sync status ---


def _get_ovn_db_ctl_path(db: str) -> str:
    """Get the ctl file path for the given database.

    For podified, returns the known path inside ovsdbserver pods.
    For TripleO/devstack, searches /var/ on a controller node.
    """
    from tobiko import podified
    if podified.has_podified_cp():
        return _PODIFIED_CTL_PATH[db]
    from tobiko.openstack import topology
    node = topology.list_openstack_nodes(
        group='controller')[0]
    cmd = 'find /var/ -name ovn{}_db.ctl'.format(db)
    found = sh.execute(cmd,
                       ssh_client=node.ssh_client,
                       expect_exit_status=None,
                       sudo=True).stdout
    candidates = found.strip().splitlines()
    if len(candidates) != 1:
        tobiko.fail(
            'Expected exactly 1 ovn{}_db.ctl file, '
            'found {}: {}'.format(
                db, len(candidates), candidates))
    return candidates[0]


def find_ovn_db_ctl_files() -> typing.Dict[str, str]:
    """Get ctl file paths for NB and SB databases.

    :returns: Dict keyed by 'nb'/'sb' with ctl file paths.
    """
    ctl_files = {}
    for db in OVNDBS:
        ctl_files[db] = _get_ovn_db_ctl_path(db)
    LOG.debug('OVN DB ctl files: %s', ctl_files)
    return ctl_files


def get_ovn_db_sync_status() -> typing.Dict[
        str, typing.List[typing.List[str]]]:
    """Query sync status for NB and SB on each OVN DB host."""
    db_sync_status: typing.Dict[
        str, typing.List[typing.List[str]]] = {}
    ctl_files = find_ovn_db_ctl_files()
    for db in OVNDBS:
        ctl_file = ctl_files[db]
        cmd = ('ovs-appctl -t {} '
               'ovsdb-server/sync-status'.format(ctl_file))
        for host_id, stdout in _run_on_ovn_db_hosts(db, cmd):
            if 'state: active' in stdout:
                status = 'active'
            elif 'state: backup' in stdout:
                status = 'backup'
            else:
                status = 'unknown'
            db_sync_status.setdefault(db, [])
            db_sync_status[db].append([host_id, status])
    LOG.debug('OVN DB status for all hosts: %s',
              db_sync_status)
    return db_sync_status


# --- RAFT cluster functions ---


def get_raft_cluster_details(
        host_id: str,
        database: str) -> typing.Dict[str, typing.Any]:
    """Return RAFT cluster details from a specific host.

    :param host_id: Hostname (TripleO/devstack) or pod name
        (podified).
    :param database: Database short name ('nb' or 'sb').
    """
    if database not in OVNDBS:
        raise ValueError(
            '{} database is not in the list {}'.format(
                database, OVNDBS))
    ctl_files = find_ovn_db_ctl_files()
    cmd = 'ovs-appctl -t {} cluster/status {}'.format(
        ctl_files[database], DBNAMES[database])
    stdout = _run_on_ovn_db_host(host_id, cmd)
    cluster_status: typing.Dict[str, typing.Any] = {}
    section = ''
    for line in stdout.splitlines():
        if not re.match(r'^\s+', line):
            line_data = line.strip().split(':', 1)
            if len(line_data) == 1:
                continue
            section, data = line_data
            if not data.strip():
                cluster_status[section] = []
                continue
            cluster_status[section] = data.strip()
        else:
            cluster_status[section].append(line.strip())
    return cluster_status


def collect_raft_cluster_details(
        database: str) -> typing.List[typing.Dict]:
    """Collect RAFT cluster details from all OVN DB hosts.

    Restarts collection if any host has 'candidate' role
    (leader election in progress).
    """
    ctl_files = find_ovn_db_ctl_files()
    cmd = 'ovs-appctl -t {} cluster/status {}'.format(
        ctl_files[database], DBNAMES[database])
    cluster_details: typing.List[typing.Dict] = []
    for _ in tobiko.retry(timeout=30, interval=1):
        restart_collection = False
        cluster_details = []
        for host_id, stdout in _run_on_ovn_db_hosts(
                database, cmd):
            details = _parse_cluster_status(stdout)
            details['host'] = host_id
            if details['Role'].lower() == 'candidate':
                LOG.warning(
                    'Cluster not stable. '
                    'Leader election in progress')
                LOG.debug(
                    'Cluster details from %s:\n%s',
                    host_id, details)
                restart_collection = True
                break
            cluster_details.append(details)
        if not restart_collection:
            break
    return cluster_details


def _parse_cluster_status(
        stdout: str) -> typing.Dict[str, typing.Any]:
    """Parse ovs-appctl cluster/status output."""
    cluster_status: typing.Dict[str, typing.Any] = {}
    section = ''
    for line in stdout.splitlines():
        if not re.match(r'^\s+', line):
            line_data = line.strip().split(':', 1)
            if len(line_data) == 1:
                continue
            section, data = line_data
            if not data.strip():
                cluster_status[section] = []
                continue
            cluster_status[section] = data.strip()
        else:
            cluster_status[section].append(line.strip())
    return cluster_status


def check_raft_timers(node_details: typing.Dict) -> None:
    """Validate RAFT communication timers."""
    election_timer = int(node_details['Election timer'])
    leader_id = node_details['Leader']
    for srv_str in node_details['Servers']:
        if 'self' in srv_str:
            continue
        if node_details['Role'] == 'follower' and \
                not srv_str.startswith(leader_id):
            continue
        timer = re.findall(
            r'last msg [0-9]+ ms ago', srv_str)
        if len(timer) != 1:
            msg = ('Failed to parse connection timer '
                   'from "{}"'.format(srv_str))
            LOG.error(msg)
            LOG.debug(node_details)
            raise RAFTStatusError(message=msg)
        if election_timer < int(timer[0].split()[2]):
            msg = ('Cluster communication time {} is higher '
                   'than election timer {}'.format(
                       int(timer[0].split()[2]),
                       election_timer))
            LOG.error(msg)
            LOG.debug(node_details)
            raise RAFTStatusError(message=msg)


def get_raft_ports() -> typing.Dict[str, str]:
    """Get RAFT cluster ports for NB and SB."""
    ports: typing.Dict[str, str] = {}
    for db in OVNDBS:
        ctl_files = find_ovn_db_ctl_files()
        cmd = 'ovs-appctl -t {} cluster/status {}'.format(
            ctl_files[db], DBNAMES[db])
        results = _run_on_ovn_db_hosts(db, cmd)
        if results:
            details = _parse_cluster_status(results[0][1])
            _, port = parse_ips_from_db_connections(
                details['Address'])
            ports[db] = port
    return ports


def get_leader_ovsdb() -> typing.List[typing.Dict]:
    """Find the RAFT leader for each OVN database."""
    cluster_details: typing.List[typing.Dict] = []
    ctl_files = find_ovn_db_ctl_files()
    for db in OVNDBS:
        leader_map: typing.Dict[str, str] = {}
        cmd = 'ovs-appctl -t {} cluster/status {}'.format(
            ctl_files[db], DBNAMES[db])
        for host_id, stdout in _run_on_ovn_db_hosts(db, cmd):
            details = _parse_cluster_status(stdout)
            if details['Role'] == 'leader':
                leader_map = {
                    'db': db,
                    'ctlfile': ctl_files[db],
                    'Role': 'leader',
                    'host': host_id}
        cluster_details.append(leader_map)
    return cluster_details


def transfer_leadership_ovsdb(
        cluster_details: typing.List[typing.Dict]) -> None:
    """Trigger RAFT leadership transfer."""
    for db_info in cluster_details:
        cmd = ("ovs-appctl -t {} cluster/failure-test "
               "transfer-leadership".format(db_info['ctlfile']))
        _run_on_ovn_db_host(db_info['host'], cmd)
    LOG.debug("Ovsdb leadership transferred")
