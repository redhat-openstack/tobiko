# Copyright 2023 Red Hat
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

import itertools

from oslo_config import cfg

GROUP_NAME = 'manila'
OPTIONS = [
    cfg.StrOpt('service_name',
               default='shared-file-system',
               help="Keystone service name for Manila "
                    "(e.g. 'shared-file-system', 'manilav2' or 'manila')."),
    cfg.StrOpt('share_protocol',
               default='nfs',
               help="Share protocol"),
    cfg.IntOpt('size',
               default=1,
               help="Default size in GB for shares created by share tests."),
    cfg.StrOpt('default_share_type_name',
               default='default',
               help="Default share type's name"),
    cfg.BoolOpt('spec_driver_handles_share_servers',
                default=False,
                help="Specifies whether the driver handles the share servers "
                     "or not"),
    # Upgrade test configuration
    cfg.StrOpt('access_type',
               default='ip',
               help="Access type for Manila share (ip, user, cert, cephx)"),
    cfg.StrOpt('access_to',
               default=None,
               help="Access to value (IP address, username, etc.) "
                    "for Manila share access rule"),
    cfg.StrOpt('access_level',
               default='rw',
               help="Access level for Manila share (rw, ro)"),
    cfg.StrOpt('mount_point',
               default='/mnt/tobiko_manila_test',
               help="Mount point for Manila share on destination host"),
    cfg.StrOpt('mount_options',
               default='',
               help="Mount options for Manila share (comma-separated)"),
    cfg.StrOpt('destination_host',
               default=None,
               help="Hostname or IP of the destination host "
                    "where share will be mounted"),
    cfg.StrOpt('destination_ssh_username',
               default=None,
               help="SSH username for destination host"),
    cfg.StrOpt('destination_ssh_key_filename',
               default=None,
               help="SSH key filename for destination host"),
    cfg.StrOpt('date_log_filename',
               default='date_log.txt',
               help="Filename for date log on mounted share"),
]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup(GROUP_NAME), opts=OPTIONS)


def list_options():
    return [(GROUP_NAME, itertools.chain(OPTIONS))]
