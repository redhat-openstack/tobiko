# Copyright (c) 2022 Red Hat, Inc.
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

import functools
import os
import time

import testtools
from oslo_log import log
import pandas
import pytest

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack import topology
from tobiko import podified
from tobiko.podified import containers as podified_containers
from tobiko.rhosp import containers as rhosp_containers
from tobiko.shell import sh
from tobiko import tripleo
from tobiko.tripleo import containers as tripleo_containers


LOG = log.getLogger(__name__)


class BaseContainersHealtTest(testtools.TestCase):

    def _assert_containers_running(self, group, expected_containers):
        topology.get_openstack_topology().assert_containers_running(
            group=group, expected_containers=expected_containers)


@tripleo.skip_if_missing_overcloud
class TripleoContainersHealthTest(BaseContainersHealtTest):
    # TODO(eolivare): refactor this class, because it replicates some code from
    # tobiko/tripleo/containers.py and its tests may be duplicating what
    # test_0vercloud_health_check already covers when it calls
    # containers.assert_all_tripleo_containers_running()

    @functools.lru_cache()
    def list_node_containers(self, ssh_client):
        """returns a list of containers and their run state"""
        return tripleo_containers.get_container_runtime().\
            list_containers(ssh_client=ssh_client)

    def test_cinder_api(self):
        """check that all common tripleo containers are running"""
        self._assert_containers_running('controller', ['cinder_api'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_rsync(self):
        self._assert_containers_running('controller', ['swift_rsync'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_proxy(self):
        self._assert_containers_running('controller', ['swift_proxy'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_object_updater(self):
        self._assert_containers_running('controller', ['swift_object_updater'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_object_server(self):
        self._assert_containers_running('controller', ['swift_object_server'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_object_replicator(self):
        self._assert_containers_running('controller',
                                        ['swift_object_replicator'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_object_expirer(self):
        self._assert_containers_running('controller', ['swift_object_expirer'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_object_auditor(self):
        self._assert_containers_running('controller', ['swift_object_auditor'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_container_updater(self):
        self._assert_containers_running('controller',
                                        ['swift_container_updater'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_container_server(self):
        self._assert_containers_running('controller',
                                        ['swift_container_server'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_container_replicator(self):
        self._assert_containers_running('controller',
                                        ['swift_container_replicator'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_container_auditor(self):
        self._assert_containers_running('controller',
                                        ['swift_container_auditor'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_account_server(self):
        self._assert_containers_running('controller', ['swift_account_server'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_account_replicator(self):
        self._assert_containers_running('controller',
                                        ['swift_account_replicator'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_account_reaper(self):
        self._assert_containers_running('controller', ['swift_account_reaper'])

    @tripleo.skip_if_ceph_rgw()
    def test_swift_account_auditor(self):
        self._assert_containers_running('controller',
                                        ['swift_account_auditor'])

    def test_nova_vnc_proxy(self):
        self._assert_containers_running('controller', ['nova_vnc_proxy'])

    def test_nova_scheduler(self):
        self._assert_containers_running('controller', ['nova_scheduler'])

    def test_nova_metadata(self):
        self._assert_containers_running('controller', ['nova_metadata'])

    def test_nova_conductor(self):
        self._assert_containers_running('controller', ['nova_conductor'])

    def test_nova_api_cron(self):
        self._assert_containers_running('controller', ['nova_api_cron'])

    def test_nova_api(self):
        self._assert_containers_running('controller', ['nova_api'])

    def test_neutron_api(self):
        self._assert_containers_running('controller', ['neutron_api'])

    def test_memcached(self):
        self._assert_containers_running('controller', ['memcached'])

    def test_controller_logrotate_crond(self):
        self._assert_containers_running('controller', ['logrotate_crond'])

    def test_keystone(self):
        self._assert_containers_running('controller', ['keystone'])

    def test_controller_iscsid(self):
        self._assert_containers_running('controller', ['iscsid'])

    def test_horizon(self):
        self._assert_containers_running('controller', ['horizon'])

    def test_heat_engine(self):
        self._assert_containers_running('controller', ['heat_engine'])

    def test_heat_api_cron(self):
        self._assert_containers_running('controller', ['heat_api_cron'])

    def test_heat_api_cfn(self):
        self._assert_containers_running('controller', ['heat_api_cfn'])

    def test_heat_api(self):
        self._assert_containers_running('controller', ['heat_api'])

    def test_glance_api(self):
        self._assert_containers_running('controller', ['glance_api'])

    def test_cinder_scheduler(self):
        self._assert_containers_running('controller', ['cinder_scheduler'])

    def test_cinder_api_cron(self):
        self._assert_containers_running('controller', ['cinder_api_cron'])

    def test_compute_iscsid(self):
        self._assert_containers_running('compute', ['iscsid'])

    def test_compute_logrotate_crond(self):
        self._assert_containers_running('compute', ['logrotate_crond'])

    def test_nova_compute(self):
        self._assert_containers_running('compute', ['nova_compute'])

    def test_nova_libvirt(self):
        nova_libvirt = tripleo_containers.get_libvirt_container_name()
        self._assert_containers_running('compute', [nova_libvirt])

    def test_nova_migration_target(self):
        self._assert_containers_running('compute', ['nova_migration_target'])

    def test_nova_virtlogd(self):
        self._assert_containers_running('compute', ['nova_virtlogd'])

    def test_ovn_containers_running(self):
        tripleo_containers.assert_ovn_containers_running()

    @pytest.mark.skip_during_ovn_migration
    def test_equal_containers_state(self, expected_containers_list=None,
                                    timeout=120, interval=5,
                                    recreate_expected=False):
        """compare all overcloud container states with using two lists:
        one is current , the other some past list
        first time this method runs it creates a file holding overcloud
        containers' states: ~/expected_containers_list_df.csv'
        second time it creates a current containers states list and
        compares them, they must be identical"""

        expected_containers_list_df = []
        # if we have a file or an explicit variable use that ,
        # otherwise  create and return
        if recreate_expected or (not (expected_containers_list or
                                      os.path.exists(
                                          rhosp_containers.
                                          expected_containers_file))):
            tripleo_containers.save_containers_state_to_file(
                tripleo_containers.list_containers())
            return
        elif expected_containers_list:
            expected_containers_list_df = pandas.DataFrame(
                tripleo_containers.get_container_states_list(
                    expected_containers_list),
                columns=['container_host', 'container_name',
                         'container_state'])
        elif os.path.exists(rhosp_containers.expected_containers_file):
            expected_containers_list_df = pandas.read_csv(
                rhosp_containers.expected_containers_file)
        failures = []
        error_info = 'Output explanation: left_only is the original state, ' \
                     'right_only is the new state'
        for _ in tobiko.retry(timeout=timeout):
            failures = []
            actual_containers_list_df = tripleo_containers.list_containers_df()
            LOG.info('expected_containers_list_df: {} '.format(
                expected_containers_list_df.to_string(index=False)))
            LOG.info('actual_containers_list_df: {} '.format(
                actual_containers_list_df.to_string(index=False)))
            # execute a `dataframe` diff between the expected
            # and actual containers
            expected_containers_state_changed = \
                rhosp_containers.dataframe_difference(
                    expected_containers_list_df, actual_containers_list_df)
            # check for changed state containerstopology
            if not expected_containers_state_changed.empty:
                failures.append('expected containers changed state ! : '
                                '\n\n{}\n{}'.format(
                                 expected_containers_state_changed.
                                 to_string(index=False), error_info))
                LOG.info('container states mismatched:\n{}\n'.format(failures))
                time.sleep(interval)
                # clear cache to obtain new data
                tripleo_containers.list_node_containers.cache_clear()
            else:
                LOG.info("assert_equal_containers_state :"
                         " OK, all containers are on the same state")
                return
        if failures:
            tobiko.fail('container states mismatched:\n{!s}', '\n'.join(
                failures))

    def config_validation(self, config_checkings):
        container_runtime_name = tripleo_containers.\
                                 get_container_runtime_name()
        for node in topology.list_openstack_nodes(
                group=config_checkings['node_group']):
            for param_check in config_checkings['param_validations']:
                obtained_param = sh.execute(
                    f"{container_runtime_name} exec -uroot "
                    f"{config_checkings['container_name']} crudini "
                    f"--get {config_checkings['config_file']} "
                    f"{param_check['section']} {param_check['param']}",
                    ssh_client=node.ssh_client, sudo=True).stdout.strip()
                self.assertTrue(param_check['expected_value'] in
                                obtained_param,
                                f"Expected {param_check['param']} value: "
                                f"{param_check['expected_value']}\n"
                                f"Obtained {param_check['param']} value: "
                                f"{obtained_param}")
        LOG.info("Configuration verified:\n"
                 f"node group: {config_checkings['node_group']}\n"
                 f"container: {config_checkings['container_name']}\n"
                 f"config file: {config_checkings['config_file']}")

    @neutron.skip_unless_is_ovn()
    def test_ovn_container_config(self):
        """check containers configuration in ovn
        """
        ovn_config_checkings = \
            {'node_group': 'controller',
             'container_name': 'neutron_api',
             'config_file': '/etc/neutron/plugins/ml2/ml2_conf.ini',
             'param_validations': [{'section': 'ml2',
                                    'param': 'mechanism_drivers',
                                    'expected_value': 'ovn'},
                                   {'section': 'ml2',
                                    'param': 'type_drivers',
                                    'expected_value': 'geneve'},
                                   {'section': 'ovn',
                                    'param': 'ovn_metadata_enabled',
                                    'expected_value': 'True'}]}
        self.config_validation(ovn_config_checkings)

    @neutron.skip_unless_is_ovs()
    def test_ovs_container_config(self):
        """check containers configuration in ovn
        """
        ovs_config_checkings = \
            {'node_group': 'controller',
             'container_name': 'neutron_api',
             'config_file': '/etc/neutron/plugins/ml2/ml2_conf.ini',
             'param_validations': [{'section': 'ml2',
                                    'param': 'mechanism_drivers',
                                    'expected_value': 'openvswitch'}]}
        self.config_validation(ovs_config_checkings)


@podified.skip_if_not_podified
class PodifiedContainersHealthTest(BaseContainersHealtTest):

    @functools.lru_cache()
    def list_node_containers(self, ssh_client):
        """returns a list of containers and their run state"""
        return podified_containers.get_container_runtime().\
            list_containers(ssh_client=ssh_client)

    def test_compute_iscsid(self):
        self._assert_containers_running(podified.EDPM_COMPUTE_GROUP,
                                        ['iscsid'])

    def test_compute_logrotate_crond(self):
        self._assert_containers_running(podified.EDPM_COMPUTE_GROUP,
                                        ['logrotate_crond'])

    def test_nova_compute(self):
        self._assert_containers_running(podified.EDPM_COMPUTE_GROUP,
                                        ['nova_compute'])

    def test_ovn_containers_running(self):
        podified_containers.assert_ovn_containers_running()

    def test_equal_containers_state(self, expected_containers_list=None,
                                    timeout=120, interval=5,
                                    recreate_expected=False):
        """compare all overcloud container states with using two lists:
        one is current , the other some past list
        first time this method runs it creates a file holding overcloud
        containers' states: ~/expected_containers_list_df.csv'
        second time it creates a current containers states list and
        compares them, they must be identical"""

        expected_containers_list_df = []
        # if we have a file or an explicit variable use that ,
        # otherwise  create and return
        if recreate_expected or (not (expected_containers_list or
                                      os.path.exists(
                                          rhosp_containers.
                                          expected_containers_file))):
            podified_containers.save_containers_state_to_file(
                podified_containers.list_containers())
            return
        elif expected_containers_list:
            expected_containers_list_df = pandas.DataFrame(
                podified_containers.get_container_states_list(
                    expected_containers_list),
                columns=['container_host', 'container_name',
                         'container_state'])
        elif os.path.exists(rhosp_containers.expected_containers_file):
            expected_containers_list_df = pandas.read_csv(
                rhosp_containers.expected_containers_file)
        failures = []
        error_info = 'Output explanation: left_only is the original state, ' \
                     'right_only is the new state'
        for _ in tobiko.retry(timeout=timeout):
            failures = []
            actual_containers_list_df = \
                podified_containers.list_containers_df()
            LOG.info('expected_containers_list_df: {} '.format(
                expected_containers_list_df.to_string(index=False)))
            LOG.info('actual_containers_list_df: {} '.format(
                actual_containers_list_df.to_string(index=False)))
            # execute a `dataframe` diff between the expected
            # and actual containers
            expected_containers_state_changed = \
                rhosp_containers.dataframe_difference(
                    expected_containers_list_df, actual_containers_list_df)
            # check for changed state containerstopology
            if not expected_containers_state_changed.empty:
                failures.append('expected containers changed state ! : '
                                '\n\n{}\n{}'.format(
                                 expected_containers_state_changed.
                                 to_string(index=False), error_info))
                LOG.info('container states mismatched:\n{}\n'.format(failures))
                time.sleep(interval)
                # clear cache to obtain new data
                podified_containers.list_node_containers.cache_clear()
            else:
                LOG.info("assert_equal_containers_state :"
                         " OK, all containers are on the same state")
                return
        if failures:
            tobiko.fail('container states mismatched:\n{!s}', '\n'.join(
                failures))
