# Copyright 2022 Red Hat
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

import dbm
import os
import shelve

from oslo_log import log

import tobiko
from tobiko.common import _lockutils


LOG = log.getLogger(__name__)
TEST_RUN_SHELF = 'test_run'


def get_shelves_dir():
    # ensure the directory exists
    from tobiko import config
    shelves_dir = os.path.expanduser(config.CONF.tobiko.common.shelves_dir)
    return shelves_dir


def get_shelf_path(shelf):
    return os.path.join(get_shelves_dir(), shelf)


@_lockutils.interworker_synched('shelves')
def addme_to_shared_resource(shelf, resource):
    shelf_path = get_shelf_path(shelf)
    # this is needed for unit tests
    resource = str(resource)
    testcase_id = tobiko.get_test_case().id()
    for attempt in tobiko.retry(timeout=10.0,
                                interval=0.5):
        try:
            with shelve.open(shelf_path) as db:
                if db.get(resource) is None:
                    db[resource] = set()
                # the add and remove methods do not work directly on the db
                auxset = db[resource]
                auxset.add(testcase_id)
                db[resource] = auxset
                return db[resource]
        except dbm.error:
            LOG.exception(f"Error accessing shelf {shelf}")
            if attempt.is_last:
                raise


@_lockutils.interworker_synched('shelves')
def removeme_from_shared_resource(shelf, resource):
    shelf_path = get_shelf_path(shelf)
    # this is needed for unit tests
    resource = str(resource)
    testcase_id = tobiko.get_test_case().id()
    for attempt in tobiko.retry(timeout=10.0,
                                interval=0.5):
        try:
            with shelve.open(shelf_path) as db:
                # the add and remove methods do not work directly on the db
                db[resource] = db.get(resource) or set()
                if testcase_id in db[resource]:
                    auxset = db[resource]
                    auxset.remove(testcase_id)
                    db[resource] = auxset
                return db[resource]
        except dbm.error:
            LOG.exception(f"Error accessing shelf {shelf}")
            if attempt.is_last:
                raise


def remove_test_from_shelf_resources(testcase_id, shelf):
    shelf_path = get_shelf_path(shelf)
    for attempt in tobiko.retry(timeout=10.0,
                                interval=0.5):
        try:
            with shelve.open(shelf_path) as db:
                if not db:
                    return
                for resource in db.keys():
                    if testcase_id in db[resource]:
                        auxset = db[resource]
                        auxset.remove(testcase_id)
                        db[resource] = auxset
                return db
        except dbm.error as err:
            LOG.exception(f"Error accessing shelf {shelf}")
            if "db type could not be determined" in str(err):
                # remove the filename extension, which depends on the specific
                # DBM implementation
                shelf_path = '.'.join(shelf_path.split('.')[:-1])
            if attempt.is_last:
                raise


@_lockutils.interworker_synched('shelves')
def remove_test_from_all_shared_resources(testcase_id):
    LOG.debug(f'Removing test {testcase_id} from all shelf resources')
    shelves_dir = get_shelves_dir()
    for filename in os.listdir(shelves_dir):
        if TEST_RUN_SHELF not in filename:
            remove_test_from_shelf_resources(testcase_id, filename)


@_lockutils.interworker_synched('shelves')
def initialize_shelves():
    shelves_dir = get_shelves_dir()
    shelf_path = os.path.join(shelves_dir, TEST_RUN_SHELF)
    id_key = 'PYTEST_XDIST_TESTRUNUID'
    test_run_uid = os.environ.get(id_key)

    tobiko.makedirs(shelves_dir)

    # if no PYTEST_XDIST_TESTRUNUID ->
    #     pytest was executed with only one worker
    # if tobiko.initialize_shelves() == True ->
    #    this is the first pytest worker running cleanup_shelves
    # then, cleanup the shelves directory
    # else, another worker did it before
    for attempt in tobiko.retry(timeout=15.0,
                                interval=0.5):
        try:
            with shelve.open(shelf_path) as db:
                if test_run_uid is None:
                    LOG.debug("Only one pytest worker - Initializing shelves")
                elif test_run_uid == db.get(id_key):
                    LOG.debug("Another pytest worker already initialized "
                              "the shelves")
                    return
                else:
                    LOG.debug("Initializing shelves for the "
                              "test run uid %s", test_run_uid)
                    db[id_key] = test_run_uid
                for filename in os.listdir(shelves_dir):
                    if TEST_RUN_SHELF not in filename:
                        file_path = os.path.join(shelves_dir, filename)
                        os.unlink(file_path)
                return
        except dbm.error:
            LOG.exception(f"Error accessing shelf {TEST_RUN_SHELF}")
            if attempt.is_last:
                raise
