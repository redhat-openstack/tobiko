# Copyright (c) 2020 Red Hat
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

import random
import re

from oslo_log import log

import tobiko
from tobiko.openstack import topology
from tobiko.shell import sh
from tobiko.tripleo import pacemaker


LOG = log.getLogger(__name__)


def get_filtered_node_containers(node, containers_regex):
    """Search all containers are matched with containers_regex list

    :param node: Node to search containers on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :param containers_regex: List of regex that can be matched to containers
    :type containers_regex: list of strings
    :return: List of contatiner names
    :rtype: list of strings
    """
    filtered_containers = []
    # 'docker' is used here in order to be compatible with old OSP versions.
    # On versions with podman, 'docker' command is linked to 'podman'
    result = sh.execute(
            'docker ps --format "{{.Names}}"',
            ssh_client=node.ssh_client, sudo=True)
    all_node_containers = result.stdout.strip().split('\n')
    for container in all_node_containers:
        container = container.strip('"')
        if any(re.fullmatch(reg, container) for reg in containers_regex):
            filtered_containers.append(container)
    return filtered_containers


def get_nodes_for_groups(groups):
    """Search for all nodes that are matched with the specified groups

    :param groups: List of groups nodes can belong to
    :type groups: list
    :return: List of nodes that belong to the specified groups
    :rtype: list of tobiko.openstack.topology.OpenStackTopologyNode
    """
    nodes = []
    for node in topology.list_openstack_nodes():
        for group in node.groups:
            if group in groups:
                nodes.append(node)
    return(nodes)


def get_config_files(node, kolla_jsons, conf_ignorelist, scripts_to_check):
    """Return the list of configuration files according to kolla JSONs

    Kolla has the container execution commands in the matched JSON files.
    Need to get all the '--config-file <file_name>' parameters from those
    JSON files.
    It is possible that the container is executed with the set of commands
    are written in a separate script instead of a single command so need
    to follow those scripts to get configuration files from there too.

    :param node: Node to search configuration files on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :param kolla_jsons: Path to kolla json files to get commands from
    :type kolla_jsons: list
    :param conf_ignorelist: Configuration files to ignore
    :type conf_ignorelist: list
    :param scripts_to_check: Sripts to look for configuration files in if those
        scripts will be found in kolla json files.
    :type scripts_to_check: list
    :return: List of config files paths within containers
    :rtype: list
    """
    cmds = sh.execute(
            f"jq '.command' {' '.join(kolla_jsons)}",
            ssh_client=node.ssh_client,
            expect_exit_status=None, sudo=True).stdout.strip().split('\n')
    LOG.debug(f'{node.name} run containers with commands {cmds}')
    config_files = set()
    for cmd in cmds:
        cmd = cmd.strip('"')
        if cmd in scripts_to_check:
            LOG.debug(f'{cmd} is recognized as script to search '
                      'for config files in')
            oc_script_location = sh.execute(
                    f'find /var/lib | grep {cmd} | grep -v overlay',
                    ssh_client=node.ssh_client,
                    sudo=True).stdout.strip().split('\n')[0]
            cmd = sh.execute(
                    f'cat {oc_script_location}',
                    ssh_client=node.ssh_client, sudo=True).stdout.strip()
            cmd = cmd.strip('"')
        temp_conf_files = re.findall('--config-file [^ \n]*', cmd)
        for conf_file in temp_conf_files:
            conf_file = conf_file.split(' ')[1]
            if conf_file in conf_ignorelist:
                LOG.debug(f'{conf_file} is in ignore list')
                continue
            config_files.add(conf_file)
    LOG.debug(f'There are {config_files} on {node.name}')
    return config_files


def get_node_neutron_containers(node):
    """Return list of all neutron containers are available on the node

    :param node: Node to search containers on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :return: List of neutron containers names
    :rtype: list of strings
    """
    neutron_containers = ['neutron_((ovs|metadata|l3)_agent|dhcp|api)',
                          'ovn_metadata_agent']
    return get_filtered_node_containers(node, neutron_containers)


def get_node_ovn_containers(node):
    """Return list of all ovn containers are available on the node

    :param node: Node to search containers on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :return: List of neutron containers names
    :rtype: list of strings
    """
    neutron_containers = [
            'ovn_(controller|metadata_agent)',
            r'ovn-dbs-bundle-(podman|docker)-\d*']
    return get_filtered_node_containers(node, neutron_containers)


