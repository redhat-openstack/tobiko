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

import re
import time

import openshift_client as oc
from oslo_log import log

import tobiko
from tobiko import config
from tobiko import podified
# from tobiko.openstack import glance
# from tobiko.openstack import keystone
# from tobiko.openstack import neutron
# from tobiko.openstack import stacks
# from tobiko.openstack import tests
# from tobiko.openstack import topology
# from tobiko.tests.faults.ha import test_cloud_recovery
# from tobiko.shell import ping
# from tobiko.shell import sh

CONF = config.CONF
LOG = log.getLogger(__name__)


@podified.skip_if_not_podified
def kill_all_galera_services():
    """kill all galera processes,
    check in pacemaker it is down"""
    galera_pods_num = sum(
        1 for node_name in oc.selector('nodes').qnames()
        for pod_obj in oc.get_pods_by_node(node_name)
        if 'cell1-galera' in pod_obj.fqname()
    )
    for i in range(galera_pods_num):
        oc.selector('pod/openstack-cell1-galera-{}'.format(i)).object()\
            .execute(['sh', '-c', 'kill -9 $(pidof mysqld)'],
                     container_name='galera')
        LOG.info('kill galera cell-{}'.format(i))

    retry = tobiko.retry(timeout=30, interval=5)
    for _ in retry:
        try:
            # checks wsrep cluster size is now unavailable
            result = oc.selector('pod/openstack-cell1-galera-0').object(
            ).execute(['sh', '-c', """mysql -u root --password=12345678
            -e 'SHOW STATUS LIKE "wsrep_cluster_size"'"""])
            # Capture and filter the error output
            error_output = result.err()
            non_error_message = """
            Defaulted container "galera" out of: galera,
            mysql-bootstrap (init)\n"""
            filtered_err_output = error_output.replace(non_error_message, '')
            if not filtered_err_output.strip():
                continue
        except oc.OpenShiftPythonException:
            LOG.info('all galera cells down')
            break
    time.sleep(60)
    for _ in retry:
        try:
            if int(re.search(r'wsrep_cluster_size\s+(\d+)', oc.selector(
                    'pod/openstack-cell1-galera-0').object().execute(
                ['sh', '-c', """mysql -u root --password=12345678 -e 'SHOW
                STATUS LIKE "wsrep_cluster_size"'"""], container_name='galera'
            ).out()).group(1)) == galera_pods_num:
                LOG.info('all galera cells are restored')
                return
        except oc.OpenShiftPythonException:
            continue
        return False


@podified.skip_if_not_podified
def remove_all_grastate_galera():
    """shut down galera properly,
    remove all grastate"""
    galera_pods_num = sum(
        1 for node_name in oc.selector('nodes').qnames()
        for pod_obj in oc.get_pods_by_node(node_name)
        if 'cell1-galera' in pod_obj.fqname()
    )
    for i in range(galera_pods_num):
        oc.selector('pod/openstack-cell1-galera-{}'.format(i)).object()\
            .execute(['sh', '-c', 'rm -rf /var/lib/mysql/grastate.dat '],
                     container_name='galera')
        LOG.info('delete grastate.dat cell-{}'.format(i))
    for i in range(galera_pods_num):
        oc.selector('pod/openstack-cell1-galera-{}'.format(i)).object()\
            .execute(['sh', '-c', 'kill -9 $(pidof mysqld)'],
                     container_name='galera')
        LOG.info('kill galera cell-{}'.format(i))
    retry = tobiko.retry(timeout=30, interval=5)
    for _ in retry:
        try:
            # checks wsrep cluster size is now unavailable
            result = oc.selector('pod/openstack-cell1-galera-0').object(
            ).execute(['sh', '-c', """mysql -u root --password=12345678
            -e 'SHOW STATUS LIKE "wsrep_cluster_size"'"""])
            # Capture and filter the error output
            error_output = result.err()
            non_error_message = """
            Defaulted container "galera" out of: galera,
            mysql-bootstrap (init)\n"""
            filtered_err_output = error_output.replace(non_error_message, '')
            if not filtered_err_output.strip():
                continue
        except oc.OpenShiftPythonException:
            LOG.info('all galera cells down')
            break
    time.sleep(60)
    for _ in retry:
        try:
            if int(re.search(r'wsrep_cluster_size\s+(\d+)', oc.selector(
                    'pod/openstack-cell1-galera-0').object().execute(
                ['sh', '-c', """mysql -u root --password=12345678 -e 'SHOW
                STATUS LIKE "wsrep_cluster_size"'"""], container_name='galera'
            ).out()).group(1)) == galera_pods_num:
                LOG.info('all galera cells are restored')
                return
        except oc.OpenShiftPythonException:
            continue
        return False
