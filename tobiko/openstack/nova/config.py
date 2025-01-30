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

DEFAULT_KEY_TYPE = 'ecdsa'
DEFAULT_KEY_FILE = f'~/.ssh/id_{DEFAULT_KEY_TYPE}'

GROUP_NAME = "nova"
OPTIONS = [
    cfg.StrOpt('key_file',
               default=DEFAULT_KEY_FILE,
               help="Default SSH key to login to server instances"),
    cfg.StrOpt('key_type',
               default=DEFAULT_KEY_TYPE,
               help="Default SSH key type to login to server instances"),
    cfg.FloatOpt('advanced_vm_connection_timeout',
                 default=1500.,
                 help="Timeout (in seconds) for establishing connection "
                      "to advanced_vm"),
    cfg.FloatOpt('advanced_vm_is_reachable_timeout',
                 default=900.,
                 help="Timeout (in seconds) till advanced_vm is reachable"),
    cfg.FloatOpt('cloudinit_is_reachable_timeout',
                 default=600.,
                 help="Timeout (in seconds) till cloud-init based server is "
                      "reachable")
]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup('nova'), opts=OPTIONS)


def list_options():
    return [(GROUP_NAME, itertools.chain(OPTIONS))]
