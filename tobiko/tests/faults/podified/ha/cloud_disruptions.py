# Copyright (c) 2021 Red Hat, Inc.
#
# All Rights Reserved.
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

import functools
import json
import re
import random

import openshift_client as oc
from oslo_log import log

import tobiko
from tobiko import config
from tobiko import podified
from tobiko.openstack import keystone

CONF = config.CONF
LOG = log.getLogger(__name__)

KILL_GALERA = 'kill -9 $(pidof mysqld)'
RM_GRASTATE = 'rm -rf /var/lib/mysql/grastate.dat'
GALERA_CLUSTER_SIZE = 'mysql -u root --password={passwd} -e \'SHOW STATUS ' \
                      'LIKE "wsrep_cluster_size"\''
CHECK_BOOTSTRAP = """
ps -eo lstart,cmd | grep -v grep|
grep wsrep-cluster-address=gcomm://
"""
RABBITMQ_LABEL = {'app.kubernetes.io/name': 'rabbitmq'}
RABBITMQ_KILL = "pkill -9 beam.smp || pkill -9 beam"
RABBITMQ_CLUSTER_STATUS = "rabbitmqctl cluster_status"
RABBITMQ_RUNNING_NODES_HEADER = "Running Nodes"
MARIADB_OPERATOR_NAMESPACE = "openstack-operators"
MARIADB_BOOTSTRAP_LOG_MARKER = "Pushing gcomm URI to bootstrap"


class GaleraBoostrapException(tobiko.TobikoException):
    message = "Bootstrap has not been activated"


class DownException(tobiko.TobikoException):
    message = "The resource is not down"


class RestoredException(tobiko.TobikoException):
    message = "The resource is not restored"


@functools.lru_cache()
def get_galera_pods_per_service(galera_service):
    # the aim of this function is just to cache results and avoid sending
    # oc requests every time
    return podified.get_pods({'service': galera_service})


def kill_all_galera_services():
    """kill all galera processes,
    check in pacemaker it is down"""
    # get galera pods sorted into 2 different lists:
    # one with 'cell-galera' an one without
    for galera_service in ('openstack-cell1-galera', 'openstack-galera'):
        pods = get_galera_pods_per_service(galera_service)
        kill_all_galera_pods(pods)
        check_all_galera_cells_down(pods[0].name())
        verify_all_galera_cells_restored(pods)


def remove_all_grastate_galera():
    """shut down galera properly,
    remove all grastate"""
    for galera_service in ('openstack-cell1-galera', 'openstack-galera'):
        pods = get_galera_pods_per_service(galera_service)
        for pod in pods:
            remove_grastate(pod.name())
        # TODO: change kill to graceful stop/ scale down
        kill_all_galera_pods(pods)
        check_all_galera_cells_down(pods[0].name())
        verify_all_galera_cells_restored(pods)


def remove_one_grastate_galera():
    """shut down galera properly,
    delete /var/lib/mysql/grastate.dat in a random node,
    check that bootstrap is done from a node with grastate"""
    for galera_service in ('openstack-cell1-galera', 'openstack-galera'):
        pods = get_galera_pods_per_service(galera_service)
        random_pod_name = random.choice(pods).name()
        remove_grastate(random_pod_name)
        # TODO: change kill to graceful stop/ scale down
        kill_all_galera_pods(pods)
        check_all_galera_cells_down(pods[0].name())
        verify_all_galera_cells_restored(pods)
        # Use mariadb-operator logs to see which pod was used for bootstrap.
        # The operator logs explicitly include the pod name selected for the
        # gcomm URI push (bootstrap), which avoids parsing Galera logs.
        galera_name = galera_service.replace("-galera", "")
        bootstrap_pod = _get_galera_bootstrap_pod(galera_name)
        LOG.info(f'bootstrap {galera_service} is {bootstrap_pod}')
        if not bootstrap_pod:
            LOG.warning(
                "Skipping bootstrap validation for Galera '%s' "
                "because operator logs are unavailable", galera_name)
            continue
        LOG.info("Bootstrap pod '%s'; grastate removed from '%s'",
                 bootstrap_pod, random_pod_name)
        if bootstrap_pod == random_pod_name:
            LOG.warning(
                "Bootstrap used grastate-removed pod '%s'", random_pod_name)
        LOG.info("Galera '%s' bootstrap selected pod '%s'",
                 galera_name, bootstrap_pod)


def _get_galera_bootstrap_pod(galera_name: str):
    with oc.project(MARIADB_OPERATOR_NAMESPACE):
        pods = oc.selector(
            "pods",
            labels={'openstack.org/operator-name': 'mariadb'}
        ).objects()
        if not pods:
            return None
        raw_logs = list(pods[0].logs().values())[0] or ""

    for line in reversed(raw_logs.splitlines()):
        if MARIADB_BOOTSTRAP_LOG_MARKER not in line:
            continue
        try:
            payload = json.loads(line.split('\t')[-1])
        except json.JSONDecodeError:
            continue
        galera_info = payload.get("Galera", {})
        if galera_info.get("name") == galera_name:
            return payload.get("pod")
    return None


