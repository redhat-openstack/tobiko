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

from tobiko import podified
from tobiko.podified import galera as galera_utils


LOG = log.getLogger(__name__)


@podified.skip_if_not_podified
class GaleraRootPasswordSanityTest(testtools.TestCase):

    def _get_galera(self):
        galera = galera_utils.get_galera()
        LOG.info("Using Galera CR: %s", galera['metadata']['name'])
        return galera

    def _assert_secret_login(self, galera_name, secret_name):
        secret = podified.get_secret(secret_name)
        self.assertIsNotNone(secret, f"Secret {secret_name} missing")
        pod_name = galera_utils.get_galera_pod_name(galera_name)
        LOG.debug("Checking mysql login on pod %s with secret %s",
                  pod_name, secret_name)
        galera_utils.assert_mysql_login(
            pod_name, podified.get_secret_password(
                secret, galera_utils.SECRET_PASSWORD_KEYS))

    def test_root_account_and_password(self):
        galera = self._get_galera()

        account_name = galera_utils.get_root_account_name(galera)
        LOG.info("Using MariaDBAccount: %s", account_name)

        spec_account = galera.get('spec', {}).get('rootDatabaseAccount')
        if spec_account:
            LOG.info("Galera spec.rootDatabaseAccount: %s", spec_account)
            self.assertEqual(
                spec_account, account_name,
                "status.rootDatabaseAccount does not match the configured "
                "spec.rootDatabaseAccount")

        account = galera_utils.get_mariadb_account(account_name)
        self.assertIsNotNone(account, f"{account_name} MariaDBAccount missing")
        self.assertEqual('System', account.get('spec', {}).get('accountType'))

        galera_secret_name = galera.get('status', {}).get(
            'rootDatabaseSecret')
        LOG.info("Galera rootDatabaseSecret: %s", galera_secret_name)
        self.assertTrue(galera_secret_name, "rootDatabaseSecret is empty")

        account_secret_name = account.get('status', {}).get('currentSecret')
        LOG.info("MariaDBAccount currentSecret: %s", account_secret_name)
        self.assertEqual(galera_secret_name, account_secret_name)

        self._assert_secret_login(
            galera['metadata']['name'], galera_secret_name)
