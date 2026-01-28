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
import sqlite3

from oslo_log import log

import tobiko
from tobiko.common import _lockutils


LOG = log.getLogger(__name__)
TEST_RUN_SHELF = 'test_run'

# dbm.error is a tuple of exception classes from available DBM backends.
# We need to combine it with sqlite3.DatabaseError for Python 3.13+ where
# the default shelve backend is dbm.sqlite3. Using tuple concatenation
# ensures a flat tuple that Python's exception handling can process.
SHELVE_ERRORS = dbm.error + (sqlite3.DatabaseError,)


def get_shelves_dir():
    # ensure the directory exists
    from tobiko import config
    shelves_dir = os.path.expanduser(config.CONF.tobiko.common.shelves_dir)
    return shelves_dir


def get_shelf_path(shelf):
    return os.path.join(get_shelves_dir(), shelf)


@_lockutils.interworker_synched('shelves')
def addme_to_shared_resource(shelf, resource):
    shelves_dir = get_shelves_dir()
    tobiko.makedirs(shelves_dir)
    shelf_path = os.path.join(shelves_dir, shelf)
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
    shelves_dir = get_shelves_dir()
    tobiko.makedirs(shelves_dir)
    shelf_path = os.path.join(shelves_dir, shelf)
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
        except FileNotFoundError:
            # File was deleted between os.listdir() and shelve.open()
            # This can happen due to race conditions with parallel workers
            LOG.debug(f"Shelf file not found (likely deleted): {shelf_path}")
            return
        except SHELVE_ERRORS as err:
            # sqlite3.DatabaseError is raised when the file has SQLite magic
            # bytes but is corrupted or not a valid database. This is NOT a
            # subclass of dbm.error, so we need to catch it separately.
            err_str = str(err)
            LOG.debug(f"Error accessing shelf {shelf}: {err_str}")

            if "db type could not be determined" in err_str:
                # The file might have an extension from a different DBM
                # implementation. Try removing the extension.
                if '.' in os.path.basename(shelf_path):
                    shelf_path = '.'.join(shelf_path.split('.')[:-1])
                    LOG.debug(f"Retrying with path: {shelf_path}")
                    continue

            if attempt.is_last:
                # Log at warning level on final failure, but don't raise
                # to avoid failing tests due to shelf cleanup issues
                LOG.warning(f"Failed to clean shelf {shelf} after retries: "
                            f"{err_str}")
                return


@_lockutils.interworker_synched('shelves')
def remove_test_from_all_shared_resources(testcase_id):
    LOG.debug(f'Removing test {testcase_id} from all shelf resources')
    shelves_dir = get_shelves_dir()

    # Gracefully handle case where shelves directory doesn't exist yet
    if not os.path.isdir(shelves_dir):
        LOG.debug(f'Shelves directory does not exist: {shelves_dir}')
        return

    for filename in os.listdir(shelves_dir):
        # Skip test run shelf and SQLite auxiliary files
        # (-shm, -wal for WAL mode, -journal for rollback journal mode)
        if (TEST_RUN_SHELF not in filename and
                not filename.endswith(('-shm', '-wal', '-journal'))):
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
