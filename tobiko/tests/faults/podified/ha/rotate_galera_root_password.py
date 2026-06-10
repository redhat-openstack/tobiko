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

import uuid

from oslo_log import log

import tobiko
from tobiko import podified
from tobiko.podified import galera as galera_utils


LOG = log.getLogger(__name__)

FINALIZER = 'openstack.org/mariadbaccount'


def _assert_auth_script_select_1(pod_name, script_path):
    """Assert auth script provides working credentials."""
    command = (f'. {script_path}; '
               f'{galera_utils.MYSQL_SELECT_1}')
    result = podified.execute_in_pod(pod_name, command, 'galera')
    podified.assert_command_ok(result, command)


def _wait_for_secret_convergence(account_name, new_secret, pod_name,
                                 script_path):
    """Check zero-downtime auth while rotation converges to the new secret."""
    for attempt in tobiko.retry(timeout=600, interval=5):
        _assert_auth_script_select_1(pod_name, script_path)
        galera = galera_utils.get_galera()
        current = galera.get('status', {}).get('rootDatabaseSecret')
        if current == new_secret:
            LOG.info("rootDatabaseSecret converged to %s", new_secret)
            return
        account = galera_utils.get_mariadb_account(account_name)
        current_secret = (account or {}).get(
            'status', {}).get('currentSecret')
        LOG.info("Waiting for convergence: "
                 "rootDatabaseSecret=%s, "
                 "MariaDBAccount.status.currentSecret=%s",
                 current, current_secret)
        attempt.check_limits()


def _validate_post_rotation(pod_name, script_path, new_secret):
    """Validate mysql login and auth script after convergence."""
    secret = podified.get_secret(new_secret)
    if not secret:
        tobiko.fail(f"Secret {new_secret} missing")
    password = podified.get_secret_password(
        secret, galera_utils.SECRET_PASSWORD_KEYS)
    galera_utils.assert_mysql_login(pod_name, password)
    LOG.info("Direct mysql login with new password succeeded")

    command = (f'. {script_path}; '
               f'{galera_utils.MYSQL_SELECT_1}')
    result = podified.execute_in_pod(pod_name, command, 'galera')
    podified.assert_command_ok(result, command)
    LOG.info("Auth script mysql login succeeded after convergence")


def _wait_for_finalizer_swap(new_secret, old_secret):
    """Wait for the finalizer to move from old to new secret."""
    for attempt in tobiko.retry(timeout=300, interval=15):
        new_has = podified.secret_has_finalizer(new_secret, FINALIZER)
        old_has = podified.secret_has_finalizer(old_secret, FINALIZER)
        if new_has and not old_has:
            LOG.info("Finalizer swap complete")
            return
        LOG.info("Waiting for finalizer swap: "
                 "new_secret has=%s, old_secret has=%s",
                 new_has, old_has)
        attempt.check_limits()


def _patch_account_secret(account_name, secret_name):
    """Patch MariaDBAccount spec.secret and verify."""
    account_obj = galera_utils.get_mariadb_account_object(account_name)
    if not account_obj:
        tobiko.fail(f"{account_name} MariaDBAccount missing")
    account_obj.model.spec['secret'] = secret_name
    account_obj.apply()
    LOG.info("Updated %s to use secret %s", account_name, secret_name)

    verified = galera_utils.get_mariadb_account(account_name)
    actual = (verified or {}).get('spec', {}).get('secret')
    LOG.info("Verified MariaDBAccount spec.secret after apply: %s",
             actual)
    if actual != secret_name:
        tobiko.fail(
            f"spec.secret patch did not apply: "
            f"expected {secret_name}, got {actual}")


def rotate_galera_root_password():
    """Rotate the root password and validate convergence."""
    galera = galera_utils.get_galera()
    LOG.info("Using Galera CR: %s", galera['metadata']['name'])
    account_name = galera_utils.get_root_account_name(galera)
    LOG.info("Using MariaDBAccount: %s", account_name)

    old_secret = galera.get('status', {}).get('rootDatabaseSecret')
    if not old_secret:
        tobiko.fail("rootDatabaseSecret is empty")
    LOG.info("Current rootDatabaseSecret: %s", old_secret)
    if not podified.secret_has_finalizer(old_secret, FINALIZER):
        tobiko.fail(f"Secret {old_secret} missing finalizer {FINALIZER}")

    new_secret = f'{account_name}-rotation-{uuid.uuid4().hex[:8]}'
    password = f'tobiko-{uuid.uuid4().hex}'
    LOG.info("Rotating to new secret: %s", new_secret)
    podified.create_secret(new_secret, password,
                           key=galera_utils.SECRET_PASSWORD_KEYS[0])
    _patch_account_secret(account_name, new_secret)

    try:
        pod_name = galera_utils.get_galera_pod_name()
        script_path = galera_utils.get_mysql_root_auth_script_path(
            pod_name)
        LOG.debug("Using mysql_root_auth.sh path: %s", script_path)
        _wait_for_secret_convergence(
            account_name, new_secret, pod_name, script_path)
        _validate_post_rotation(pod_name, script_path, new_secret)
        _wait_for_finalizer_swap(new_secret, old_secret)
    except Exception:
        LOG.error("Rotation failed; reverting spec.secret to %s",
                  old_secret)
        _patch_account_secret(account_name, old_secret)
        raise
