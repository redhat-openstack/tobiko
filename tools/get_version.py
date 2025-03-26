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
import sys

TOP_DIR = os.path.realpath(os.path.dirname(os.path.dirname(__file__)))

if TOP_DIR not in sys.path:
    sys.path.insert(0, TOP_DIR)

from tools import common


def main():
    version = get_version()
    sys.stdout.write(f'{version}\n')


CACHE = {}


def get_version():
    version = CACHE.get('version')
    if not version:
        CACHE['version'] = version = common.execute(
            f"git -C '{TOP_DIR}' describe --always").splitlines()[0]
    return version


if __name__ == '__main__':
    main()
