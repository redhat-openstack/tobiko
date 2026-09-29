# Copyright 2026 Red Hat
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

from unittest import mock

import tobiko
from tobiko.podified import galera
from tobiko.tests import unit


def _galera(name='openstack', status=None):
    return {
        'metadata': {'name': name},
        'status': status or {},
    }


def _galera_object(name):
    galera_object = mock.Mock()
    galera_object.as_dict.return_value = _galera(name=name)
    return galera_object


class ListGaleraNamesTest(unit.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        mock.patch.object(galera.podified, 'project_context').start()
        self.mock_selector = mock.patch.object(galera.oc, 'selector').start()
        self.addCleanup(mock.patch.stopall)

    def test_returns_sorted_names(self):
        self.mock_selector.return_value.objects.return_value = [
            _galera_object('openstack-cell1'), _galera_object('openstack')]
        self.assertEqual(
            ['openstack', 'openstack-cell1'], galera.list_galera_names())

    def test_fails_when_no_galeras_found(self):
        self.mock_selector.return_value.objects.return_value = []
        self.assertRaises(tobiko.FailureException, galera.list_galera_names)


class SelectGaleraNameTest(unit.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        mock.patch.object(galera.podified, 'project_context').start()
        self.mock_selector = mock.patch.object(galera.oc, 'selector').start()
        self.addCleanup(mock.patch.stopall)

    def test_returns_a_random_galera_name(self):
        self.mock_selector.return_value.objects.return_value = [
            _galera_object('openstack-cell1'), _galera_object('openstack')]
        with mock.patch.object(galera.random, 'choice') as mock_choice:
            mock_choice.return_value = 'openstack-cell1'
            self.assertEqual(
                'openstack-cell1', galera.select_galera_name())
        mock_choice.assert_called_once_with(['openstack', 'openstack-cell1'])


class GetGaleraServiceNameTest(unit.TobikoUnitTest):

    def test_default_cell(self):
        self.assertEqual(
            'openstack-galera', galera.get_galera_service_name('openstack'))

    def test_non_default_cell(self):
        self.assertEqual(
            'openstack-cell1-galera',
            galera.get_galera_service_name('openstack-cell1'))


class GetGaleraPodNameTest(unit.TobikoUnitTest):

    def setUp(self):
        super().setUp()
        self.mock_get_pods = mock.patch.object(
            galera.podified, 'get_pods').start()
        self.addCleanup(mock.patch.stopall)

    def _pod(self, name):
        pod = mock.Mock()
        pod.name.return_value = name
        return pod

    def test_selects_pods_for_the_given_cell_only(self):
        self.mock_get_pods.return_value = [
            self._pod('openstack-cell1-galera-1'),
            self._pod('openstack-cell1-galera-0'),
        ]
        self.assertEqual(
            'openstack-cell1-galera-0',
            galera.get_galera_pod_name('openstack-cell1'))
        self.mock_get_pods.assert_called_once_with(
            labels={'service': 'openstack-cell1-galera'})

    def test_skips_when_no_pods_found_for_the_cell(self):
        self.mock_get_pods.return_value = []
        self.assertRaises(
            tobiko.SkipException,
            galera.get_galera_pod_name, 'openstack-cell1')


class GetRootAccountNameTest(unit.TobikoUnitTest):

    def test_returns_status_root_database_account(self):
        # status.rootDatabaseAccount reflects the actual account name
        # regardless of whether it was auto-generated or set via
        # spec.rootDatabaseAccount (see OSPRH-27668).
        account_name = galera.get_root_account_name(
            _galera(status={'rootDatabaseAccount': 'openstack-mariadb-root'}))
        self.assertEqual('openstack-mariadb-root', account_name)

    def test_fails_when_status_root_database_account_missing(self):
        self.assertRaises(
            tobiko.FailureException,
            galera.get_root_account_name, _galera())

    def test_fails_when_status_root_database_account_empty(self):
        self.assertRaises(
            tobiko.FailureException,
            galera.get_root_account_name,
            _galera(status={'rootDatabaseAccount': ''}))
