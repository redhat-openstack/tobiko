from __future__ import absolute_import

import io
import re

from oslo_log import log
import pandas

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack import topology
from tobiko.tripleo import overcloud
from tobiko.shell import sh
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


class OvercloudProcessesException(tobiko.TobikoException):
    message = "not all overcloud processes are in running state, " \
              "{process_error}"


def get_overcloud_node_processes_table(ssh_client: ssh.SSHClientType):
    """
    get processes tables from overcloud node

       returns :
[root@controller-0 ~]# ps -axw -o "%U" -o "|%p" -o "|%P" -o "|%C" -o "|%z" -o
"|%x" -o "|%c" -o "|%a" |grep -v 'ps -aux'|head
USER    |    PID|   PPID|%CPU|   VSZ|    TIME|COMMAND        |COMMAND
|overcloud_node
root    |      1|      0| 1.3|246892|01:08:57|systemd        |/usr/lib/systemd
controller-0 ...
/systemd --switched-root --system --deserialize 18
root    |      2|      0| 0.0|     0|00:00:00|kthreadd       |[kthreadd]
root    |      3|      2| 0.0|     0|00:00:00|rcu_gp         |[rcu_gp]
root    |      4|      2| 0.0|     0|00:00:00|rcu_par_gp     |[rcu_par_gp]
root    |      6|      2| 0.0|     0|00:00:00|kworker/0:0H-ev|[kworker/0:0H
-events_highpri]
root    |      8|      2| 0.0|     0|00:00:00|mm_percpu_wq   |[mm_percpu_wq]
root    |      9|      2| 0.0|     0|00:00:06|ksoftirqd/0    |[ksoftirqd/0]
root    |     10|      2| 0.0|     0|00:04:28|rcu_sched      |[rcu_sched]
root    |     11|      2| 0.0|     0|00:00:05|migration/0    |[migration/0]

    :return: dataframe of overcloud node processes dataframe
    """

    output = sh.execute(
        "ps -axw -o \"%U\" -o \"DELIM%p\" -o \"DELIM%P\" -o \"DELIM%C\" -o "
        "\"DELIM%z\" -o \"DELIM%x\" -o \"DELIM%c\" -o \"DELIM%a\" |grep -v "
        "'ps -axw' |sed 's/\"/''/g'",
        ssh_client=ssh_client).stdout
    stream = io.StringIO(output)
    table: pandas.DataFrame = pandas.read_csv(
        stream, sep='DELIM', header=None, skiprows=1)
    table.replace(to_replace=' ', value="", regex=True, inplace=True)
    table.columns = ['USER', 'PID', 'PPID', 'CPU', 'VSZ', 'TIME', 'PROCESS',
                     'PROCESS_ARGS']
    # pylint: disable=unsupported-assignment-operation
    hostname = sh.get_hostname(ssh_client=ssh_client)
    table['overcloud_node'] = hostname

    LOG.debug("Successfully got overcloud nodes processes status table")
    return table


def get_overcloud_nodes_running_process(process):
    """
    Check what nodes are running the specifies
    process: exact str of a process name as seen in ps -axw -o "%c"
    :return: list of overcloud nodes
    """
    oc_procs_df = overcloud.get_overcloud_nodes_dataframe(
                                            get_overcloud_node_processes_table)
    oc_nodes_running_process = oc_procs_df.query('PROCESS=="{}"'.format(
        process))['overcloud_node'].unique()
    return oc_nodes_running_process


def check_if_process_running_on_overcloud(process):
    """
    Check what nodes are running the specifies
    process: exact str of a process name as seen in ps -axw -o "%c"
    :return: list of overcloud nodes
    """
    oc_procs_df = overcloud.get_overcloud_nodes_dataframe(
                                          get_overcloud_node_processes_table)
    if not oc_procs_df.query('PROCESS=="{}"'.format(process)).empty:
        return True
    else:
        return False


