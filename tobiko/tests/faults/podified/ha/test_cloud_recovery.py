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

from oslo_log import log
import testtools

from tobiko.tests.faults.ha import test_cloud_recovery
from tobiko.tests.faults.podified.ha import cloud_disruptions
from tobiko.openstack import tests
from tobiko import podified
from tobiko.openstack import nova


LOG = log.getLogger(__name__)


def podified_health_checks():
    nova.check_nova_services_health()
    tests.test_alive_agents_are_consistent_along_time()
    # create a unique stack that will be cleaned up at the end of each test
    # TODO(eolivare) add tests.test_server_creation_no_fip() when BGP is
    # configured with expose_tenant_networks
    tests.test_server_creation()
    nova.action_on_all_instances('active')
    nova.check_virsh_domains_running()
    test_cloud_recovery.octavia_health_checks()


class PodifiedCloudHealthCheck(test_cloud_recovery.OvercloudHealthCheck):
    def setup_fixture(self):
        # run validations
        LOG.info("Start executing Podified health checks.")
        podified_health_checks()
        LOG.info("Podified health checks successfully executed.")


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
