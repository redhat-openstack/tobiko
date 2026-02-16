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

import shlex

import openshift_client as oc
from oslo_log import log

import tobiko
from tobiko import config
from tobiko import podified


LOG = log.getLogger(__name__)
CONF = config.CONF

GALERA_SERVICE = 'openstack-galera'
DEFAULT_ACCOUNT_SUFFIX = 'mariadb-root'
SECRET_PASSWORD_KEYS = ('DatabasePassword', 'databasePassword')
MYSQL_ROOT_AUTH_SCRIPT_DEFAULT = '/var/lib/operator-scripts/mysql_root_auth.sh'
MYSQL_SELECT_1 = 'mysql -u root -e "SELECT 1;"'


def select_galera_name():
    """Pick the Galera CR name to test against.

    Prefer names starting with 'openstack'. Otherwise use the first
    Galera name (sorted).
    """
    with podified.project_context():
        selector = oc.selector('galera')
        galeras = selector.objects()
    if not galeras:
        tobiko.fail("No Galera resources found")
    names = sorted(
        [galera.as_dict()['metadata']['name'] for galera in galeras]
    )
    for name in names:
        if name.startswith('openstack'):
            return name
    return names[0]


def get_galera():
    """Return the selected Galera CR as a dict."""
    galera_name = select_galera_name()
    with podified.project_context():
        selector = oc.selector(f'galera/{galera_name}')
        return selector.object().as_dict()


def get_root_account_name(galera):
    """Return the configured root account name, or the default."""
    root_account = galera.get('spec', {}).get('rootDatabaseAccount')
    if root_account:
        return root_account
    return get_default_root_account_name(galera)


def get_default_root_account_name(galera):
    """Return the default root account name for a Galera CR."""
    return f"{galera['metadata']['name']}-{DEFAULT_ACCOUNT_SUFFIX}"


def get_mariadb_account(account_name):
    """Return a MariaDBAccount CR as a dict or None when missing."""
    account_obj = get_mariadb_account_object(account_name)
    return account_obj.as_dict() if account_obj else None


def get_mariadb_account_object(account_name):
    """Return a MariaDBAccount CR object or None when missing."""
    with podified.project_context():
        selector = oc.selector(f'mariadbaccount/{account_name}')
        if not selector.objects():
            return None
        return selector.object()


def get_galera_pod_name():
    """Return a stable Galera pod name (sorted by name)."""
    pods = podified.get_pods(labels={'service': GALERA_SERVICE})
    if not pods:
        tobiko.skip_test(f"No pods found for service '{GALERA_SERVICE}'")
    pods = sorted(pods, key=lambda pod: pod.name())
    return pods[0].name()


def assert_mysql_login(pod_name, password):
    """Execute a mysql login against the Galera pod using a raw password."""
    escaped_password = shlex.quote(password)
    command = f'mysql -uroot -p{escaped_password} -e "SELECT 1;"'
    for attempt in tobiko.retry(timeout=30, interval=5):
        result = podified.execute_in_pod(pod_name, command, 'galera')
        status = getattr(result, 'status', 0)
        if callable(status):
            status = status()
        if isinstance(status, str) and status.isdigit():
            status = int(status)
        if status in (0, None):
            LOG.debug("MySQL login succeeded on pod %s", pod_name)
            return
        if attempt.is_last:
            stderr = getattr(result, 'err', lambda: '')()
            stdout = getattr(result, 'out', lambda: '')()
            tobiko.fail(
                f"Command failed: {command}\n"
                f"status: {status}\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            )


def get_mysql_root_auth_script_path(pod_name):
    """Return the mysql_root_auth.sh path inside the Galera pod."""
    candidates = [
        MYSQL_ROOT_AUTH_SCRIPT_DEFAULT,
    ]
    for path in candidates:
        command = f'test -f {path} && echo {path}'
        result = podified.execute_in_pod(pod_name, command, 'galera')
        if result.out().strip():
            LOG.debug("mysql_root_auth.sh found at: %s", path)
            return path

    command = (
        'ls -1 /var/lib/operator-scripts/*/mysql_root_auth.sh 2>/dev/null '
        '| head -n 1'
    )
    result = podified.execute_in_pod(pod_name, command, 'galera')
    path = result.out().strip()
    if path:
        LOG.debug("mysql_root_auth.sh found under operator-scripts: %s", path)
        return path

    command = (
        'command -v find >/dev/null 2>&1 && '
        'find /var/lib -maxdepth 4 -type f -name mysql_root_auth.sh '
        '2>/dev/null | head -n 1'
    )
    result = podified.execute_in_pod(pod_name, command, 'galera')
    path = result.out().strip()
    if path:
        LOG.debug("mysql_root_auth.sh found via find at: %s", path)
        return path
    LOG.debug("mysql_root_auth.sh not found; find output: %s", result.out())
    tobiko.fail("mysql_root_auth.sh not found in Galera pod")
