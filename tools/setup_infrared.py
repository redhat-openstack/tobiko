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

import os
import subprocess
import sys

TOP_DIR = os.path.dirname(os.path.dirname(__file__))
if TOP_DIR not in sys.path:
    sys.path.insert(0, TOP_DIR)

from tools import common

LOG = common.get_logger(__name__)


def main():
    common.setup_logging()
    show_infrared_version()

    plugin_path = os.environ.get('IR_TOBIKO_PLUGIN')
    if plugin_path:
        add_tobiko_plugin(path=plugin_path)

    show_infrared_workspaces()
    ensure_workspace()
    copy_inventory()


def show_infrared_version():
    return common.execute('ir --version || ir --version', capture_stdout=False)


def show_infrared_plugins():
    return common.execute('ir plugin list', capture_stdout=False)


def has_plugin(name):
    try:
        common.execute("ir plugin list | awk '( $4 == \"{}\" )'", name,
                       capture_stdout=False)
    except subprocess.CalledProcessError as ex:
        LOG.debug("tobiko plugin not found ({})", ex)
        return False
    else:
        LOG.info("tobiko plugin found")
        return True


def show_infrared_workspaces():
    return common.execute('ir workspace list', capture_stdout=False)


def add_tobiko_plugin(path=None):
    if has_plugin('tobiko'):
        remove_plugin('tobiko')
    add_plugin(path)
    show_infrared_plugins()


def remove_plugin(name):
    try:
        common.execute('ir plugin remove "{}"', name)
    except subprocess.CalledProcessError as ex:
        LOG.debug("plug-in '%s' not removed: %s", name, ex)
        return False
    else:
        LOG.info("plug-in '%s' removed", name)
        return True


def add_plugin(path):
    path = common.normalize_path(path)
    if not os.path.isdir(path):
        message = ("invalid plug-in directory: '{}'").format(path)
        raise RuntimeError(message)

    common.execute('ir plugin add "{}"', path)
    LOG.info("plug-in added from path '%s'", path)


def ensure_workspace(filename=None):
    filename = (filename or
                os.environ.get('IR_WORKSPACE_FILE') or
                'workspace.tgz')
    filename = common.normalize_path(filename)
    workspace = common.name_from_path(filename)
    if os.path.isfile(filename):
        try:
            common.execute('ir workspace delete "{}"', workspace)
        except subprocess.CalledProcessError as ex:
            LOG.debug("workspace '%s' not deleted: %s", workspace, ex)
        common.execute('ir workspace import "{}"', filename)
        LOG.info("workspace imported from file '%s'", filename)
        return
    else:
        LOG.debug("workspace file not found: '%s'", filename)

    try:
        common.execute('ir workspace checkout "{}"', workspace)
    except subprocess.CalledProcessError as ex:
        LOG.debug("workspace '%s' not checked out: %s", workspace, ex)
    else:
        LOG.info("workspace '%s' checked out", workspace)
        return

    common.execute('infrared workspace checkout --create "{}"', workspace)
    LOG.info("workspace '%s' created", workspace)


def copy_inventory(filename=None):
    filename = (filename or
                os.environ.get('ANSIBLE_INVENTORY') or
                'ansible_hosts')
    if not os.path.isfile(filename):
        LOG.debug('inventary file not found: %r', filename)
        return False

    dest_file = common.execute('ir workspace inventory')
    LOG.debug("got workspace inventory file: '%s'", dest_file)

    dest_dir = os.path.basename(dest_file)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        LOG.info("directory created: '%s'", dest_dir)

    common.execute('cp {} {}', filename, dest_file)
    LOG.info("inventary file '%s' copied to '%s'", filename, dest_file)
    return True


if __name__ == '__main__':
    main()
