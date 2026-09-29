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

from tobiko.podified import galera as galera_utils
from tobiko.tests.faults.podified.ha import rotate_galera_root_password \
    as rotate
from tobiko.tests.unit import _case


def _galera(name, old_secret):
    return {
        'metadata': {'name': name},
        'status': {'rootDatabaseSecret': old_secret},
    }


class RotateGaleraRootPasswordTest(_case.TobikoUnitTest):
    """Regression tests for pinning the rotation to a single Galera CR.

    get_galera() picks a random cell (see select_galera_name()); every
    later lookup for that rotation must reuse the same cell name instead
    of re-randomizing, otherwise pod/secret lookups can target a
    different cell than the one that was actually rotated.
    """

    def setUp(self):
        super().setUp()
        self.galera_name = 'openstack-cell1'
        self.old_secret = 'openstack-cell1-mariadb-root-db-secret'
        self.account_name = 'openstack-cell1-mariadb-root'

        mock.patch.object(
            galera_utils, 'get_galera',
            return_value=_galera(self.galera_name, self.old_secret)).start()
        mock.patch.object(
            galera_utils, 'get_root_account_name',
            return_value=self.account_name).start()
        mock.patch.object(
            rotate.podified, 'secret_has_finalizer',
            return_value=True).start()
        mock.patch.object(rotate.podified, 'create_secret').start()

        self.mock_patch_account_secret = mock.patch.object(
            rotate, '_patch_account_secret').start()
        self.mock_get_galera_pod_name = mock.patch.object(
            galera_utils, 'get_galera_pod_name',
            return_value=f'{self.galera_name}-galera-0').start()
        mock.patch.object(
            galera_utils, 'get_mysql_root_auth_script_path',
            return_value='/var/lib/operator-scripts/mysql_root_auth.sh'
        ).start()

        self.mock_wait_for_convergence = mock.patch.object(
            rotate, '_wait_for_secret_convergence').start()
        mock.patch.object(rotate, '_validate_post_rotation').start()
        mock.patch.object(rotate, '_wait_for_finalizer_swap').start()

        self.addCleanup(mock.patch.stopall)

    def test_pins_pod_lookup_to_the_selected_cell(self):
        rotate.rotate_galera_root_password()

        self.mock_get_galera_pod_name.assert_called_once_with(
            self.galera_name)

    def test_pins_convergence_check_to_the_selected_cell(self):
        rotate.rotate_galera_root_password()

        convergence_args = self.mock_wait_for_convergence.call_args[0]
        self.assertEqual(self.galera_name, convergence_args[0])

    def test_reverts_secret_on_failure(self):
        self.mock_wait_for_convergence.side_effect = RuntimeError('boom')

        self.assertRaises(RuntimeError, rotate.rotate_galera_root_password)

        self.mock_patch_account_secret.assert_called_with(
            self.account_name, self.old_secret)


class WaitForSecretConvergenceTest(_case.TobikoUnitTest):
    # These tests exercise the private _wait_for_secret_convergence()
    # helper directly.
    # pylint: disable=protected-access

    def setUp(self):
        super().setUp()
        mock.patch.object(rotate, '_assert_auth_script_select_1').start()
        self.mock_get_galera_by_name = mock.patch.object(
            galera_utils, 'get_galera_by_name').start()
        self.mock_get_galera = mock.patch.object(
            galera_utils, 'get_galera').start()
        mock.patch.object(galera_utils, 'get_mariadb_account').start()
        self.addCleanup(mock.patch.stopall)

    def test_checks_the_pinned_cell_not_a_random_one(self):
        galera_name = 'openstack-cell1'
        new_secret = 'openstack-cell1-mariadb-root-rotation-abcd1234'
        self.mock_get_galera_by_name.return_value = {
            'status': {'rootDatabaseSecret': new_secret}}

        rotate._wait_for_secret_convergence(
            galera_name, 'openstack-cell1-mariadb-root', new_secret,
            'openstack-cell1-galera-0', '/path/to/mysql_root_auth.sh')

        self.mock_get_galera_by_name.assert_called_once_with(galera_name)
        self.mock_get_galera.assert_not_called()
