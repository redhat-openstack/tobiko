# Copyright 2019 Red Hat
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

GROUP_NAME = 'octavia'
OPTIONS = [
    cfg.IntOpt('check_interval',
               default=5,
               help='Interval to check for status changes, in seconds.'),
    cfg.IntOpt('check_timeout',
               default=360,
               help='Timeout, in seconds, to wait for a status change.'),
    cfg.StrOpt('amphora_user',
               default='cloud-user',
               help='The user we should use when we SSH the amphora.'),
]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup(GROUP_NAME), opts=OPTIONS)


def list_options():
    return [(GROUP_NAME, itertools.chain(OPTIONS))]
