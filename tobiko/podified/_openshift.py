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
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.shell import sh

CONF = config.CONF
LOG = log.getLogger(__name__)

OSP_CONTROLPLANE = 'openstackcontrolplane'
OSP_DP_NODESET = 'openstackdataplanenodeset'
DP_SSH_SECRET_NAME = 'secret/dataplane-ansible-ssh-private-key-secret'
OSP_BM_HOST = 'baremetalhost.metal3.io'
OSP_BM_CRD = 'baremetalhosts.metal3.io'
OCP_WORKERS = 'nodes'
OVNDBCLUSTER = 'ovndbcluster'

OVN_DP_SERVICE_NAME = 'ovn'
COMPUTE_DP_SERVICE_NAMES = ['nova', 'nova-custom', 'nova-custom-ceph']

EDPM_COMPUTE_GROUP = 'edpm-compute'
EDPM_NETWORKER_GROUP = 'edpm-networker'
EDPM_OTHER_GROUP = 'edpm-other'


_IS_OC_CLIENT_AVAILABLE = None
_IS_BM_CRD_AVAILABLE = None

try:
    import openshift_client as oc
except ModuleNotFoundError:
    _IS_OC_CLIENT_AVAILABLE = False


def _is_oc_client_available() -> bool:
    # pylint: disable=global-statement
    global _IS_OC_CLIENT_AVAILABLE
    if _IS_OC_CLIENT_AVAILABLE is None:
        _IS_OC_CLIENT_AVAILABLE = False
        try:
            if sh.execute('which oc').exit_status == 0:
                _IS_OC_CLIENT_AVAILABLE = True
        except sh.ShellCommandFailed:
            pass
    return _IS_OC_CLIENT_AVAILABLE


def _is_baremetal_crd_available() -> bool:
    # pylint: disable=global-statement
    global _IS_BM_CRD_AVAILABLE
    if not _is_oc_client_available():
        return False
    if _IS_BM_CRD_AVAILABLE is None:
        try:
            # oc.selector("crd") does not need to run on a specific OCP project
            _IS_BM_CRD_AVAILABLE = any(
                [OSP_BM_CRD in n for n in oc.selector("crd").qnames()])
        except oc.OpenShiftPythonException:
            _IS_BM_CRD_AVAILABLE = False
    return _IS_BM_CRD_AVAILABLE


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


def _get_edpm_node_ctlplane_ip_from_status(hostname, node_status):
    all_ips = node_status.get('AllIPs') or node_status.get('allIPs')
    if not all_ips:
        LOG.warning("No IPs found in the Nodeset status: %s",
                    node_status)
        return
    host_ips = all_ips.get(hostname)
    if not host_ips:
        LOG.warning("Host %s not found in AllIPs: %s",
                    hostname, all_ips)
        return
    return host_ips.get('ctlplane')


def has_podified_cp() -> bool:
    if not _is_oc_client_available():
        LOG.debug("Openshift CLI client isn't installed.")
        return False
    try:
        return bool(
            oc.selector(OSP_CONTROLPLANE, all_namespaces=True).objects())
    except oc.OpenShiftPythonException:
        return False


def get_dataplane_ssh_keypair():
    private_key = ""
    public_key = ""
    try:
        with oc.project(CONF.tobiko.podified.osp_project):
            secret_object = oc.selector(DP_SSH_SECRET_NAME).object()
        private_key = secret_object.as_dict()['data']['ssh-privatekey']
        public_key = secret_object.as_dict()['data']['ssh-publickey']
    except oc.OpenShiftPythonException as err:
        LOG.error("Error while trying to get Dataplane secret SSH Key: %s",
                  err)
    return private_key, public_key


