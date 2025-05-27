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

GROUP_NAME = "topology"
OPTIONS = [
    cfg.ListOpt('nodes',
                default=None,
                help="List of hostname nodes"),
    cfg.StrOpt('key_file',
               default=None,
               help="Default SSH key to login to cloud nodes"),
    cfg.StrOpt('username',
               default=None,
               help="Default username for SSH login"),
    cfg.StrOpt('port',
               default=None,
               help="Default port for SSH login"),
    cfg.StrOpt('ip_version',
               default=None,
               choices=['', '4', '6'],
               help="Limit connectivity to cloud to IPv4 o IPv6"),
    cfg.StrOpt('log_datetime_pattern',
               default=r"(\d{4}-\d{2}-\d{2} [0-9:.]+) .+",
               help="Regex to be used to parse date and time from "
                    "the OpenStack services' log lines. "),
    cfg.StrOpt('devstack_neutron_service',
               default='neutron-api',
               help="Name of the neutron service on an Openstack environment "
                    "deployed with devstack"),
]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup(GROUP_NAME), opts=OPTIONS)


def list_options():
    return [(GROUP_NAME, itertools.chain(OPTIONS))]
