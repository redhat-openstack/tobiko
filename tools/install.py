#!/usr/bin/env python3
# Copyright 2018 Red Hat
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
import site
import sys


TOP_DIR = os.path.realpath(os.path.dirname(os.path.dirname(__file__)))

if TOP_DIR not in sys.path:
    sys.path.insert(0, TOP_DIR)

from tools import common  # noqa
from tools import get_version  # noqa

LOG = common.get_logger(__name__)

TOX_VERSION = os.environ.get('TOX_VERSION') or '>=4.13'

TOX_CONSTRAINTS = (os.environ.get('TOX_CONSTRAINTS') or
                   f"-c{TOP_DIR}/upper-constraints.txt")


def main():
    common.setup_logging()
    install_tox()
    install_bindeps()
    install_tobiko()


def install_tox(version=TOX_VERSION):
    LOG.info(f"Installing Tox... (version: {version})")
    pip_install(f"'tox{version}'")


def install_bindeps():
    LOG.info(f"Installing Tobiko binary dependencies...")
    common.execute(os.path.join(TOP_DIR, 'tools', 'install-bindeps.sh'),
                   capture_stdout=False)


def install_tobiko():
    version = get_version.get_version()
    LOG.info(f"Installing Tobiko version {version}...")
    pip_install(f"-e '{TOP_DIR}'")


def pip_install(args):
    LOG.debug(f"Installing packages: {args}...")
    common.execute_python(f"-m pip install {TOX_CONSTRAINTS} {args}",
                          capture_stdout=False)


def pip_unisntall(args):
    LOG.debug(f"Uninstalling packages: {args}...")
    common.execute_python(f"-m pip uninstall -y {args}",
                          capture_stdout=False)


if __name__ == '__main__':
    main()