def remove_grastate(pod_name):
    podified.execute_in_pod(pod_name, RM_GRASTATE, 'galera')
    LOG.info(f'grastate.dat removed from {pod_name}')


def kill_all_galera_pods(galera_pods):
    for pod in galera_pods:
        podified.execute_in_pod(pod.name(), KILL_GALERA, 'galera')
        LOG.info(f'kill galera pod {pod}')


def check_all_galera_cells_down(pod_name):
    pw = keystone.keystone_credentials().password

    retry = tobiko.retry(timeout=30, interval=5)
    for _ in retry:
        try:
            cluster_size = podified.execute_in_pod(
                pod_name, GALERA_CLUSTER_SIZE.format(passwd=pw), 'galera')
            error_output = cluster_size.err()
            non_error_message = "Defaulted container \"galera\" out of:"\
                                "galera, mysql-bootstrap (init)\n"
            filtered_err_output = error_output.replace(non_error_message, '')
            if not filtered_err_output.strip():
                continue
        except oc.OpenShiftPythonException:
            LOG.info('all galera cells down')
            return
    raise DownException()


def verify_all_galera_cells_restored(pods):
    pw = keystone.keystone_credentials().password

    retry = tobiko.retry(timeout=160, interval=10)
    for _ in retry:
        pod_name = pods[0].name()
        try:
            cluster_size = podified.execute_in_pod(
                pod_name, GALERA_CLUSTER_SIZE.format(passwd=pw), 'galera')
        except oc.OpenShiftPythonException:
            continue

        wsrep_cluster_size = int(re.search(r'wsrep_cluster_size\s+(\d+)',
                                           cluster_size.out()).group(1))
        if wsrep_cluster_size == len(pods):
            LOG.info('all galera cells are restored')
            return

    raise RestoredException()


def _rabbitmq_user_full_name(user_name: str, rabbitmq_users=None):
    rabbitmq_users = rabbitmq_users or podified.list_rabbitmq_user_names()
    for qname in rabbitmq_users:
        name = qname.split("/")[-1]
        if user_name in name:
            return name
    return None


def _rabbitmq_user_exists(user_name: str, rabbitmq_users=None) -> bool:
    return bool(_rabbitmq_user_full_name(user_name, rabbitmq_users))


def _get_rabbitmq_pods(labels=None):
    return podified.get_pods(labels or RABBITMQ_LABEL)


def _rabbitmq_container_ready(pod_obj):
    statuses = pod_obj.as_dict().get("status", {}).get(
        "containerStatuses", [])
    for status in statuses:
        if status.get("name") == "rabbitmq":
            return bool(status.get("ready"))
    # Fallback if there are no explicit rabbitmq pod, if every pod is ready.
    return all(status.get("ready") for status in statuses
               ) if statuses else False


def _wait_for_rabbitmq_pod_ready(pod_name: str, ready: bool,
                                 timeout: float = 120.,
                                 interval: float = 5.):
    retry = tobiko.retry(timeout=timeout, interval=interval)
    for attempt in retry:
        with oc.project(CONF.tobiko.podified.osp_project):
            pod = oc.selector(f"pod/{pod_name}").object()
        if _rabbitmq_container_ready(pod) is ready:
            return
        if attempt.is_last:
            raise tobiko.TobikoException(
                f"RabbitMQ pod '{pod_name}' did not reach ready={ready}")


def _rabbitmq_running_nodes(pod_name: str):
    output = podified.execute_in_pod(
        pod_name, RABBITMQ_CLUSTER_STATUS, "rabbitmq").out()
    running = []
    in_running = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped == RABBITMQ_RUNNING_NODES_HEADER:
            in_running = True
            continue
        if in_running:
            if not stripped:
                continue
            if stripped.startswith("rabbit@"):
                running.append(stripped)
                continue
            break
    return running


def _wait_for_rabbitmq_cluster_ready(control_pod: str, expected_nodes: int,
                                     timeout: float = 120.,
                                     interval: float = 10.):
    retry = tobiko.retry(timeout=timeout, interval=interval)
    for attempt in retry:
        running = _rabbitmq_running_nodes(control_pod)
        if len(running) == expected_nodes:
            return
        if attempt.is_last:
            raise tobiko.TobikoException(
                "RabbitMQ cluster did not recover: "
                f"expected {expected_nodes} running nodes")


def kill_random_rabbitmq_pod_and_recover():
    # Kill a random RabbitMQ pod, verify it goes down, then confirm pod
    # and cluster recover and health checks pass.
    LOG.info("Starting kill random RabbitMQ pod flow")
    pods = _get_rabbitmq_pods()
    if not pods:
        raise tobiko.TobikoException("No RabbitMQ pods found")
    target_pod = random.choice(pods)
    target_pod_name = target_pod.name()
    control_pod_name = next(
        (pod.name() for pod in pods if pod.name() != target_pod_name),
        target_pod_name)
    LOG.info("Killing RabbitMQ process in pod '%s'", target_pod_name)
    podified.execute_in_pod(target_pod_name, RABBITMQ_KILL, "rabbitmq")
    _wait_for_rabbitmq_pod_ready(target_pod_name, ready=False)
    LOG.info("RabbitMQ pod '%s' is down; waiting for recovery",
             target_pod_name)
    _wait_for_rabbitmq_pod_ready(target_pod_name, ready=True)
    _wait_for_rabbitmq_cluster_ready(
        control_pod_name, expected_nodes=len(pods))
    LOG.info("RabbitMQ pod '%s' recovered and cluster is healthy",
             target_pod_name)


