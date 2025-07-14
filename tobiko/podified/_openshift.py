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

import glob
import json
import typing

import netaddr
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.shell import http_ping
from tobiko.shell import iperf3
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.shell import ssh

CONF = config.CONF
LOG = log.getLogger(__name__)

OSP_CONTROLPLANE = 'openstackcontrolplane'
OSP_DP_NODESET = 'openstackdataplanenodeset'
OSP_CONFIG_SECRET_NAME = 'secret/openstack-config-secret'
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
_TOBIKO_PROJECT_EXISTS = None

try:
    import openshift_client as oc
except ModuleNotFoundError:
    _IS_OC_CLIENT_AVAILABLE = False

# NOTE(slaweq): This path is "hardcoded" in the tobiko.shell.ping._ping
# module currently so lets use it here like that as well. Maybe in the
# future there will be need to make it configurable but for now it is
# not needed.
PING_RESULTS_DIR = 'tobiko_ping_results'
# Also directory where results are stored inside the POD is hardcoded,
# It is in the $HOME/{PING_RESULTS_DIR}/ and $HOME inside the tobiko container
# is "/var/lib/tobiko"
POD_PING_RESULTS_DIR = f"/var/lib/tobiko/{PING_RESULTS_DIR}"

HTTP_PING_RESULTS_DIR = "tobiko_http_ping_results"
POD_HTTP_PING_RESULTS_DIR = f"/var/lib/tobiko/{HTTP_PING_RESULTS_DIR}"


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
    secret_name = (
        f'secret/{CONF.tobiko.podified.dataplane_node_ssh_key_secret}')
    try:
        with oc.project(CONF.tobiko.podified.osp_project):
            secret_object = oc.selector(secret_name).object()
        private_key = secret_object.as_dict(
            ).get('data', {}).get('ssh-privatekey', "")
        public_key = secret_object.as_dict(
            ).get('data', {}).get('ssh-publickey', "")
    except oc.OpenShiftPythonException as err:
        LOG.error("Error while trying to get Dataplane secret SSH Key: %s",
                  err)
    return private_key, public_key


def get_openstack_config_secret():
    with oc.project(CONF.tobiko.podified.osp_project):
        try:
            secret_object = oc.selector(OSP_CONFIG_SECRET_NAME).object()
        except oc.OpenShiftPythonException as err:
            LOG.info("Error while trying to get openstack config secret "
                     f"{OSP_CONFIG_SECRET_NAME} from Openshift. Error: {err}")
            return
    return secret_object.as_dict()


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


def _project_exists(name):
    projects_selector = oc.selector(f"projects/{name}")
    return not len(projects_selector.objects()) == 0


def _ensure_project_exists(name):
    # pylint: disable=global-statement
    global _TOBIKO_PROJECT_EXISTS
    if not _TOBIKO_PROJECT_EXISTS and not _project_exists(name):
        project_def = {
            'apiVersion': 'v1',
            'kind': 'Namespace',
            'metadata': {
                'name': name
            }
        }
        oc.create(project_def)
        _TOBIKO_PROJECT_EXISTS = True


def tobiko_project_context():
    _ensure_project_exists(CONF.tobiko.podified.background_tasks_project)
    return oc.project(CONF.tobiko.podified.background_tasks_project)


def check_or_start_tobiko_ping_command(server_ip):
    cmd_args = ['ping', server_ip, '--interval', CONF.tobiko.ping.interval]
    pod_name = f'tobiko-ping-{server_ip}'.replace('.', '-')
    return check_or_start_tobiko_command(
        cmd_args, pod_name, _check_ping_results)


def check_or_start_tobiko_command(cmd_args, pod_name, check_function):
    pod_obj = _get_pod(pod_name)
    if pod_obj:
        # in any case test is still running, check for failures:
        # execute process check i.e. go over results file
        # truncate the log file and restart the POD with background
        # command
        LOG.info('running a check function: '
                 f'on results of processes: {pod_name}')
        check_function(pod_obj)
        with tobiko_project_context():
            pod_obj.delete(ignore_not_found=True)
            LOG.info('checked and stopped previous tobiko command '
                     f'POD {pod_name}; starting a new POD.')
    elif config.is_prevent_create():
        tobiko.fail(f'Expected POD {pod_name} not running. '
                    f'That POD should have been running: {cmd_args}')
    else:
        # First time the test is run:
        # if POD by specific name is not present start one:
        LOG.info('No previous tobiko command POD found: '
                 f'{pod_name}, starting a new POD '
                 f'of function: {cmd_args}')

    pod_obj = _start_tobiko_command_pod(cmd_args, pod_name)
    # check test is not failing from the beginning
    check_function(pod_obj)


