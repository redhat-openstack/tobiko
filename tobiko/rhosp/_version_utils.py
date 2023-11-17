# Copyright 2022 Red Hat
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

import tobiko
from tobiko.shell import sh


@functools.lru_cache()
def get_rhosp_release(connection: sh.ShellConnectionType = None) \
        -> str:
    connection = sh.shell_connection(connection)
    with connection.open_file('/etc/rhosp-release', 'r') as fd:
        rhosp_release = fd.read().strip()
    if isinstance(rhosp_release, bytes):
        rhosp_release = rhosp_release.decode('UTF-8', 'ignore')
    return rhosp_release


def get_rhosp_version(connection: sh.ShellConnectionType = None) \
        -> tobiko.Version:
    return tobiko.parse_version(get_rhosp_release(connection))