def get_node_neutron_config_files(node):
    """Return all relevant neutron config files

    :param node: Overcloud node to search log files on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :return: List of config files paths within neutron containers
    :rtype: list of strings
    """
    kolla_jsons = ['/var/lib/kolla/config_files/neutron*']
    conf_ignorelist = ['/usr/share/neutron/neutron-dist.conf']
    scripts_to_check = ['/neutron_ovs_agent_launcher.sh']
    config_files = get_config_files(node,
                                    kolla_jsons,
                                    conf_ignorelist,
                                    scripts_to_check)
    return config_files


def get_node_ovn_config_files():
    """Return all relevant ovn config files

    :return: List of config files paths within ovn containers
    :rtype: list of strings
    """
    return ['/etc/openvswitch/default.conf']


def get_pacemaker_resource_from_container(container):
    """Returns pacemaker resource name or None

    :param container: Name of the container
    :type container: string
    :return: pacemaker resource name or None
    :rtype: string
    """
    pcs_resource = None
    resource_candidate = re.search(r'(.*)-(docker|podman)-\d', container)
    if resource_candidate:
        pcs_resource = resource_candidate.group(1)
    return pcs_resource


def get_node_logdir_from_pcs(node, container):
    """ Return the logdir for a given pacemaker resource

    :param node: Node the container is running on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :param container: Name of the container
    :type container: string
    :return: Path to the logfiles on the container
    :rtype: string
    """
    pcs_resource = get_pacemaker_resource_from_container(container)
    if pcs_resource is None:
        return
    logdir = None
    out_lines = pacemaker.run_pcs_resource_operation(
            pcs_resource, pacemaker.SHOW, node=node.ssh_client).splitlines()
    log_files_regex = re.compile(
        r'^\s*options=.*source-dir=(.*) target-dir=.*-log-files\)$')
    for line in out_lines:
        log_files_match = log_files_regex.search(line)
        if log_files_match:
            logdir = log_files_match.group(1)
            if line.endswith('-new-log-files)'):
                break
            else:
                continue
    return logdir


def get_pacemaker_resource_logfiles(node, container):
    logfiles = []
    exclude_pid_files = 'ovn-controller.pid'
    resource = get_pacemaker_resource_from_container(container)
    out_lines = pacemaker.run_pcs_resource_operation(
        resource, pacemaker.SHOW, node=node.ssh_client).splitlines()
    run_files_regex = re.compile(
        r'^\s*options=.*source-dir=(.*) target-dir=.*-run-files\)$')
    for line in out_lines:
        run_files_match = run_files_regex.search(line)
        if run_files_match:
            pid_files = (sh.execute(f'find {run_files_match.group(1)} '
                                    f'-name *.pid ! -name {exclude_pid_files}',
                                    ssh_client=node.ssh_client).
                         stdout.splitlines())
            break
    pids = sh.execute(f'cat {" ".join(pid_files)}',
                      ssh_client=node.ssh_client,
                      sudo=True).stdout.splitlines()
    for pid in pids:
        cmd_stdout = sh.execute(f'docker exec -u root {container} '
                                f'cat /proc/{pid}/cmdline',
                                ssh_client=node.ssh_client,
                                sudo=True).stdout
        for log_file in re.findall('--log-file=[^ \n\x00]*', cmd_stdout):
            logfiles.append(log_file.split('=')[1])
    return logfiles


def get_default_container_logfiles(container):
    CONTAINER_LOGFILE_DICT_LIST = [
        {'container_regex': 'ovn_controller',
         'default_logfiles': ['/var/log/openvswitch/ovn-controller.log']}]
    for cont_logfile_dict in CONTAINER_LOGFILE_DICT_LIST:
        if re.fullmatch(cont_logfile_dict['container_regex'], container):
            return cont_logfile_dict['default_logfiles']
    raise RuntimeError(f'No default log file found for container {container}')