def _get_pod(pod_name):
    with tobiko_project_context():
        pod_sel = oc.selector(f'pod/{pod_name}')
        if len(pod_sel.objects()) > 1:
            raise tobiko.MultipleObjectsFound(pod_sel.objects())
        if not pod_sel.objects():
            return
        return pod_sel.objects()[0]


def _start_pod(cmd, args, pod_name, pod_image):
    pod_def = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": CONF.tobiko.podified.background_tasks_project
        },
        "spec": {
            "containers": [{
                "name": pod_name,
                "image": pod_image,
                "command": cmd,
                # All items from args have to be converted to
                # strings, otherwise the pod creation may fail
                "args": [str(arg) for arg in args],
            }],
            "restartPolicy": "Never"
        }
    }

    if CONF.tobiko.podified.tobiko_pod_extra_network:
        pod_def["metadata"]["annotations"] = {
            "k8s.v1.cni.cncf.io/networks":
            CONF.tobiko.podified.tobiko_pod_extra_network}
    if CONF.tobiko.podified.tobiko_pod_tolerations:
        pod_def["spec"]["tolerations"] = \
            CONF.tobiko.podified.tobiko_pod_tolerations
    if CONF.tobiko.podified.tobiko_pod_node_selector:
        pod_def["spec"]["nodeSelector"] = \
            CONF.tobiko.podified.tobiko_pod_node_selector

    with tobiko_project_context():
        pod_sel = oc.create(pod_def)
        with oc.timeout(CONF.tobiko.podified.tobiko_start_pod_timeout):
            try:
                success, pod_objs, _ = pod_sel.until_all(
                    success_func=lambda pod:
                        pod.as_dict()['status']['phase'] == 'Running'
                )
            except oc.OpenShiftPythonException:
                LOG.error(f'Pod {pod_name} creation failed')
                pod_describe = oc.selector(
                    f'pod/{pod_name}').object().describe()
                LOG.error(f'{pod_describe}')
                raise

    if success:
        return pod_objs[0]


def _start_tobiko_command_pod(cmd_args, pod_name):
    return _start_pod(
        cmd=["tobiko"], args=cmd_args, pod_name=pod_name,
        pod_image=CONF.tobiko.podified.tobiko_image)


def _copy_file_from_pod(pod, src, dest, dest_file_pattern):
    for attempt in tobiko.retry(timeout=30., interval=5.):
        cp = oc.oc_action(pod.context, 'cp', [src, dest])
        if cp.status == 0 and glob.glob(dest_file_pattern):
            break
        elif attempt.is_last:
            tobiko.fail("Failed to copy files from the POD "
                        f"{pod.name()}. Error: {cp.err}")


def _check_ping_results(pod):
    # NOTE(slaweq): we have to put ping log files in the directory
    #   as defined below because it is expected to be like that by the
    #   tobiko.shell.ping._ping module so we can use those existing
    #   functions to check results
    ping_results_dest = f'{sh.get_user_home_dir()}/{PING_RESULTS_DIR}'
    ping_log_file_pattern = f'{ping_results_dest}/ping_*.log'
    _copy_file_from_pod(
        pod, f"{pod.name()}:{POD_PING_RESULTS_DIR}", ping_results_dest,
        ping_log_file_pattern)
    # ping.check_ping_statistics() calls tobiko.truncate_logfile(filename) to
    # rename log files to ping_<IP>.log_<date>
    ping.check_ping_statistics()


def execute_in_pod(pod_name, command, container_name=None):
    with oc.project(CONF.tobiko.podified.osp_project):
        return oc.selector(f'pod/{pod_name}').object().execute(
            ['sh', '-c', command], container_name=container_name)


def _get_iperf_client_pod_name(
        address: typing.Union[str, netaddr.IPAddress]) -> str:
    return f'tobiko-iperf-client-{address}'.replace('.', '-')


