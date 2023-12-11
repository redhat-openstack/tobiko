# Copyright 2019 Red Hat
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

import os
import unittest

import netaddr
import pandas as pd
import testtools

from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import metalsmith
from tobiko import tripleo
from tobiko.tripleo import pacemaker
from tobiko.tripleo import services
from tobiko.tripleo import processes
import tobiko

CONF = config.CONF


@tripleo.skip_if_missing_undercloud
class OvercloudKeystoneCredentialsTest(testtools.TestCase):

    def test_fetch_overcloud_credentials(self):
        env = tripleo.load_overcloud_rcfile()
        self.assertTrue(env['OS_AUTH_URL'])
        self.assertTrue(env.get('OS_USERNAME') or env.get('OS_USER_ID'))
        self.assertTrue(env['OS_PASSWORD'])
        self.assertTrue(env.get('OS_TENANT_NAME') or
                        env.get('OS_PROJECT_NAME') or
                        env.get('OS_TENANT_ID') or
                        env.get('OS_PROJECT_ID'))

    def test_overcloud_keystone_credentials(self):
        fixture = tripleo.overcloud_keystone_credentials()
        self.assertIsInstance(fixture,
                              keystone.KeystoneCredentialsFixture)
        credentials = keystone.keystone_credentials(fixture)
        credentials.validate()

    def test_overcloud_keystone_session(self):
        session = tripleo.overcloud_keystone_session()
        client = keystone.get_keystone_client(session=session)
        endpoints = keystone.list_endpoints(client=client)
        self.assertNotEqual([], endpoints)

    def test_overcloud_keystone_client(self):
        client = tripleo.overcloud_keystone_client()
        _services = keystone.list_services(client=client)
        self.assertTrue(_services)


@tripleo.skip_if_missing_overcloud
class OvercloudMetalsmithApiTest(testtools.TestCase):

    def test_list_overcloud_nodes(self):
        nodes = tripleo.list_overcloud_nodes()
        self.assertTrue(nodes)
        for node in nodes:
            node_ip = metalsmith.find_instance_ip_address(
                instance=node, check_connectivity=True)
            self.assertIsInstance(node_ip, netaddr.IPAddress)

    def test_find_overcloud_nodes(self):
        node = tripleo.find_overcloud_node()
        node_ip = metalsmith.find_instance_ip_address(instance=node,
                                                      check_connectivity=True)
        self.assertIsInstance(node_ip, netaddr.IPAddress)

    def test_get_overcloud_node_ip_address(self):
        overcloud_node_ip = tripleo.overcloud_node_ip_address()
        self.assertIsInstance(overcloud_node_ip, netaddr.IPAddress)

    def test_overcloud_host_config(self):
        instance = tripleo.find_overcloud_node()
        host_config = tobiko.setup_fixture(
            tripleo.overcloud_host_config(instance=instance))
        instance_ips = set()
        for ips in instance.ip_addresses().values():
            instance_ips.update(ips)
        self.assertIn(host_config.host, instance_ips)
        self.assertIsInstance(host_config.hostname, str)
        netaddr.IPAddress(host_config.hostname)
        self.assertEqual(CONF.tobiko.rhosp.ssh_port,
                         host_config.port)
        self.assertEqual(tripleo.get_overcloud_ssh_username(),
                         host_config.username)
        key_filename = tobiko.tobiko_config_path(
            CONF.tobiko.rhosp.ssh_key_filename)
        self.assertEqual(key_filename, host_config.key_filename)
        self.assertTrue(os.path.isfile(key_filename))
        self.assertTrue(os.path.isfile(key_filename + '.pub'))

    def test_overcloud_ssh_client_connection(self):
        instance = tripleo.find_overcloud_node()
        ssh_client = tripleo.overcloud_ssh_client(instance=instance)
        ssh_client.connect()


@tripleo.skip_if_missing_overcloud
class OvercloudPacemakerTest(testtools.TestCase):
    """
    Assert that all pacemaker resources are in
    healthy state
    """

    def test_get_pacemaker_resource_table(self):
        resource_table = pacemaker.get_pcs_resources_table()
        self.assertIsInstance(resource_table, pd.DataFrame)

    def test_pacemaker_resources_health(self):
        pcs_health = pacemaker.PacemakerResourcesStatus()
        self.assertTrue(pcs_health.all_healthy)


@tripleo.skip_if_missing_overcloud
class OvercloudServicesTest(testtools.TestCase):
    """
    Assert that a subset of overcloud services are in running state
    across the overcloud nodes
    """

    services_status = tobiko.required_fixture(
        services.OvercloudServicesStatus)

    def test_get_services_resource_table(self):
        self.assertIsInstance(self.services_status.oc_services_df,
                              pd.DataFrame)

    def test_overcloud_services(self):
        self.assertTrue(self.services_status.basic_overcloud_services_running)

    def test_get_overcloud_nodes_running_pcs_resource(self):
        nodes_list = pacemaker.get_overcloud_nodes_running_pcs_resource(
            resource_type='(ocf::heartbeat:rabbitmq-cluster):',
            resource_state='Started')
        self.assertIsInstance(nodes_list, list)


