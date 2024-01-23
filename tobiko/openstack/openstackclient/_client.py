# Copyright (c) 2020 Red Hat, Inc.
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

import json

from oslo_log import log

from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack.openstackclient import _exception
from tobiko.shell import sh
import tobiko.tripleo


CONF = config.CONF
LOG = log.getLogger(__name__)


def execute(cmd, *args, **kwargs):
    arg_list = _param_list(*args, **kwargs)
    cmd_to_exec = cmd.format(params=' '.join(arg_list))
    if tobiko.tripleo.has_undercloud():
        ssh_client = tobiko.tripleo.undercloud_ssh_client()
    else:
        ssh_client = None
    try:
        LOG.debug(f'Command to be executed:\n{cmd_to_exec}')
        result = sh.execute(cmd_to_exec, ssh_client=ssh_client)
    except sh.ShellCommandFailed as ex:
        if ex.exit_status == 1:
            raise _exception.OSPCliApiError(message=f'{ex.stderr}')
        elif ex.exit_status == 2:
            raise _exception.OSPCliClientError(message=f'{ex.stderr}')
        else:
            raise
    output_format = kwargs.pop('format', '')
    if output_format == 'json':
        return json.loads(result.stdout)
    else:
        return dict()


def _param_list(*args, **kwargs):
    if not any(param in kwargs for param in ['os-token', 'os-username']):
        credentials = keystone.keystone_credentials()
        tmp_auth = {}
        tmp_auth['os-auth-url'] = credentials.auth_url
        tmp_auth['os-password'] = credentials.password
        tmp_auth['os-username'] = credentials.username
        tmp_auth['os-cacert'] = credentials.cacert
        tmp_auth['os-project-name'] = credentials.project_name
        tmp_auth['os-user-domain-name'] = credentials.user_domain_name
        tmp_auth['os-project-domain-name'] = credentials.project_domain_name
        tmp_auth['os-project-domain-id'] = credentials.project_domain_id
        if credentials.api_version == 3:
            tmp_auth['os-identity-api-version'] = credentials.api_version
        if 'https://' in credentials.auth_url and not credentials.cacert:
            tmp_auth['os-cacert'] = \
                CONF.tobiko.tripleo.undercloud_cacert_file
        for key, val in tmp_auth.items():
            if val:
                kwargs[key] = val
    arg_list = []
    for arg in args:
        if len(arg) == 1:
            arg_list.append(f'-{arg}')
        else:
            arg_list.append(f'--{arg}')
    for arg, value in kwargs.items():
        if len(arg) == 1:
            arg_list.append(f'-{arg} {value}')
        else:
            arg_list.append(f'--{arg} {value}')
    return arg_list