def _store_iperf3_client_results(
        address: typing.Union[str, netaddr.IPAddress],
        output_dir: str = 'tobiko_iperf_results'):
    # openshift client returns logs in dict where keyname has format
    # <fully-qualified-name> -> <log output>
    # In this case, we don't really need to check it as requested logs
    # are only from the single POD so it can just try to get first
    # item from the dict's values()
    pod_obj = _get_pod(_get_iperf_client_pod_name(address))
    raw_pod_logs = list(pod_obj.logs().values())[0]
    if not raw_pod_logs:
        LOG.warning('No logs from the iperf3 client POD.')
        return

    # Logs are printed by ipef3 client to the stdout in json
    # format, but the format is different then what is stored
    # in the file when "--logfile" option is used in ipef3
    # So to be able to validate them in the same way, logs from
    # stdout of the Pod needs to be converted
    iperf3_results_data = iperf3.parse_json_stream_output(raw_pod_logs)

    logfile = iperf3.get_iperf3_logs_filepath(address, output_dir)
    with open(logfile, "w") as f:
        json.dump(iperf3_results_data, f)


def start_iperf3(
        address: typing.Union[str, netaddr.IPAddress],
        bitrate: int = None,
        download: bool = None,
        port: int = None,
        protocol: str = None,
        iperf3_server_ssh_client: ssh.SSHClientType = None,
        **kwargs):  # noqa; pylint: disable=W0613

    if iperf3_server_ssh_client:
        iperf3.start_iperf3_server(
            port, protocol, iperf3_server_ssh_client)

    parameters = iperf3.iperf3_client_parameters(
        address=address, bitrate=bitrate,
        download=download, port=port, protocol=protocol,
        timeout=0, json_stream=True)

    cmd_args = iperf3.get_iperf3_client_command(
            parameters).as_list()[1:]
    pod_name = _get_iperf_client_pod_name(address)
    _start_pod(
        cmd=["iperf3"], args=cmd_args, pod_name=pod_name,
        pod_image=CONF.tobiko.podified.iperf3_image)


def stop_iperf3_client(
        address: typing.Union[str, netaddr.IPAddress],
        **kwargs):  # noqa; pylint: disable=W0613
    # First logs from the POD needs to be stored in the file
    # so that it can be validated later
    _store_iperf3_client_results(address)

    pod_obj = _get_pod(_get_iperf_client_pod_name(address))
    with tobiko_project_context():
        pod_obj.delete(ignore_not_found=True)


def iperf3_pod_alive(
        address: typing.Union[str, netaddr.IPAddress],  # noqa; pylint: disable=W0613
        **kwargs) -> bool:
    pod_obj = _get_pod(_get_iperf_client_pod_name(address))
    if not pod_obj:
        return False
    return pod_obj.as_dict()['status']['phase'] == 'Running'


def _get_http_ping_pod_name(
        server_ip: typing.Union[str, netaddr.IPAddress]) -> str:
    return f'tobiko-http-ping-{server_ip}'.replace('.', '-')


def _check_http_ping_results_from_pod(pod):
    """Copy log file from the POD and then check file locally."""
    results_dest = http_ping.get_log_dir()
    log_file_pattern = f'{results_dest}/http_ping_*.log'
    _copy_file_from_pod(
        pod, f"{pod.name()}:{POD_HTTP_PING_RESULTS_DIR}", results_dest,
        log_file_pattern)
    http_ping.check_http_ping_results()


def check_or_start_tobiko_http_ping_command(
        server_ip: typing.Union[str, netaddr.IPAddress]):
    cmd_args = ['http', 'ping', server_ip]
    pod_name = _get_http_ping_pod_name(server_ip)
    return check_or_start_tobiko_command(
        cmd_args, pod_name, _check_http_ping_results_from_pod)


def get_ocp_node_uptime(node_name: str):
    # timeout is needed to avoid that the `oc debug` command gets stuck forever
    output = sh.execute(f"timeout 10 oc debug node/{node_name} -- "
                        "chroot /host cat /proc/uptime").stdout
    uptime_line = output.splitlines()[0]
    uptime_string = uptime_line.split()[0]
    return float(uptime_string)


def reboot_ocp_node(node_name: str):
    LOG.debug(f"Rebooting OCP node {node_name}...")
    sh.execute(f"oc debug node/{node_name} -- chroot /host reboot")
    LOG.debug(f"Reboot command sent to OCP node {node_name}.")
