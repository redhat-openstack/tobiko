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

import netaddr
import openshift_client as oc
from oslo_log import log

from tobiko.shell import sh

LOG = log.getLogger(__name__)

OSP_CONTROLPLANE = 'openstackcontrolplane'
OSP_DP_NODESET = 'openstackdataplanenodeset'
DP_SSH_SECRET_NAME = 'secret/dataplane-ansible-ssh-private-key-secret'
OCP_WORKERS = 'nodes'

OVN_DP_SERVICE_NAME = 'ovn'
COMPUTE_DP_SERVICE_NAMES = ['nova', 'nova-custom']

EDPM_COMPUTE_GROUP = 'edpm-compute'
EDPM_NETWORKER_GROUP = 'edpm-networker'
EDPM_OTHER_GROUP = 'edpm-other'


def _is_oc_client_available() -> bool:
    try:
        if sh.execute('which oc').exit_status == 0:
            return True
    except sh.ShellCommandFailed:
        pass
    return False


def _get_group(services):
    for compute_dp_service in COMPUTE_DP_SERVICE_NAMES:
        if compute_dp_service in services:
            return EDPM_COMPUTE_GROUP
    if OVN_DP_SERVICE_NAME in services:
        return EDPM_NETWORKER_GROUP
    return EDPM_OTHER_GROUP


def _get_ocp_worker_hostname(worker):
    for address in worker.get('status', {}).get('addresses', []):
        if address.get('type') == 'Hostname':
            return address['address']


def _get_ocp_worker_addresses(worker):
    return [
        netaddr.IPAddress(address['address']) for
        address in worker.get('status', {}).get('addresses', [])
        if address.get('type') != 'Hostname']


def has_podified_cp() -> bool:
    if not _is_oc_client_available():
        LOG.debug("Openshift CLI client isn't installed.")
        return False
    try:
        return bool(oc.selector(OSP_CONTROLPLANE).objects())
    except oc.OpenShiftPythonException:
        return False


def get_dataplane_ssh_keypair():
    private_key = ""
    public_key = ""
    try:
        secret_object = oc.selector(DP_SSH_SECRET_NAME).object()
        private_key = secret_object.as_dict()['data']['ssh-privatekey']
        public_key = secret_object.as_dict()['data']['ssh-publickey']
    except oc.OpenShiftPythonException as err:
        LOG.error("Error while trying to get Dataplane secret SSH Key: %s",
                  err)
    return private_key, public_key


def list_edpm_nodes():
    nodes = []
    nodeset_sel = oc.selector(OSP_DP_NODESET)
    for nodeset in nodeset_sel.objects():
        nodeset_spec = nodeset.as_dict()['spec']
        node_template = nodeset_spec['nodeTemplate']
        nodeset_nodes = nodeset_spec['nodes']
        group_name = _get_group(nodeset_spec['services'])
        for node in nodeset_nodes.values():
            node_dict = {
                'hostname': node.get('hostName'),
                'host': node['ansible']['ansibleHost'],
                'group': group_name,
                'port': (
                    node.get('ansible', {}).get('ansiblePort') or
                    node_template.get('ansible', {}).get('ansiblePort')),
                'username': (
                    node.get('ansible', {}).get('ansibleUser') or
                    node_template.get('ansible', {}).get('ansibleUser')),
            }
            nodes.append(node_dict)
    return nodes


def list_ocp_workers():
    nodes_sel = oc.selector(OCP_WORKERS)
    ocp_workers = []
    for node in nodes_sel.objects():
        node_dict = node.as_dict()
        ocp_workers.append({
            'hostname': _get_ocp_worker_hostname(node_dict),
            'addresses': _get_ocp_worker_addresses(node_dict)
        })
    return ocp_workers