def get_container_logfiles(node, container):
    """ Return the logfiles of the processes that are executed on the container

    :param node: Node the container is running on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :param container: Name of the container
    :type container: string
    :return: Path to the logfiles on the container
    :rtype: list
    """
    cmd = sh.execute(
            f'docker exec -u root {container} cat /run_command',
            ssh_client=node.ssh_client, sudo=True)
    cmd_stdout = cmd.stdout.strip()
    if 'pacemaker_remoted' in cmd_stdout:
        return get_pacemaker_resource_logfiles(node, container)
    if ' ' not in cmd_stdout:  # probably script as no space in the command
        cmd = sh.execute(
                f'docker exec -u root {container} cat {cmd_stdout}',
                ssh_client=node.ssh_client, sudo=True)
        cmd_stdout = cmd.stdout.strip()
    LOG.debug(f'The following command is executed in {container} container '
              f'on {node.name} node:\n{cmd_stdout}')

    log_files = []
    for log_file in re.findall('--log-file=[^ \n]*', cmd_stdout):
        log_files.append(log_file.split('=')[1])
    if log_files:
        return log_files

    if re.findall(r'--log-file[^=]*$', cmd_stdout):
        LOG.debug(f'Using default log file for the command: {cmd_stdout}')
        return get_default_container_logfiles(container)
    LOG.warning(f'No log found for the command: {cmd_stdout}')
    return None


def log_random_msg(node, container, logfile):
    """Print random message to the container log file

    :param node: Node the container is running on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :param container: Name of the container
    :type container: string
    :param logfile: Path to the logfile on the container
    :type logfile: string
    :return: Message that has been printed to container log file
    :rtype: string
    """
    symbols = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    random_msg = ''.join(random.choice(symbols) for i in range(30))
    LOG.debug(f'Trying to print {random_msg} string to {logfile} log file '
              f'in {container} container on {node.name} node')
    log_msg(node, container, logfile, random_msg)
    return random_msg


def log_msg(node, container, logfile, msg):
    """Print random message to the container log file

    :param node: Node the container is running on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :param container: Name of the container
    :type container: string
    :param logfile: Path to the logfile on the container
    :type logfile: string
    :param msg: Message to log
    :type msg: string
    """
    cmd = f"sh -c 'echo {msg} >> {logfile}'"
    sh.execute(f'docker exec -u root {container} {cmd}',
               ssh_client=node.ssh_client, sudo=True)


def find_msg_in_file(node, logfile, message, rotated=False):
    """Search for the message in the logfile

    :param node: Node the container is running on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    :param logfile: Path of the logfile
    :type logfile: string
    :param message: Message to search for
    :type message: string
    :param rotated: Variable to flag that log file has to be rotated
        so the name will be ended by '.1'
    :type rotated: bool
    :return: True if message exists in file or False otherwise
    :rtype: bool
    """
    if rotated:
        suffix = ".1"
    else:
        suffix = ""
    LOG.debug(f'Searching for {message} in {logfile}{suffix} on {node.name}')
    result = sh.execute(f'grep -h {message} {logfile}{suffix}',
                        ssh_client=node.ssh_client,
                        expect_exit_status=None, sudo=True)
    if result.stderr:
        tobiko.fail(f'Failed to read {logfile} on {node.name}:\n'
                    f'{result.stderr}')
    elif result.stdout.strip() == message:
        return True
    else:
        return False


def rotate_logs(node):
    """Rotate all the container logs using 'logrotate'

    :param node: Node to rotate logs on
    :type node: class: tobiko.openstack.topology.OpenStackTopologyNode
    """
    containers = get_filtered_node_containers(node, ['logrotate.*', ])
    if not containers:
        tobiko.skip_test('No logrotate container has been found')
    container = containers[0]
    sh.execute(f'docker exec -u root {container} logrotate '
               '-f /etc/logrotate-crond.conf',
               ssh_client=node.ssh_client, sudo=True)


def has_docker():
    return get_docker_version() is not None


skip_unless_has_docker = tobiko.skip_unless(
    "requires docker on controller nodes", has_docker)


def get_docker_version():
    # use a fixture to save the result
    return tobiko.setup_fixture(
        DockerVersionFixture).docker_version


class DockerVersionFixture(tobiko.SharedFixture):

    docker_version = None

    def setup_fixture(self):
        controller = topology.find_openstack_node(group='controller')
        try:
            result = sh.execute('docker --version',
                                ssh_client=controller.ssh_client)
        except sh.ShellCommandFailed:
            pass
        else:
            self.docker_version = result.stdout
