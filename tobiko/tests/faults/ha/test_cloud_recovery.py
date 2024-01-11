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
#    under the License.
from __future__ import absolute_import

import typing

import pytest
from oslo_log import log
import testtools

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import nova as nova_osp
from tobiko.openstack import octavia
from tobiko.openstack import topology
from tobiko.openstack import tests
from tobiko.tests.faults.ha import cloud_disruptions
from tobiko.tripleo import pacemaker
from tobiko.tripleo import processes
from tobiko.tripleo import containers
from tobiko.tripleo import nova
from tobiko.tripleo import overcloud
from tobiko.tripleo import undercloud


CONF = config.CONF
LOG = log.getLogger(__name__)
SKIP_MESSAGE_EXTLB = ('Tests requiring a main VIP should be skipped when an '
                      'external load balancer is used')
has_external_lb = CONF.tobiko.rhosp.has_external_load_balancer


def overcloud_health_checks(passive_checks_only=False,
                            skip_mac_table_size_test=False):
    # this method will be changed in future commit
    check_pacemaker_resources_health()
    check_overcloud_processes_health()
    nova.check_nova_services_health()
    tests.test_alive_agents_are_consistent_along_time()
    if not passive_checks_only:
        # create a uniq stack
        check_vm_create()
        nova.start_all_instances()
        nova.check_computes_vms_running_via_virsh()
    containers.list_node_containers.cache_clear()
    containers.assert_all_tripleo_containers_running()
    containers.assert_equal_containers_state()
    containers.run_container_config_validations()
    tests.test_ovn_dbs_validations()
    # skip_mac_table_size_test has to be removed when BZ1695122 is resolved
    # we need it for the moment because this validation should not be performed
    # after any overcloud node is rebooted
    if not skip_mac_table_size_test:
        tests.test_ovs_bridges_mac_table_size()

    octavia_health_checks()


# check vm create with ssh and ping checks
def check_vm_create():
    tests.test_server_creation()
    if overcloud.is_ovn_bgp_agent_running():
        try:
            node = topology.find_openstack_node(group='networker')
        except topology.NoSuchOpenStackTopologyNodeGroup:
            node = topology.find_openstack_node(group='controller')
        expose_tenant_networks = topology.get_config_setting(
            'bgp-agent.conf', node.ssh_client, 'expose_tenant_networks')
        if expose_tenant_networks and expose_tenant_networks.lower() == 'true':
            tests.test_server_creation_no_fip()


# check cluster failed statuses
def check_pacemaker_resources_health():
    return pacemaker.PacemakerResourcesStatus().all_healthy


def check_overcloud_processes_health():
    procs = processes.OvercloudProcessesStatus()
    return (procs.basic_overcloud_processes_running and
            procs.ovn_overcloud_processes_validations)


def octavia_health_checks():
    if keystone.is_service_missing(name='octavia'):
        LOG.debug('octavia service not available')
        return
    # check LBs and Amphorae are healthy
    LOG.debug("check all LBs are in healthy status")
    for lb in octavia.list_load_balancers():
        LOG.debug("checkin LBs:\n%s", lb)
        octavia.wait_for_status(lb['id'], interval=5., timeout=120.)
        octavia.wait_for_status(lb['id'],
                                status_key=octavia.OPERATING_STATUS,
                                status=octavia.ONLINE,
                                interval=5.,
                                timeout=120.)
    LOG.debug("All LBs are in healthy status")


class OvercloudHealthCheck(tobiko.SharedFixture):

    skips: typing.FrozenSet[str] = frozenset()

    @classmethod
    def run_before(cls, **params):
        cls.run(after=False, **params)

    @classmethod
    def run_after(cls, **params):
        cls.run(after=True, **params)

    @classmethod
    def run(cls, after: bool, **params):
        fixture = tobiko.get_fixture(cls)
        params.setdefault('passive_checks_only', False)
        # In version OSP17.0 and highier,
        # 'test_ovs_bridges_mac_table_size()' test can run.
        if topology.verify_osp_version('17.0', lower=True):
            params.setdefault('skip_mac_table_size_test', True)
        skips = frozenset(k for k, v in params.items() if v)
        if after or skips < fixture.skips:
            # Force re-check
            tobiko.cleanup_fixture(fixture)
        else:
            LOG.info("Will skip Overcloud health checks if already "
                     f"executed: {params}")
        fixture.skips = skips
        tobiko.setup_fixture(fixture)

    def setup_fixture(self):
        # run validations
        params = {name: True
                  for name in self.skips}
        LOG.info(f"Start executing Overcloud health checks: {params}.")
        overcloud_health_checks(**params)
        LOG.info(f"Overcloud health checks successfully executed: {params}.")

    def cleanup_fixture(self):
        self.skips = frozenset()