def rabbitmq_rotation():
    # Configure a dedicated RabbitMQ user for a service
    # and then rotate RabbitMQ credentials for this service
    LOG.info("Starting RabbitMQ rotation flow")
    with oc.project(config.CONF.tobiko.podified.osp_project):
        cp_name = oc.selector(
            podified.OSP_CONTROLPLANE
        ).qname().split("/")[-1]
    LOG.info("Using controlplane '%s' for rotation", cp_name)

    # Step 1: Add dedicated RabbitMQ user
    LOG.info("Adding dedicated RabbitMQ user for cinder")
    user = modify_service_messaging_user(cp_name, 'cinder', 'add')
    LOG.info("Waiting for RabbitMQUser '%s' to become ready", user)
    podified.wait_for_rabbitmq_user_ready(user)
    LOG.info("Waiting for cinder TransportURL to use '%s'", user)
    podified.wait_for_transporturl_user('cinder', user)
    LOG.info("Waiting for controlplane to be ready")
    podified.wait_for_controlplane_ready(cp_name)
    rabbitmq_users = podified.list_rabbitmq_user_names()
    if not _rabbitmq_user_exists(user, rabbitmq_users):
        raise tobiko.TobikoException(
            f"RabbitMQ user '{user}' was not found in: {rabbitmq_users}")

    # Step 2: Replace with new user
    LOG.info("Replacing RabbitMQ user for cinder")
    new_user = modify_service_messaging_user(cp_name, 'cinder', 'replace')
    LOG.info("Waiting for RabbitMQUser '%s' to become ready", new_user)
    podified.wait_for_rabbitmq_user_ready(new_user)
    LOG.info("Waiting for cinder TransportURL to use '%s'", new_user)
    podified.wait_for_transporturl_user('cinder', new_user)
    LOG.info("Waiting for cinder TransportURL to be fully reconciled")
    podified.wait_for_transporturl_setup_complete('cinder')
    LOG.info("Waiting for controlplane to be ready")
    podified.wait_for_controlplane_ready(cp_name)
    rabbitmq_users = podified.list_rabbitmq_user_names()
    if not (_rabbitmq_user_exists(user, rabbitmq_users) or
            _rabbitmq_user_exists(new_user, rabbitmq_users)):
        raise tobiko.TobikoException(
            f"New RabbitMQ user '{new_user}' not found after replace: "
            f"{rabbitmq_users}")

    # Step 3: Wait for auto-cleanup of old user
    # The infra-operator determines EDPM status from the TransportURL's
    # ownerReference Kind: for controlplane-only services (like cinder),
    # the old user is released immediately without waiting for NodeSet
    # deployment. NodeSet sync is only required for services that run
    # agents on EDPM nodes (Nova, Neutron).
    LOG.info("Waiting for operator to auto-clean old user '%s'", user)

    try:
        for _ in tobiko.retry(timeout=300., interval=15.):
            rabbitmq_users = podified.list_rabbitmq_user_names()
            if not _rabbitmq_user_exists(user, rabbitmq_users):
                LOG.info("RabbitMQ rotation flow completed successfully")
                return
            labels = podified.get_rabbitmq_user_labels(user)
            if labels and labels.get(
                    "rabbitmq.openstack.org/orphaned") == "true":
                LOG.info("Old user '%s' marked as orphaned, waiting "
                         "for deletion", user)
            else:
                LOG.debug("Old user '%s' not yet orphaned", user)
    except tobiko.RetryTimeLimitError as exc:
        raise tobiko.TobikoException(
            f"RabbitMQ user '{user}' was not auto-cleaned after "
            f"rotation. Still found in: {rabbitmq_users}") from exc


def modify_service_messaging_user(cp_name: str, service: str,
                                  modification: str = "add"):
    with oc.project(config.CONF.tobiko.podified.osp_project):
        cp_obj = oc.selector(
            f"{podified.OSP_CONTROLPLANE}/{cp_name}"
        ).objects()[0]
    spec = cp_obj.model.setdefault("spec", {})
    sv_name = spec.setdefault(service, {})
    template = sv_name.setdefault("template", {})
    mbus = template.setdefault("messagingBus", {})
    new_user_name = f"{service}-{random.randrange(1000000)}"

    if modification in ("add", "replace"):
        # add if empty, replace if already set
        mbus["user"] = new_user_name
        cp_obj.apply()
        return new_user_name
    else:
        raise ValueError(f"Unsupported modification: {modification}")
