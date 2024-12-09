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

kill_galera = 'kill -9 $(pidof mysqld)'
rm_grastate = 'rm -rf /var/lib/mysql/grastate.dat'
galera_cluster_size = 'mysql -u root --password={passwd} -e \'SHOW STATUS ' \
                      'LIKE "wsrep_cluster_size"\''
check_bootstrap = """
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
            random_pod_name, check_bootstrap, 'galera').out().strip()
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
    podified.execute_in_pod(pod_name, rm_grastate, 'galera')
    LOG.info(f'grastate.dat removed from {pod_name}')


def kill_all_galera_pods(galera_pods):
    for pod in galera_pods:
        podified.execute_in_pod(pod.name(), kill_galera, 'galera')
        LOG.info(f'kill galera pod {pod}')


def check_all_galera_cells_down(pod_name):
    pw = keystone.keystone_credentials().password

    retry = tobiko.retry(timeout=30, interval=5)
    for _ in retry:
        try:
            cluster_size = podified.execute_in_pod(
                pod_name, galera_cluster_size.format(passwd=pw), 'galera')
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

    retry = tobiko.retry(timeout=60, interval=10)
    for _ in retry:
        pod_name = pods[0].name()
        try:
            cluster_size = podified.execute_in_pod(
                pod_name, galera_cluster_size.format(passwd=pw), 'galera')
        except oc.OpenShiftPythonException:
            continue

        wsrep_cluster_size = int(re.search(r'wsrep_cluster_size\s+(\d+)',
                                           cluster_size.out()).group(1))
        if wsrep_cluster_size == len(pods):
            LOG.info('all galera cells are restored')
            return

    raise RestoredException()
