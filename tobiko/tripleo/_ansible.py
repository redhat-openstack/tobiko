# Copyright 2020 Red Hat
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

import functools
import io
import os
import re
import typing

from oslo_log import log
from packaging import version

import tobiko
from tobiko import config
from tobiko.shell import ansible
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.tripleo import _overcloud
from tobiko.tripleo import _undercloud
from tobiko.tripleo import _config


LOG = log.getLogger(__name__)


def get_tripleo_ansible_inventory():
    inventory_file = get_tripleo_ansible_inventory_file()
    with io.open(inventory_file, 'rb') as fd:
        return tobiko.load_yaml(fd)


def has_tripleo_ansible_inventory() -> bool:
    inventory_file = get_tripleo_ansible_inventory_file()
    return inventory_file is not None


skip_if_missing_tripleo_ansible_inventory = \
    tobiko.skip_unless("Can't read TripleO Ansible inventory",
                       has_tripleo_ansible_inventory)


@functools.lru_cache()
def get_tripleo_ansible_inventory_file() -> typing.Optional[str]:
    if _undercloud.has_undercloud():
        inventory_file = config.CONF.tobiko.rhosp.inventory_file
        if inventory_file:
            inventory_file = tobiko.tobiko_config_path(inventory_file)
            fetch_tripleo_inventary_file(inventory_file=inventory_file)
            return inventory_file
    return None


def skip_unless_undercloud_has_ansible(min_version: float = None):
    reason = ("Ansible not found on undercloud host "
              f"(min_version={min_version})")
    return tobiko.skip_unless(reason=reason,
                              predicate=has_undercloud_ansible_version,
                              min_version=min_version)


def has_undercloud_ansible_version(min_version: float = None) -> bool:
    ssh_client = _undercloud.undercloud_ssh_client()
    try:
        output = sh.execute('ansible --version',
                            ssh_client=ssh_client).stdout
    except sh.ShellCommandFailed:
        LOG.debug("Error getting ansible version", exc_info=1)
        return False

    if min_version is not None:
        first_line = output.splitlines()[0]
        # obtain the ansible version with a regex
        # the expected output can have a format like these
        # ansible 2.9.27
        # ansible [core 2.12.2]
        search_version = re.search(r'(\d+\.)?(\d+\.)?(\*|\d+)', first_line)
        if not search_version:
            return False
        ansible_version_full = search_version.group(0)
        version_pair = ansible_version_full.split('.', 2)[:2]
        # compare versions rather than floats - example of a posible mistake:
        # version 2.12 is higher than version 2.9
        current_version = version.parse('.'.join(version_pair))
        if current_version < version.parse(str(min_version)):
            LOG.debug(f"Ansible version is < {min_version}:\n"
                      f"{first_line}\n")
            return False
    return True


READ_TRIPLEO_ANSIBLE_INVENTORY_SCRIPT = """
source {undercloud_rcfile} || exit 1

set -x

if [ "$OS_CLOUD" == "" ]; then
    # on some releases tripleo-ansible-inventory command is supported
    INVENTORY_FILE=$(mktemp tripleo-hosts-XXXXXXXXXX.yaml)
    tripleo-ansible-inventory --ansible_ssh_user "{overcloud_ssh_username}" \\
                              --static-yaml-inventory "$INVENTORY_FILE"
    RC=$?

    if [ $RC == 0 ]; then
        cat "$INVENTORY_FILE"
    fi
    rm -fR "$INVENTORY_FILE"
    exit $RC
fi

# on latest releases, the updated inventory can always be found into the
# following path
TAI_DIR=~/overcloud-deploy/overcloud/config-download/overcloud
cat $TAI_DIR/tripleo-ansible-inventory.yaml
"""


def read_tripleo_ansible_inventory():
    tripleo = _config.get_tripleo_config()
    ssh_client = _undercloud.undercloud_ssh_client()
    script = READ_TRIPLEO_ANSIBLE_INVENTORY_SCRIPT.format(
        undercloud_rcfile=tripleo.undercloud_rcfile[0],
        overcloud_ssh_username=_overcloud.get_overcloud_ssh_username())
    return sh.execute('/bin/bash', stdin=script, ssh_client=ssh_client).stdout


def fetch_tripleo_inventary_file(inventory_file: str):
    content = read_tripleo_ansible_inventory()
    tobiko.makedirs(os.path.dirname(inventory_file))
    with io.open(inventory_file, 'w') as fd:
        fd.write(content)


class UndercloudAnsiblePlaybook(ansible.AnsiblePlaybook):

    @property
    def ssh_client(self) -> ssh.SSHClientType:
        return _undercloud.undercloud_ssh_client()

    def _ensure_inventory_files(self, *inventory_filenames: str) \
            -> typing.List[str]:
        inventory_file = get_tripleo_ansible_inventory_file()
        if inventory_file is not None:
            inventory_filenames += (inventory_file,)
        return super()._ensure_inventory_files(*inventory_filenames)


def undercloud_ansible_playbook() -> UndercloudAnsiblePlaybook:
    return tobiko.get_fixture(UndercloudAnsiblePlaybook)


def run_playbook_from_undercloud(
        command: sh.ShellCommand = None,
        playbook: str = None,
        playbook_dirname: str = None,
        playbook_filename: str = None,
        inventory_filenames: typing.Iterable[str] = None,
        playbook_files: typing.Iterable[str] = None,
        requirements_files: typing.Iterable[str] = None,
        roles: typing.Iterable[str] = None,
        roles_path: typing.Iterable[str] = None,
        verbosity: int = None):
    return undercloud_ansible_playbook().run_playbook(
        command=command,
        playbook=playbook,
        playbook_dirname=playbook_dirname,
        playbook_filename=playbook_filename,
        inventory_filenames=inventory_filenames,
        playbook_files=playbook_files,
        requirements_files=requirements_files,
        roles=roles,
        roles_path=roles_path,
        verbosity=verbosity)


def setup_undercloud_ansible_playbook():
    if _undercloud.has_undercloud():
        ansible.register_ansible_playbook(
            undercloud_ansible_playbook())
