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

from tobiko.podified import _topology
from tobiko.podified import _openshift
from tobiko.podified import containers


EDPM_NODE = _topology.EDPM_NODE
OCP_WORKER = _topology.OCP_WORKER
EDPM_COMPUTE_GROUP = _openshift.EDPM_COMPUTE_GROUP
EDPM_NETWORKER_GROUP = _openshift.EDPM_NETWORKER_GROUP
EDPM_OTHER_GROUP = _openshift.EDPM_OTHER_GROUP

PodifiedTopology = _topology.PodifiedTopology

skip_if_not_podified = _topology.skip_if_not_podified
skip_if_podified = _topology.skip_if_podified

get_dataplane_ssh_keypair = _openshift.get_dataplane_ssh_keypair
has_podified_cp = _openshift.has_podified_cp
get_ovndbcluter = _openshift.get_ovndbcluter

get_container_runtime_name = containers.get_container_runtime_name
