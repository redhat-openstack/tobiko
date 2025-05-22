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

GROUP_NAME = "ping"
OPTIONS = [
    cfg.IntOpt('count',
               default=1,
               help="Number of ICMP messages to wait before ending "
                    "ping command execution"),
    cfg.IntOpt('deadline',
               default=5,
               help="Max seconds waited from ping command before "
                    "self terminating himself"),
    cfg.StrOpt('fragmentation',
               default=None,
               help="If False it will not allow ICMP messages to "
                    "be delivered in smaller fragments"),
    cfg.IntOpt('interval',
               default=1,
               help="Seconds of time interval between "
                    "consecutive before ICMP messages"),
    cfg.IntOpt('packet_size',
               default=None,
               help="Size in bytes of ICMP messages (including "
                    "headers and payload)"),
    cfg.IntOpt('timeout',
               default=300.,
               help="Maximum time in seconds a sequence of ICMP "
                    "messages is sent to a destination host before "
                    "reporting as a failure")]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup('ping'), opts=OPTIONS)


def list_options():
    return [(GROUP_NAME, itertools.chain(OPTIONS))]
