# Copyright (c) 2019 Red Hat
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

import random

import testtools
from oslo_log import log

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack import openstackclient
from tobiko.openstack import stacks


LOG = log.getLogger(__name__)


class BaseCliTest(testtools.TestCase):

    def setUp(self):
        super(BaseCliTest, self).setUp()
        self.api = neutron.get_neutron_client()

    def api_network_delete(self, network):
        nets = self.api.list_networks()['networks']
        for net in nets:
            if net['name'] == network:
                self.api.delete_network(net['id'])
                break
            if net['id'] == network:
                self.api.delete_network(network)
                break

    def api_subnet_delete(self, subnet_name):
        subnets = self.api.list_subnets()['subnets']
        for subnet in subnets:
            if subnet['name'] == subnet_name:
                self.api.delete_subnet(subnet['id'])
                break
            if subnet['id'] == subnet_name:
                self.api.delete_subnet(subnet_name)
                break

    def api_port_delete(self, port_name):
        ports = self.api.list_ports()['ports']
        for port in ports:
            if port['name'] == port_name:
                self.api.delete_port(port['id'])
                break
            if port['id'] == port_name:
                self.api.delete_port(port_name)
                break

    def api_network_log_delete(self, log_name):
        logs = self.api.list_network_logs()['logs']
        for _log in logs:
            if _log['name'] == log_name:
                self.api.delete_network_log(_log['id'])
                break
            if _log['id'] == log_name:
                self.api.delete_network_log(_log['id'])
                break

    def api_random_port_create(self):
        net_name = self.random_name()
        port_name = self.random_name()
        network = self.api.create_network({'network': {'name': net_name}})
        self.addCleanup(self.api_network_delete, net_name)
        network_id = network['network']['id']
        self.api.create_port({'port': {'name': port_name,
                                       'network_id': network_id}})
        self.addCleanup(self.api_port_delete, port_name)
        return port_name

    def api_random_subnet_create(self):
        net_name = self.random_name()
        subnet_name = self.random_name()
        network = self.api.create_network({'network': {'name': net_name}})
        self.addCleanup(self.api_network_delete, net_name)
        network_id = network['network']['id']
        self.api.create_subnet({'subnet': {'name': subnet_name,
                                           'network_id': network_id,
                                           'ip_version': 4,
                                           'cidr': '123.123.123.0/24'}})
        return subnet_name

    def api_random_network_create(self):
        name = self.random_name()
        self.api.create_network({'network': {'name': name}})
        self.addCleanup(self.api_network_delete, name)
        return name

    def api_random_network_log_create(self, sec_group_id=None):
        name = self.random_name()
        api_args = {'log': {'name': name,
                    'resource_type': 'security_group'}}
        if sec_group_id:
            api_args['log']['resource_id'] = sec_group_id
        self.api.create_network_log(api_args)
        self.addCleanup(self.api_network_log_delete, name)
        return name

    def random_name(self, length=16):
        letters = 'abcdefghijklmnopqrstuvwxyz'
        random_string = ''.join(random.choice(letters) for i in range(length))
        return f'{self.__class__.__name__}-{random_string}'


@neutron.skip_if_missing_networking_extensions('logging')
class NeutronLogCliTest(BaseCliTest):

    LOGS_AMOUNT = 2

    sec_groups_stack = tobiko.required_fixture(
        stacks.SecurityGroupsFixture)

    def _get_icmp_sec_group_id(self):
        """Returns the uuid of a security group with ICMP allowed."""
        sec_group_obj = self.sec_groups_stack.icmp_security_group_id
        if hasattr(sec_group_obj, '__iter__'):
            return sec_group_obj
        return sec_group_obj[0]

    def test_network_loggable_resources_list(self):
        response = openstackclient.network_loggable_resources_list()
        supported_types = [item['Supported types'] for item in response]
        self.assertIn('security_group', supported_types,
                      "Security group logging isn't supported.")

    def test_network_log_create(self):
        log_name = self.random_name()
        test_sec_group_id = self._get_icmp_sec_group_id()
        response = openstackclient.network_log_create(
                log_name, **{'resource-type': 'security_group',
                             'resource': test_sec_group_id,
                             'event': 'ALL'})
        self.addCleanup(self.api_network_log_delete, log_name)
        err_msg = 'Creation of log for security group using CLI failed.'
        # pylint: disable=E1126
        self.assertEqual(response['Enabled'], True, err_msg)
        self.assertEqual(response['Type'], 'security_group', err_msg)
        self.assertEqual(response['Event'], 'ALL', err_msg)

    def test_network_log_show(self):
        test_sec_group_id = self._get_icmp_sec_group_id()
        log_name = self.api_random_network_log_create(test_sec_group_id)
        _log = openstackclient.network_log_show(log_name)
        err_msg = 'Details show of log for security group using CLI failed.'
        # pylint: disable=E1126
        self.assertEqual(_log['Name'], log_name, err_msg)

    def test_network_log_create_all(self):
        log_name = self.random_name()
        response = openstackclient.network_log_create(
                log_name, **{'resource-type': 'security_group',
                             'event': 'ALL'})
        self.addCleanup(self.api_network_log_delete, log_name)
        err_msg = 'Creation of log for security group using CLI failed.'
        # pylint: disable=E1126
        self.assertEqual(response['Enabled'], True, err_msg)
        self.assertEqual(response['Type'], 'security_group', err_msg)
        self.assertEqual(response['Event'], 'ALL', err_msg)

    def test_network_log_list(self):
        test_sec_group_id = self._get_icmp_sec_group_id()
        log_names = [self.api_random_network_log_create(test_sec_group_id)
                     for i in range(self.LOGS_AMOUNT)]
        for log_name in log_names:
            self.addCleanup(self.api_network_log_delete, log_name)
        logs = openstackclient.network_log_list()
        found_count = 0
        for _log in logs:
            if _log['Name'] in log_names:
                found_count += 1
        err_msg = (f'Listing {self.LOGS_AMOUNT} logs for security groups '
                   'using CLI failed.')
        # pylint: disable=E1126
        self.assertEqual(found_count, self.LOGS_AMOUNT, err_msg)

    def test_network_log_delete(self):
        test_sec_group_id = self._get_icmp_sec_group_id()
        log_names = [self.api_random_network_log_create(test_sec_group_id)
                     for i in range(self.LOGS_AMOUNT)]
        openstackclient.network_log_delete(log_names)
        logs = self.api.list_network_logs()['logs']
        err_msg = 'Deletion of logs for security group using CLI failed.'
        for log_name in log_names:
            for _log in logs:
                self.assertNotEqual(_log['name'], log_name, err_msg)


