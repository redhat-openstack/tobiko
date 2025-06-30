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

from oslo_log import log
import testtools

from tobiko.tests.faults.containers import container_ops


LOG = log.getLogger(__name__)


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
