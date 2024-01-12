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

from tobiko.rhosp import _version_utils
from tobiko.rhosp import _topology

RhospTopology = _topology.RhospTopology
RhospNode = _topology.RhospNode

get_rhosp_release = _version_utils.get_rhosp_release
get_rhosp_version = _version_utils.get_rhosp_version

ip_to_hostname = _topology.ip_to_hostname