def list_edpm_nodes():
    nodes = []
    with oc.project(CONF.tobiko.podified.osp_project):
        nodesets = oc.selector(OSP_DP_NODESET).objects()
    for nodeset in nodesets:
        nodeset_spec = nodeset.as_dict()['spec']
        nodeset_status = nodeset.as_dict()['status']
        node_template = nodeset_spec['nodeTemplate']
        nodeset_nodes = nodeset_spec['nodes']
        group_name = _get_group(nodeset_spec['services'])
        for node in nodeset_nodes.values():
            node_hostname = node.get('hostName')
            node_dict = {
                'hostname': node_hostname,
                'host': (node['ansible'].get('ansibleHost') or
                         _get_edpm_node_ctlplane_ip_from_status(
                             node_hostname, nodeset_status)),
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
    # oc.selector("nodes") does not need to run on a specific OCP project
    nodes_sel = oc.selector(OCP_WORKERS)
    ocp_workers = []
    for node in nodes_sel.objects():
        node_dict = node.as_dict()
        ocp_workers.append({
            'hostname': _get_ocp_worker_hostname(node_dict),
            'addresses': _get_ocp_worker_addresses(node_dict)
        })
    return ocp_workers


def power_on_edpm_node(nodename):
    _set_edpm_node_online_status(nodename, online=True)


def power_off_edpm_node(nodename):
    _set_edpm_node_online_status(nodename, online=False)


def _set_edpm_node_online_status(nodename, online):
    if _is_baremetal_crd_available() is False:
        LOG.info("BareMetal operator is not available in the deployment. "
                 "Starting and stopping EDPM nodes is not supported.")
        return
    try:
        with oc.project(CONF.tobiko.podified.osp_project):
            bm_node = oc.selector(f"{OSP_BM_HOST}/{nodename}").objects()[0]
    except oc.OpenShiftPythonException as err:
        LOG.info(f"Error while trying to get BareMetal Node '{nodename}' "
                 f"from Openshift. Error: {err}")
        return
    except IndexError:
        LOG.error(f"Node {nodename} not found in the {OSP_BM_HOST} CRs.")
        return
    bm_node.model.spec['online'] = online
    try:
        # NOTE(slaweq): returned status is 0 when all operations where
        # finished successfully. Otherwise status will be different than
        # 0, like in the shell scripts
        if not bool(bm_node.apply().status()):
            _wait_for_poweredOn_status(nodename, online)
    except oc.OpenShiftPythonException as err:
        LOG.error(f"Error while applying new online state: {online} for "
                  f"the node: {nodename}. Error: {err}")


def _wait_for_poweredOn_status(nodename, expected_status,
                               timeout: tobiko.Seconds = None):
    for attempt in tobiko.retry(
            timeout=timeout,
            count=10,
            interval=5.,
            default_timeout=30):
        LOG.debug(f"Checking power status of the '{nodename}'.")
        try:
            with oc.project(CONF.tobiko.podified.osp_project):
                poweredOn = oc.selector(
                    f"{OSP_BM_HOST}/{nodename}"
                ).objects()[0].model.status['poweredOn']
        except oc.OpenShiftPythonException as err:
            LOG.error("Error while trying to get 'poweredOn' state of "
                      f"the node {nodename}. Error: {err}")
        else:
            if poweredOn == expected_status:
                LOG.debug(f"Actual poweredOn state of the node {nodename} "
                          f"is: '{poweredOn}' which is as expected.")
                return True
            LOG.debug(f"Actual poweredOn state is: '{poweredOn}' != "
                      f" '{expected_status}'")
        attempt.check_limits()


def get_ovndbcluter(ovndbcluster_name):
    with oc.project(CONF.tobiko.podified.osp_project):
        ovndbcluter = oc.selector(
            f"{OVNDBCLUSTER}/{ovndbcluster_name}").objects()
    if len(ovndbcluter) != 1:
        tobiko.fail(f"Unexpected number of {OVNDBCLUSTER}/{ovndbcluster_name} "
                    f"objects obtained: {len(ovndbcluter)}")
    return ovndbcluter[0].as_dict()


def get_pods(labels=None):
    with oc.project(CONF.tobiko.podified.osp_project):
        return oc.selector('pods', labels=labels).objects()


def get_pod_names(labels=None):
    with oc.project(CONF.tobiko.podified.osp_project):
        return oc.selector('pods', labels=labels).qnames()


def get_pod_count(labels=None):
    with oc.project(CONF.tobiko.podified.osp_project):
        return oc.selector('pods', labels=labels).count_existing()


def delete_pods(labels=None):
    with oc.project(CONF.tobiko.podified.osp_project):
        return oc.selector('pods', labels=labels).delete()