@undercloud.skip_if_missing_undercloud
class DisruptTripleoNodesTest(testtools.TestCase):
    """ HA Tests: run health check -> disruptive action -> health check
    disruptive_action: a function that runs some
    disruptive scenario on a overcloud"""
    vms_detailed_info = None
    undisrupt_network_at_teardown = False

    def tearDown(self):
        super(DisruptTripleoNodesTest, self).tearDown()

        # this loop is run after test_z999_reboot_controller_galera_main_vip
        for i, vm in enumerate(self.vms_detailed_info or []):
            if vm is None or vm.get('id') is None:
                # server_name pattern comes from multi_ip_test_stack.yaml
                server_name = "group_of_vms_%d" % i
                try:
                    server = nova_osp.find_server(unique=True,
                                                  name=server_name)
                except tobiko.ObjectNotFound:
                    LOG.debug(f"Server {server_name} not found. "
                              "Perhaps it was never created.")
                    continue
                vm_id = server.id
            else:
                vm_id = vm['id']
            try:
                nova_osp.delete_server(vm_id)
            except nova_osp.ServerNotFoundError:
                LOG.debug(f"Server {vm_id} not found. "
                          "Perhaps it was already deleted.")

        # this is run after test_network_disruptor_main_vip
        if self.undisrupt_network_at_teardown:
            self.undisrupt_network_at_teardown = False
            cloud_disruptions.network_undisrupt_controller_main_vip()

    def test_0vercloud_health_check(self):
        OvercloudHealthCheck.run_before(skip_mac_table_size_test=False)

    @nova.skip_background_vm_ping_checks_when_nondvr
    def test_z99_hard_reboot_controllers_recovery(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.reset_all_controller_nodes()
        OvercloudHealthCheck.run_after()

    @staticmethod
    def _any_amphora_lb():
        """ returns True if octavia is configured and any octavia amphora LB
        exists"""
        return (keystone.has_service(name='octavia') and
                any([lb['provider'] == octavia.AMPHORA_PROVIDER
                     for lb in octavia.list_load_balancers()]))

    @nova.skip_background_vm_ping_checks
    def test_soft_reboot_computes_recovery(self):
        OvercloudHealthCheck.run_before()

        sequentially = self._any_amphora_lb()
        cloud_disruptions.reset_all_compute_nodes(hard_reset=False,
                                                  sequentially=sequentially)
        # verify VM status is updated after reboot
        nova.wait_for_all_instances_status('SHUTOFF')
        # start all VM instance
        # otherwise sidecar containers will not run after computes reboot
        nova.start_all_instances()
        OvercloudHealthCheck.run_after(passive_checks_only=True)

    # TODO(eolivare): the following test is skipped due to rhbz#1890895
    # def test_hard_reboot_computes_recovery(self):
    #     OvercloudHealthCheck.run_before()
    #     cloud_disruptions.reset_all_compute_nodes(hard_reset=True)
    #     # verify VM status is updated after reboot
    #     nova.wait_for_all_instances_status('SHUTOFF')
    #     # start all VM instance
    #     # otherwise sidecar containers will not run after computes reboot
    #     nova.start_all_instances()
    #     OvercloudHealthCheck.run_after(passive_checks_only=True)

    @nova.skip_background_vm_ping_checks_when_nondvr
    @testtools.skipIf(has_external_lb, SKIP_MESSAGE_EXTLB)
    def test_z999_reboot_controller_galera_main_vip(self):
        # This test case may fail at times if RHBZ#2124877 is not resolved
        # but that bug is due to a race condition,
        # so it is not reproducible 100% times
        OvercloudHealthCheck.run_before(passive_checks_only=True)
        multi_ip_test_fixture, ports_before_stack_creation = \
            cloud_disruptions.reboot_controller_galera_main_vip()
        OvercloudHealthCheck.run_after(passive_checks_only=True)
        self.vms_detailed_info = cloud_disruptions.get_vms_detailed_info(
            multi_ip_test_fixture)
        LOG.debug('detailed info from the list of vms created: %r',
                  self.vms_detailed_info)
        cloud_disruptions.check_no_duplicate_ips(
            self.vms_detailed_info, ports_before_stack_creation)

    @nova.skip_background_vm_ping_checks_when_nondvr
    @testtools.skipIf(has_external_lb, SKIP_MESSAGE_EXTLB)
    def test_z99_reboot_controller_main_vip(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.reset_controller_main_vip()
        OvercloudHealthCheck.run_after()

    @nova.skip_background_vm_ping_checks_when_nondvr
    @testtools.skipIf(has_external_lb, SKIP_MESSAGE_EXTLB)
    def test_z99_reboot_controller_non_main_vip(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.reset_controllers_non_main_vip()
        OvercloudHealthCheck.run_after()

    @nova.skip_background_vm_ping_checks_when_nondvr
    @testtools.skipIf(has_external_lb, SKIP_MESSAGE_EXTLB)
    def test_z99_crash_controller_main_vip(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.crash_controller_main_vip()
        OvercloudHealthCheck.run_after()

    @nova.skip_background_vm_ping_checks_when_nondvr
    @overcloud.skip_unless_kexec_tools_installed
    @testtools.skipIf(has_external_lb, SKIP_MESSAGE_EXTLB)
    def test_z99_crash_controller_non_main_vip(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.crash_controllers_non_main_vip()
        OvercloudHealthCheck.run_after()

    @nova.skip_background_vm_ping_checks_when_nondvr
    @pacemaker.skip_if_fencing_not_deployed
    @testtools.skipIf(has_external_lb, SKIP_MESSAGE_EXTLB)
    def test_network_disruptor_main_vip(self):
        OvercloudHealthCheck.run_before()
        self.undisrupt_network_at_teardown = True
        cloud_disruptions.network_disrupt_controller_main_vip()
        OvercloudHealthCheck.run_after()

    # @pacemaker.skip_if_fencing_not_deployed
    # def test_network_disruptor_non_main_vip(self):
    #     OvercloudHealthCheck.run_before()
    #     cloud_disruptions.network_disrupt_controllers_non_main_vip()
    #     OvercloudHealthCheck.run_after()
    #     cloud_disruptions.network_undisrupt_controllers_non_main_vip()

    @neutron.skip_unless_is_ovn()
    @overcloud.skip_unless_ovn_using_ha
    def test_reset_ovndb_pcs_master_resource(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.reset_ovndb_pcs_master_resource()
        OvercloudHealthCheck.run_after()

    @neutron.skip_unless_is_ovn()
    @overcloud.skip_unless_ovn_using_ha
    def test_reset_ovndb_pcs_resource(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.reset_ovndb_pcs_resource()
        OvercloudHealthCheck.run_after()

    @neutron.skip_unless_is_ovn()
    @overcloud.skip_unless_ovn_using_ha
    def test_reset_ovndb_master_container(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.reset_ovndb_master_container()
        OvercloudHealthCheck.run_after()

    def test_kill_rabbitmq_service_one_controller(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.kill_rabbitmq_service()
        OvercloudHealthCheck.run_after()

    def test_kill_all_galera_services(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.kill_all_galera_services()
        OvercloudHealthCheck.run_after()

    def test_remove_all_grastate_galera(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.remove_all_grastate_galera()
        OvercloudHealthCheck.run_after()

    def test_remove_one_grastate_galera(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.remove_one_grastate_galera()
        OvercloudHealthCheck.run_after()

    def test_request_galera_sst(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.request_galera_sst()
        OvercloudHealthCheck.run_after()

    @nova.skip_background_vm_ping_checks_when_nondvr
    @pytest.mark.flaky(reruns=0)
    def test_controllers_shutdown(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.test_controllers_shutdown()
        OvercloudHealthCheck.run_after()

    @overcloud.skip_unless_ovn_bgp_agent
    def test_restart_ovn_bgp_agents(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.restart_service_on_all_nodes(
            topology.get_agent_service_name(neutron.OVN_BGP_AGENT))
        OvercloudHealthCheck.run_after()

    @overcloud.skip_unless_ovn_bgp_agent
    def test_restart_frr(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.restart_service_on_all_nodes(
            topology.get_agent_service_name(neutron.FRR))
        OvercloudHealthCheck.run_after()

    def test_restart_neutron(self):
        OvercloudHealthCheck.run_before()
        cloud_disruptions.restart_service_on_all_nodes(
            topology.get_agent_service_name(neutron.NEUTRON))
        OvercloudHealthCheck.run_after()

# [..]
# more tests to follow
# run health checks
# faults stop rabbitmq service on one controller
# run health checks again
