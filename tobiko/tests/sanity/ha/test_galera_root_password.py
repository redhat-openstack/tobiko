# Copyright (c) 2026 Red Hat, Inc.
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

from oslo_log import log
import testtools

import tobiko
from tobiko import podified
from tobiko.podified import galera as galera_utils


LOG = log.getLogger(__name__)


@podified.skip_if_not_podified
class GaleraRootPasswordSanityTest(testtools.TestCase):

    def _get_galera(self):
        galera = galera_utils.get_galera()
        LOG.info("Using Galera CR: %s", galera['metadata']['name'])
        return galera

    def _assert_secret_login(self, secret_name):
        secret = podified.get_secret(secret_name)
        self.assertIsNotNone(secret, f"Secret {secret_name} missing")
        pod_name = galera_utils.get_galera_pod_name()
        LOG.debug("Checking mysql login on pod %s with secret %s",
                  pod_name, secret_name)
        galera_utils.assert_mysql_login(
            pod_name, podified.get_secret_password(
                secret, galera_utils.SECRET_PASSWORD_KEYS))

    def test_default_root_account_created(self):
        galera = self._get_galera()
        if galera.get('spec', {}).get('rootDatabaseAccount'):
            tobiko.skip_test("Custom rootDatabaseAccount is configured")

        account_name = galera_utils.get_root_account_name(galera)
        LOG.info("Using MariaDBAccount: %s", account_name)
        account = galera_utils.get_mariadb_account(account_name)
        self.assertIsNotNone(account, f"{account_name} MariaDBAccount missing")
        self.assertEqual('System', account.get('spec', {}).get('accountType'))

        root_secret = galera.get('status', {}).get('rootDatabaseSecret')
        LOG.info("Galera rootDatabaseSecret: %s", root_secret)
        self.assertTrue(root_secret, "rootDatabaseSecret is empty")
        self._assert_secret_login(root_secret)

    def test_custom_root_account_respected(self):
        galera = self._get_galera()
        custom_account = galera.get('spec', {}).get('rootDatabaseAccount')
        if not custom_account:
            tobiko.skip_test("No custom rootDatabaseAccount configured")
        LOG.info("Using custom MariaDBAccount: %s", custom_account)

        default_account = galera_utils.get_default_root_account_name(galera)
        if custom_account == default_account:
            tobiko.skip_test("Custom rootDatabaseAccount matches default name")

        default_account_obj = galera_utils.get_mariadb_account(default_account)
        self.assertIsNone(default_account_obj,
                          f"Default account {default_account} exists")

        account = galera_utils.get_mariadb_account(custom_account)
        self.assertIsNotNone(
            account, f"{custom_account} MariaDBAccount missing"
        )
        secret_name = account.get('status', {}).get('currentSecret')
        self.assertTrue(secret_name,
                        "MariaDBAccount.status.currentSecret not set")
        LOG.info("MariaDBAccount currentSecret: %s", secret_name)

        root_secret = galera.get('status', {}).get('rootDatabaseSecret')
        LOG.info("Galera rootDatabaseSecret: %s", root_secret)
        self.assertEqual(secret_name, root_secret)
        self._assert_secret_login(secret_name)