class OvercloudProcessesStatus(object):
    """
    class to handle processes checks,
    checks that all of these are running in the overcloud:
    'ovsdb-server','pcsd', 'corosync', 'beam.smp', 'mysqld', 'redis-server',
    'haproxy', 'nova-conductor', 'nova-scheduler', 'neutron-server',
    'nova-compute', 'glance-api'
    """
    def __init__(self):
        self.processes_to_check = ['ovsdb-server', 'pcsd', 'corosync',
                                   'beam.smp', 'mysqld', 'redis-server',
                                   'haproxy', 'nova-conductor',
                                   'nova-scheduler', 'neutron-server',
                                   'nova-compute', 'glance-api']

        num_northd_proc = 'all' if overcloud.is_ovn_using_raft() else 1
        self.ovn_processes_to_check_per_node = [{'name': 'ovn-controller',
                                                 'node_group': 'controller',
                                                 'number': 'all'},
                                                {'name': 'ovn-controller',
                                                 'node_group': 'compute',
                                                 'number': 'all'},
                                                {'name': 'ovn-northd',
                                                 'node_group': 'controller',
                                                 'number': num_northd_proc}]

        self.oc_procs_df = overcloud.get_overcloud_nodes_dataframe(
                                            get_overcloud_node_processes_table)

    def _basic_overcloud_process_running(self, process_name):
        # osp16/python3 process is "neutron-server:"
        if process_name == 'neutron-server' and \
                self.oc_procs_df.query('PROCESS=="{}"'.format(
                process_name)).empty:
            process_name = 'neutron-server:'
        # osp17 mysqld process name is mysqld_safe
        if process_name == 'mysqld' and \
                self.oc_procs_df.query('PROCESS=="{}"'.format(
                process_name)).empty:
            process_name = 'mysqld_safe'
        # redis not deployed on osp17 by default, only if some
        # other services such as designate and octavia are deployed
        if (process_name == 'redis-server' and
                not overcloud.is_redis_expected()):
            redis_message = ("redis-server not expected on OSP 17 "
                             "and later releases by default")
            if self.oc_procs_df.query(
                    f'PROCESS=="{process_name}"').empty:
                LOG.info(redis_message)
                return
            else:
                raise OvercloudProcessesException(
                    process_error=redis_message)

        if not self.oc_procs_df.query('PROCESS=="{}"'.format(
                process_name)).empty:
            LOG.info("overcloud processes status checks: "
                     "process {} is  "
                     "in running state".format(process_name))
            return
        else:
            LOG.info("Failure : overcloud processes status checks:"
                     "process {} is not running ".format(
                      process_name))
            raise OvercloudProcessesException(
                process_error="process {} is not running ".format(
                              process_name))

    @property
    def basic_overcloud_processes_running(self):
        """
        Checks that the oc_procs_df dataframe has all of the list procs
        :return: Bool
        """
        for attempt in tobiko.retry(timeout=300., interval=1.):
            try:
                for process_name in self.processes_to_check:
                    self._basic_overcloud_process_running(process_name)
            except OvercloudProcessesException:
                if attempt.is_last:
                    LOG.error('Not all overcloud processes are running')
                    raise
                LOG.info('Retrying overcloud processes: %s', attempt.details)
                self.oc_procs_df = overcloud.get_overcloud_nodes_dataframe(
                    get_overcloud_node_processes_table)

            # if all procs are running we can return true
            return True

    def _ovn_overcloud_process_validations(self, process_dict):
        if not self.oc_procs_df.query('PROCESS=="{}"'.format(
                process_dict['name'])).empty:
            LOG.info("overcloud processes status checks: "
                     f"process {process_dict['name']} is  "
                     "in running state")

            ovn_proc_filtered_df = self.oc_procs_df.query(
                'PROCESS=="{}"'.format(process_dict['name']))

            if (process_dict['node_group'] not in
                    topology.list_openstack_node_groups()):
                LOG.debug(
                    f"{process_dict['node_group']} is not "
                    "a node group part of this Openstack cloud")
                return
            node_list = [node.name
                         for node in
                         topology.list_openstack_nodes(
                            group=process_dict['node_group'])]
            node_names_re = re.compile(r'|'.join(node_list))
            node_filter = (ovn_proc_filtered_df.overcloud_node.
                           str.match(node_names_re))
            # get the processes running on a specific type of nodes
            ovn_proc_filtered_per_node_df = \
                ovn_proc_filtered_df[node_filter]
            total_num_processes = len(ovn_proc_filtered_per_node_df)

            if type(process_dict['number']) == int:
                expected_num_processes = process_dict['number']
            elif process_dict['number'] == 'all':
                expected_num_processes = len(node_list)
            else:
                raise ValueError("Unexpected value:"
                                 f"{process_dict['number']}")

            if expected_num_processes != total_num_processes:
                raise OvercloudProcessesException(
                    "Unexpected number"
                    f" of processes {process_dict['name']} running on "
                    f"{process_dict['node_group']} nodes")
            # process successfully validated
            LOG.debug(f"{process_dict['name']} successfully validated on "
                      f"{process_dict['node_group']} nodes")

    @property
    def ovn_overcloud_processes_validations(self):
        """
        Checks that the oc_procs_df dataframe has OVN processes running on the
        expected overcloud node or nodes
        :return: Bool
        """
        if not neutron.has_ovn():
            LOG.info("Networking OVN not configured")
            return True

        for attempt in tobiko.retry(timeout=300., interval=1.):
            try:
                for process_dict in self.ovn_processes_to_check_per_node:
                    self._ovn_overcloud_process_validations(process_dict)
            except OvercloudProcessesException:
                if attempt.is_last:
                    LOG.error('Unexpected number of OVN overcloud processes')
                    raise
                LOG.info('Retrying OVN overcloud processes: %s',
                         attempt.details)
                self.oc_procs_df = overcloud.get_overcloud_nodes_dataframe(
                    get_overcloud_node_processes_table)

            # if all procs are running we can return true
            return True
