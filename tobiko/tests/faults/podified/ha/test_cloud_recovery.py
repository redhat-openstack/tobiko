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
from __future__ import absolute_import

import random

from oslo_log import log
import testtools

import tobiko
from tobiko import config
from tobiko.tests.faults.ha import test_cloud_recovery
from tobiko.tests.faults.podified.ha import cloud_disruptions
from tobiko.tests.faults.podified.ha import rotate_galera_root_password
from tobiko.openstack import tests
from tobiko.openstack import topology
from tobiko import podified
from tobiko.openstack import nova
from tobiko.podified import containers as podified_containers
from tobiko.shell import sh


CONF = config.CONF
LOG = log.getLogger(__name__)


def check_edpm_deployment_health():
    """Wait for all EDPM data plane deployments to become ready."""
    names = podified.list_dataplane_deployment_names()
    if not names:
        tobiko.fail(f'No {podified.OSP_DP_DEPLOYMENT} found in project '
                    f'{CONF.tobiko.podified.osp_project}')
    LOG.info('Waiting for EDPM data plane deployments to be ready: %r', names)
    for name in names:
        podified.wait_for_edpm_deployment_ready(name)


def check_podified_containers_health():
    """Check EDPM host containers (nova_compute and OVN) are running."""
    podified_containers.list_node_containers.cache_clear()
    podified_containers.assert_containers_running(
        podified.EDPM_COMPUTE_GROUP, ['nova_compute'])
    podified_containers.assert_ovn_containers_running()
    podified_containers.assert_equal_containers_state()


def _is_ovn_bgp_agent_running():
    groups = topology.get_openstack_topology().groups
    for group in (podified.EDPM_NETWORKER_GROUP, podified.EDPM_COMPUTE_GROUP):
        if group not in groups:
            continue
        if podified_containers.assert_containers_running(
                group, ['ovn_bgp_agent'], bool_check=True):
            return True
    return False


def check_vm_create():
    tests.test_server_creation()
    if _is_ovn_bgp_agent_running():
        try:
            node = topology.find_openstack_node(
                group=podified.EDPM_NETWORKER_GROUP)
        except topology.NoSuchOpenStackTopologyNodeGroup:
            node = topology.find_openstack_node(
                group=podified.EDPM_COMPUTE_GROUP)
        expose_tenant_networks = topology.get_config_setting(
            'bgp-agent.conf', node.ssh_client, 'expose_tenant_networks')
        if (expose_tenant_networks and
                expose_tenant_networks.lower() == 'true'):
            tests.test_server_creation_no_fip()


def podified_health_checks(passive_checks_only=False, **_kwargs):
    # Extra skip flags (e.g. skip_mac_table_size_test) are accepted for
    # compatibility with OvercloudHealthCheck but ignored here: the OVS
    # mac-table-size validation relies on TripleO config paths that do not
    # exist on EDPM nodes.
    podified.assert_ocp_pods_running()
    check_edpm_deployment_health()
    nova.check_nova_services_health()
    tests.test_alive_agents_are_consistent_along_time()
    if not passive_checks_only:
        # create a unique stack that will be cleaned up at the end of each test
        check_vm_create()
        nova.action_on_all_instances('active')
        nova.check_virsh_domains_running()
    check_podified_containers_health()
    tests.test_ovn_dbs_are_synchronized()
    test_cloud_recovery.octavia_health_checks()


class PodifiedCloudHealthCheck(test_cloud_recovery.OvercloudHealthCheck):

    @classmethod
    def set_version_dependent_skips(cls, params):
        # The parent implementation calls verify_osp_version('17.0'), which
        # reads /etc/rhosp-release from a node of the 'controller' group. On
        # podified that group holds OCP control plane nodes, where neither
        # that file nor the nova_conductor container nor nova-manage exist.
        # The three failed lookups are swallowed, but they are logged as
        # command failures and show up as spurious errors in the job logs.
        # The mac-table-size validation they gate is not applicable to EDPM
        # nodes anyway, so do not probe the version at all here.
        pass

    def setup_fixture(self):
        # run validations
        params = {name: True for name in self.skips}
        LOG.info(f"Start executing Podified health checks: {params}.")
        try:
            podified_health_checks(**params)
        except Exception:
            LOG.exception("Podified health checks failed.")
            raise
        LOG.info(
            f"Podified health checks successfully executed: {params}.")


@podified.skip_if_not_podified
class DisruptPodifiedNodesTest(testtools.TestCase):
    """ HA Tests: run health check -> disruptive action -> health check
    disruptive_action: a function that runs some
    disruptive scenario on a node"""

    def test_0vercloud_health_check(self):
        PodifiedCloudHealthCheck.run_before()

    def test_kill_all_galera_services(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.kill_all_galera_services()
        PodifiedCloudHealthCheck.run_after()

    def test_remove_all_grastate_galera(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.remove_all_grastate_galera()
        PodifiedCloudHealthCheck.run_after()

    def test_remove_one_grastate_galera(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.remove_one_grastate_galera()
        PodifiedCloudHealthCheck.run_after()

    def test_rabbitmq_rotation(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.rabbitmq_rotation()
        PodifiedCloudHealthCheck.run_after()

    def test_rabbitmq_kill_random_pod(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.kill_random_rabbitmq_pod_and_recover()
        PodifiedCloudHealthCheck.run_after()

    def test_galera_root_password_rotation(self):
        PodifiedCloudHealthCheck.run_before()
        rotate_galera_root_password.rotate_galera_root_password()
        PodifiedCloudHealthCheck.run_after()

    def test_hard_reboot_ocp_node(self):
        """Temporary test — remove once the VIP-based tests below are ready."""
        node = random.choice(cloud_disruptions.get_ocp_controller_nodes())
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.disrupt_ocp_nodes(
            nodes=[node], disrupt_method=sh.hard_reset_method)
        PodifiedCloudHealthCheck.run_after()

    @testtools.skip("VIP-based node selection not yet implemented")
    def test_hard_reboot_ocp_node_main_vip(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.hard_reboot_ocp_node_main_vip()
        PodifiedCloudHealthCheck.run_after()

    @testtools.skip("VIP-based node selection not yet implemented")
    def test_hard_reboot_ocp_nodes_non_main_vip(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.hard_reboot_ocp_nodes_non_main_vip()
        PodifiedCloudHealthCheck.run_after()

    @testtools.skip("VIP-based node selection not yet implemented")
    def test_soft_reboot_ocp_node_main_vip(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.soft_reboot_ocp_node_main_vip()
        PodifiedCloudHealthCheck.run_after()

    @testtools.skip("VIP-based node selection not yet implemented")
    def test_soft_reboot_ocp_nodes_non_main_vip(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.soft_reboot_ocp_nodes_non_main_vip()
        PodifiedCloudHealthCheck.run_after()

    @testtools.skip("VIP-based node selection not yet implemented")
    def test_crash_ocp_node_main_vip(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.crash_ocp_node_main_vip()
        PodifiedCloudHealthCheck.run_after()

    @testtools.skip("VIP-based node selection not yet implemented")
    def test_crash_ocp_nodes_non_main_vip(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.crash_ocp_nodes_non_main_vip()
        PodifiedCloudHealthCheck.run_after()

    @podified.skip_if_compact_ocp_cluster
    def test_hard_reboot_all_ocp_nodes(self):
        PodifiedCloudHealthCheck.run_before()
        cloud_disruptions.hard_reboot_all_ocp_nodes()
        PodifiedCloudHealthCheck.run_after()
