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

import uuid

from oslo_log import log
import testtools

import tobiko
from tobiko import podified
from tobiko.tests.faults.containers import container_ops


LOG = log.getLogger(__name__)


@podified.skip_if_podified
@container_ops.skip_unless_has_podman
class LogFilesTest(testtools.TestCase):

    def test_neutron_logs_exist(self):
        groups = ['controller', 'compute', 'networker']
        neutron_nodes = container_ops.get_nodes_for_groups(groups)
        for node in neutron_nodes:
            # set is used to remove duplicated containers
            containers = set(container_ops.get_node_neutron_containers(node) +
                             container_ops.get_node_ovn_containers(node))
            for container in containers:
                logfiles = (container_ops.
                            get_container_logfiles(node, container))
                if not logfiles:
                    LOG.warning(f'No logfiles have been found in {container} '
                                f'container of {node.name} node')
                    continue
                # logdir is obtained differently for pcs resources
                pcs_logdir = (container_ops.
                              get_node_logdir_from_pcs(node, container))

                for logfile in logfiles:
                    log_msg = container_ops.log_random_msg(node,
                                                           container,
                                                           logfile)
                    if pcs_logdir:
                        node_logfile = (pcs_logdir +
                                        f'/{logfile.split("/")[-1]}')
                    else:
                        node_logfile = '/var/log/containers/'\
                                       f'{logfile.split("/")[-2]}/'\
                                       f'{logfile.split("/")[-1]}'
                    self.assertTrue(container_ops.find_msg_in_file(
                        node, node_logfile, log_msg))

    def test_neutron_logs_rotate(self):
        groups = ['controller', 'compute', 'networker']
        neutron_nodes = container_ops.get_nodes_for_groups(groups)
        msg = ''
        for node in neutron_nodes:
            node_logfiles = []
            # set is used to remove duplicated containers
            containers = set(container_ops.get_node_neutron_containers(node) +
                             container_ops.get_node_ovn_containers(node))
            pcs_logdir_dict = {}
            for container in containers:
                cont_logfiles = (container_ops.
                                 get_container_logfiles(node, container))
                if not cont_logfiles:
                    LOG.warning(f'No logfiles have been found in {container} '
                                f'container of {node.name} node')
                    continue
                node_logfiles += cont_logfiles
                # logdir is obtained differently for pcs resources
                pcs_logdir = (container_ops.
                              get_node_logdir_from_pcs(node, container))

                for logfile in cont_logfiles:
                    pcs_logdir_dict[logfile] = pcs_logdir
                    if not msg:
                        msg = container_ops.log_random_msg(node,
                                                           container,
                                                           logfile)
                    else:
                        container_ops.log_msg(node, container, logfile, msg)
            container_ops.rotate_logs(node)
            for logfile in set(node_logfiles):
                if pcs_logdir_dict.get(logfile):
                    node_logfile = (pcs_logdir_dict[logfile] +
                                    f'/{logfile.split("/")[-1]}')
                else:
                    node_logfile = '/var/log/containers/'\
                                   f'{logfile.split("/")[-2]}/'\
                                   f'{logfile.split("/")[-1]}'
                self.assertTrue(container_ops.find_msg_in_file(node,
                                                               node_logfile,
                                                               msg,
                                                               rotated=True))


@podified.skip_if_not_podified
class PodifiedLogFilesTest(testtools.TestCase):

    def check_edpm_logs(self, node, container):
        """Verify the output of a container reaches the journal"""
        marker = f'tobiko-{uuid.uuid4().hex}'
        container_ops.print_to_container_stdout(node, container, marker)
        for attempt in tobiko.retry(timeout=30., interval=2.):
            logs = '\n'.join(container_ops.get_journal_log_lines(
                node, container, since='1m'))
            if marker in logs:
                break
            if attempt.is_last:
                self.fail(f'Marker not found in the journal of {container} '
                          f'container of {node.name} node')

    def test_neutron_edpm_logs_exist(self):
        for node in container_ops.get_edpm_nodes():
            containers = set(container_ops.get_node_neutron_containers(node) +
                             container_ops.get_node_ovn_containers(node))
            self.assertNotEqual(set(), containers,
                                f'No neutron/OVN containers found on '
                                f'{node.name} node')
            for container in containers:
                self.check_edpm_logs(node, container)

    def check_pod_logs(self, pod):
        """Verify the output of every container of a pod reaches its logs"""
        markers = {}
        for container in pod.model.spec.containers:
            marker = f'tobiko-{uuid.uuid4().hex}'
            podified.execute_in_pod(
                pod.name(), f'echo {marker} > /proc/1/fd/1', container.name)
            markers[container.name] = marker
        for attempt in tobiko.retry(timeout=30., interval=2.):
            logs = '\n'.join(pod.logs(since='1m').values())
            missing = [c for c, m in markers.items() if m not in logs]
            if not missing:
                break
            if attempt.is_last:
                self.fail(f'Marker not found in the logs of {missing} '
                          f'container(s) of {pod.name()} pod')

    def test_neutron_pod_logs_exist(self):
        services = ('neutron', 'ovn-northd', 'ovsdbserver-nb',
                    'ovsdbserver-sb')
        for service in services:
            pods = podified.get_pods(labels={'service': service})
            self.assertNotEqual([], pods, f'No {service} pods found')
            for pod in pods:
                self.check_pod_logs(pod)