@tripleo.skip_if_missing_overcloud
class OvercloudProcessesTest(testtools.TestCase):
    """
    Assert that a subset of overcloud processes are in running state
    across the overcloud nodes
    """

    def test_get_processes_resource_table(self):
        ops = processes.OvercloudProcessesStatus()
        self.assertIsInstance(ops.oc_procs_df,
                              pd.DataFrame)

    def test_overcloud_processes(self):
        ops = processes.OvercloudProcessesStatus()
        self.assertTrue(ops.basic_overcloud_processes_running)


@tripleo.skip_if_missing_undercloud
class OvercloudVersionTest(unittest.TestCase):
    # TODO(eolivare): move the properties to a common class, since they are
    # duplicate in OvercloudVersionTest and UndercloudVersionTest

    @property
    def lower_version(self) -> str:
        v = tripleo.overcloud_version()
        if v.micro > 0:
            lower_v = f"{v.major}.{v.minor}.{v.micro - 1}"
        elif v.minor > 0:
            lower_v = f"{v.major}.{v.minor -1}.{v.micro}"
        elif v.major > 0:
            lower_v = f"{v.major -1}.{v.minor}.{v.micro}"
        else:
            raise ValueError(f"wrong version: {v}")
        return lower_v

    @property
    def same_version(self) -> str:
        v = tripleo.overcloud_version()
        return f"{v.major}.{v.minor}.{v.micro}"

    @property
    def higher_version(self) -> str:
        v = tripleo.overcloud_version()
        return f"{v.major}.{v.minor}.{v.micro + 1}"

    def test_overcloud_version(self):
        version = tripleo.overcloud_version()
        self.assertTrue(tobiko.match_version(version, min_version='13'))

    def test_has_overcloud(self):
        self.assertTrue(tripleo.has_overcloud())

    def test_has_overcloud_with_min_version(self):
        self.assertTrue(
            tripleo.has_overcloud(min_version=self.same_version))

    def test_has_overcloud_with_min_version_lower(self):
        self.assertTrue(
            tripleo.has_overcloud(min_version=self.lower_version))

    def test_has_overcloud_with_min_version_higher(self):
        self.assertFalse(
            tripleo.has_overcloud(min_version=self.higher_version))

    def test_has_overcloud_with_max_version(self):
        self.assertFalse(
            tripleo.has_overcloud(max_version=self.same_version))

    def test_has_overcloud_with_max_version_lower(self):
        self.assertFalse(
            tripleo.has_overcloud(max_version=self.lower_version))

    def test_has_overcloud_with_max_version_higher(self):
        self.assertTrue(
            tripleo.has_overcloud(max_version=self.higher_version))

    def test_skip_unless_has_overcloud(self):
        self._assert_test_skip_unless_has_overcloud_dont_skip()

    def test_skip_unless_has_overcloud_with_min_version(self):
        self._assert_test_skip_unless_has_overcloud_dont_skip(
            min_version=self.same_version)

    def test_skip_unless_has_overcloud_with_min_version_lower(self):
        self._assert_test_skip_unless_has_overcloud_dont_skip(
            min_version=self.lower_version)

    def test_skip_unless_has_overcloud_with_min_version_higher(self):
        self._assert_test_skip_unless_has_overcloud_skip(
            min_version=self.higher_version)

    def test_skip_unless_has_overcloud_with_max_version(self):
        self._assert_test_skip_unless_has_overcloud_skip(
            max_version=self.same_version)

    def test_skip_unless_has_overcloud_with_max_version_lower(self):
        self._assert_test_skip_unless_has_overcloud_skip(
            max_version=self.lower_version)

    def test_skip_unless_has_overcloud_with_max_version_higher(self):
        self._assert_test_skip_unless_has_overcloud_dont_skip(
            max_version=self.higher_version)

    def _assert_test_skip_unless_has_overcloud_dont_skip(
            self,
            min_version: tobiko.VersionType = None,
            max_version: tobiko.VersionType = None):
        executed = []

        @tripleo.skip_unless_has_overcloud(min_version=min_version,
                                           max_version=max_version)
        def decorated_function():
            executed.append(True)

        self.assertFalse(executed)
        decorated_function()
        self.assertTrue(executed)

    def _assert_test_skip_unless_has_overcloud_skip(
            self,
            min_version: tobiko.VersionType = None,
            max_version: tobiko.VersionType = None):
        @tripleo.skip_unless_has_overcloud(min_version=min_version,
                                           max_version=max_version)
        def decorated_function():
            raise self.fail('Not skipped')

        with self.assertRaises(unittest.SkipTest):
            decorated_function()
