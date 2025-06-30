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

from tobiko.shell import sh
from tobiko.tests.faults.containers import container_ops


LOG = log.getLogger(__name__)


@container_ops.skip_unless_has_podman
class ConfigurationFilesTest(testtools.TestCase):

    def check_config(self, node, containers, file_list, service):
        """Verify that files on the node are equal to the file in container

        It calculates MD5 sum of the configuration file in the changed
        directory if it exists there or in original directory otherwise.
        It also follows any links if necessary.
        """
        original_dir = f'/var/lib/config-data/{service}'
        changed_dir = f'/var/lib/config-data/puppet-generated/{service}'
        verified = True
        skip_container_list = ['ovn-dbs-bundle']
        for fname in file_list:
            flink = sh.execute(
                    f'sudo readlink {changed_dir}{fname} || '
                    f'sudo readlink {original_dir}{fname}',
                    ssh_client=node.ssh_client,
                    expect_exit_status=None).stdout.strip() or fname
            md5_output = sh.execute(
                    f'sudo md5sum {changed_dir}{flink} || '
                    f'sudo md5sum {changed_dir}{fname} || '
                    f'sudo md5sum {original_dir}{flink} ||'
                    f'sudo md5sum {original_dir}{fname}',
                    ssh_client=node.ssh_client,
                    expect_exit_status=None).stdout.strip().split(' ')
            if md5_output:
                md5 = md5_output[0]
                LOG.debug(f'{md5_output[-1]} on {node.name} has {md5} MD5')
            else:
                md5 = ''
                verified = False
                LOG.error(f'{node.name}: {fname} does not exist in '
                          f'{original_dir} or {changed_dir}')
            for container in containers:
                skip_this_container = False
                for skip_container in skip_container_list:
                    if skip_container in container:
                        skip_this_container = True
                if skip_this_container:
                    continue
                result = sh.execute(
                        f"sudo podman exec -u root {container} md5sum "
                        f"{fname} | awk '{{print $1}}'",
                        ssh_client=node.ssh_client)
                container_md5 = result.stdout.strip()
                LOG.debug(f'{fname} in {container} container '
                          f'has {container_md5} md5 hash')
                if container_md5 != md5:
                    LOG.error(f'incorrect md5 for {fname}. '
                              f'{node.name}: {md5}, {container} container: '
                              f'{container_md5}')
                    verified = False
        return verified

    def test_neutron_config_files(self):
        groups = ['controller', 'compute', 'networker']
        neutron_nodes = container_ops.get_nodes_for_groups(groups)
        for node in neutron_nodes:
            containers_neutron = (container_ops.
                                  get_node_neutron_containers(node))
            config_neutron = container_ops.get_node_neutron_config_files(node)
            self.assertTrue(
                    self.check_config(node, containers_neutron,
                                      config_neutron, 'neutron'))
            containers_ovn = container_ops.get_node_ovn_containers(node)
            config_ovn = container_ops.get_node_ovn_config_files()
            self.assertTrue(
                    self.check_config(node, containers_ovn,
                                      config_ovn, 'ovn_controller'))