class NeutronNetworkCliTest(BaseCliTest):

    def test_network_creation(self):
        net_name = self.random_name()
        output = openstackclient.network_create(net_name)
        self.addCleanup(self.api_network_delete, net_name)
        self.assertEqual(output['name'], net_name)  # pylint: disable=E1126
        self.assertEqual(output['status'], 'ACTIVE')  # pylint: disable=E1126

    def test_network_deletion(self):
        net_name_1 = self.api_random_network_create()
        net_name_2 = self.api_random_network_create()
        openstackclient.network_delete([net_name_1, net_name_2])
        nets = self.api.list_networks()['networks']
        for net in nets:
            self.assertNotEqual(net['name'], net_name_1)
            self.assertNotEqual(net['name'], net_name_2)

    def test_network_list(self):
        net_name = self.api_random_network_create()
        nets = openstackclient.network_list()
        found = False
        for net in nets:
            if net['Name'] == net_name:
                found = True
                break
        self.assertTrue(found)

    def test_network_show(self):
        net_name = self.api_random_network_create()
        net = openstackclient.network_show(net_name)
        self.assertEqual(net['name'], net_name)  # pylint: disable=E1126


class NeutronSubnetCliTest(BaseCliTest):

    def test_subnet_creation(self):
        subnet_name = self.random_name()
        net_name = self.api_random_network_create()
        output = openstackclient.subnet_create(
                subnet_name, net_name, **{'subnet-range': '123.123.123.0/24'})
        self.assertEqual(output['name'], subnet_name)  # pylint: disable=E1126

    def test_subnet_deletion(self):
        subnet_name_1 = self.api_random_subnet_create()
        subnet_name_2 = self.api_random_subnet_create()
        openstackclient.subnet_delete([subnet_name_1, subnet_name_2])
        subnets = self.api.list_subnets()['subnets']
        for subnet in subnets:
            self.assertNotEqual(subnet['name'], subnet_name_1)
            self.assertNotEqual(subnet['name'], subnet_name_2)

    def test_subnet_list(self):
        subnet_name = self.api_random_subnet_create()
        subnets = openstackclient.subnet_list()
        found = False
        for subnet in subnets:
            if subnet['Name'] == subnet_name:
                found = True
                break
        self.assertTrue(found)

    def test_subnet_show(self):
        subnet_name = self.api_random_subnet_create()
        subnet = openstackclient.subnet_show(subnet_name)
        self.assertEqual(subnet['name'], subnet_name)  # pylint: disable=E1126


class NeutronPortCliTest(BaseCliTest):

    def test_port_creation(self):
        port_name = self.random_name()
        net_name = self.api_random_network_create()
        output = openstackclient.port_create(port_name, net_name)
        self.addCleanup(self.api_port_delete, port_name)
        self.assertEqual(output['name'], port_name)  # pylint: disable=E1126

    def test_port_deletion(self):
        port_name_1 = self.api_random_port_create()
        port_name_2 = self.api_random_port_create()
        openstackclient.port_delete([port_name_1, port_name_2])
        ports = self.api.list_ports()['ports']
        for port in ports:
            self.assertNotEqual(port['name'], port_name_1)
            self.assertNotEqual(port['name'], port_name_2)

    def test_port_list(self):
        port_name = self.api_random_port_create()
        ports = openstackclient.port_list()
        found = False
        for port in ports:
            if port['Name'] == port_name:
                found = True
                break
        self.assertTrue(found)

    def test_port_show(self):
        port_name = self.api_random_port_create()
        port = openstackclient.port_show(port_name)
        self.assertEqual(port['name'], port_name)  # pylint: disable=E1126
