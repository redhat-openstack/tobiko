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

from tobiko import podified
from tobiko.shell import sh
from tobiko.tests.faults.containers import container_ops


LOG = log.getLogger(__name__)


@podified.skip_if_podified
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


@podified.skip_if_not_podified
class PodifiedConfigurationFilesTest(testtools.TestCase):

    def check_edpm_config(self, node, container):
        """Verify the config directories are mounted into the container

        It compares the file names of every config directory bind mounted
        into the container with the file names of its mount source on the
        node.
        """
        mounts = container_ops.get_container_config_mounts(node, container)
        if not mounts:
            LOG.debug(f'No config directory is mounted into {container} '
                      f'container of {node.name} node')
            return True
        verified = True
        for host_dir, container_dir in mounts.items():
            host_files = container_ops.list_files_on_node(node, host_dir)
            container_files = container_ops.list_files_in_container(
                node, container, container_dir)
            if not container_files:
                LOG.error(f'{node.name}: {container_dir} of {container} '
                          f'container is empty ({host_dir} holds '
                          f'{host_files})')
                verified = False
            elif host_files != container_files:
                LOG.error(f'{node.name}: {container_dir} of {container} '
                          f'container holds {container_files} while '
                          f'{host_dir} holds {host_files}')
                verified = False
        return verified

    def test_neutron_edpm_config_files(self):
        for node in container_ops.get_edpm_nodes():
            containers = set(container_ops.get_node_neutron_containers(node) +
                             container_ops.get_node_ovn_containers(node))
            self.assertNotEqual(set(), containers,
                                f'No neutron/OVN containers found on '
                                f'{node.name} node')
            for container in containers:
                self.assertTrue(
                    self.check_edpm_config(node, container),
                    f'Invalid config directory of {container} container of '
                    f'{node.name} node')

    def check_pod_config(self, pod_name, container):
        """Verify the files copied by kolla match their source"""
        verified = True
        for source, dest in container_ops.get_pod_kolla_config_files(
                pod_name, container):
            source_md5 = container_ops.get_pod_file_md5(
                pod_name, container, source)
            if source_md5 is None:
                continue  # optional file that was not provided
            dest_md5 = container_ops.get_pod_file_md5(
                pod_name, container, dest)
            if source_md5 != dest_md5:
                LOG.error(f'{pod_name}: {dest} of {container} container '
                          f'differs from {source}')
                verified = False
        return verified

    def test_neutron_pod_config_files(self):
        pods = podified.get_pods(labels={'service': 'neutron'})
        self.assertNotEqual([], pods, 'No neutron pods found')
        for pod in pods:
            for container in pod.model.spec.containers:
                self.assertTrue(
                    self.check_pod_config(pod.name(), container.name),
                    f'Invalid config files of {container.name} container '
                    f'of {pod.name()} pod')
