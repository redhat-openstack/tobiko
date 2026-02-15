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
        # gcomm:// without args means that bootstrap is done from this node
        bootstrap = podified.execute_in_pod(
            random_pod_name, CHECK_BOOTSTRAP, 'galera').out().strip()
        if len(pods) > 1:
            if re.search(r'wsrep-cluster-address=gcomm://(?:\s|$)', bootstrap
                         ) is None:
                raise GaleraBoostrapException()
        elif re.search(r'wsrep-cluster-address=gcomm://', bootstrap) is None:
            raise GaleraBoostrapException()
        lastDate = re.findall(r"\w{,3}\s*\w{,3}\s*\d{,2}\s*\d{,2}:\d{,2}"
                              r":\d{,2}\s*\d{4}", bootstrap)[-1]
        LOG.info(f'last boostrap required at {lastDate}')


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


def rabbitmq_rotation():
    # Configure a dedicated RabbitMQ user for a service
    # and then rotate RabbitMQ credentials for this service
    LOG.info("Starting RabbitMQ rotation flow")
    with oc.project(config.CONF.tobiko.podified.osp_project):
        cp_name = oc.selector(
            podified.OSP_CONTROLPLANE
        ).qname().split("/")[-1]
    LOG.info("Using controlplane '%s' for rotation", cp_name)
    LOG.info("Adding dedicated RabbitMQ user for cinder")
    user = modify_service_messaging_user(cp_name, 'cinder', 'add')
    podified.wait_for_controlplane_ready(cp_name)
    rabbitmq_users = podified.list_rabbitmq_user_names()
    if not _rabbitmq_user_exists(user, rabbitmq_users):
        raise tobiko.TobikoException(
            f"RabbitMQ user '{user}' was not found in: {rabbitmq_users}")
    LOG.info("Replacing RabbitMQ user for cinder")
    new_user = modify_service_messaging_user(cp_name, 'cinder', 'replace')
    podified.wait_for_controlplane_ready(cp_name)
    rabbitmq_users = podified.list_rabbitmq_user_names()
    if not (_rabbitmq_user_exists(user, rabbitmq_users) or
            _rabbitmq_user_exists(new_user, rabbitmq_users)):
        raise tobiko.TobikoException(
            "RabbitMQ users not found after replace: "
            f"expected '{user}' or '{new_user}' in {rabbitmq_users}")
    LOG.info("Removing safeguard finalizer for old user '%s'", user)
    remove_rabbitmq_user_safeguard(user)
    podified.wait_for_controlplane_ready(cp_name)
    try:
        for _ in tobiko.retry(timeout=100., interval=10.):
            rabbitmq_users = podified.list_rabbitmq_user_names()
            if not _rabbitmq_user_exists(user, rabbitmq_users):
                LOG.info("RabbitMQ rotation flow completed successfully")
                return
    except tobiko.RetryTimeLimitError as exc:
        raise tobiko.TobikoException(
            f"RabbitMQ user '{user}' was still found in: "
            f"{rabbitmq_users} after safeguard deletion") from exc


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


def remove_rabbitmq_user_safeguard(user_name: str):
    with oc.project(CONF.tobiko.podified.osp_project):
        qnames = oc.selector("rabbitmquser").qnames()
        full_name = _rabbitmq_user_full_name(user_name, qnames)
        if not full_name:
            raise tobiko.TobikoException(
                f"RabbitMQ user '{user_name}' not found in: {qnames}")
        rabbitmq_user = oc.selector(
            f"rabbitmquser/{full_name}"
        ).object()
        finalizers = rabbitmq_user.as_dict().get(
            "metadata", {}).get("finalizers", [])
        if "rabbitmq.openstack.org/cleanup-blocked" not in finalizers:
            return
        new_finalizers = [
            finalizer for finalizer in finalizers
            if finalizer != "rabbitmq.openstack.org/cleanup-blocked"
        ]
        patch = [{
            "op": "replace",
            "path": "/metadata/finalizers",
            "value": new_finalizers
        }]
        rabbitmq_user.patch(patch, "json")
