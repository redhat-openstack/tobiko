# Copyright (c) 2024 Red Hat, Inc.
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

import contextlib
import functools
import os

from oslo_concurrency import lockutils
from oslo_log import log
from oslo_utils import reflection
from oslo_utils import timeutils


LOG = log.getLogger(__name__)


def interworker_synched(name):
    """Re-definition of oslo_concurrency.lockutils.synchronized.

    Tobiko needs to re-difine this decorator in order to avoid intra-
    process/worker locks. This is because tobiko is executed in multiple
    processes (using pytest), but each process only runs one thread.

    The intra-process lock should not be applied in tobiko because some of the
    locked methods could be called recurrently.
    Example:
    The creation (setup_fixture) of CirrosPeerServerStackFixture depends on the
    creation of CirrosServerStackFixture, which is also its parent class.
    With intra-process locks, the creation of CirrosServerStackFixture could
    not be started (would be locked by the creation of
    CirrosPeerServerStackFixture).
    """

    def wrap(f):

        @functools.wraps(f)
        def inner(*args, **kwargs):
            t1 = timeutils.now()
            t2 = None
            gotten = True
            f_name = reflection.get_callable_name(f)
            try:
                with lock(name):
                    t2 = timeutils.now()
                    LOG.debug('Lock "%(name)s" acquired by "%(function)s" :: '
                              'waited %(wait_secs)0.3fs',
                              {'name': name,
                               'function': f_name,
                               'wait_secs': (t2 - t1)})
                    return f(*args, **kwargs)
            except lockutils.AcquireLockFailedException:
                gotten = False
            finally:
                t3 = timeutils.now()
                if t2 is None:
                    held_secs = "N/A"
                else:
                    held_secs = "%0.3fs" % (t3 - t2)
                LOG.debug('Lock "%(name)s" "%(gotten)s" by "%(function)s" ::'
                          ' held %(held_secs)s',
                          {'name': name,
                           'gotten': 'released' if gotten else 'unacquired',
                           'function': f_name,
                           'held_secs': held_secs})
        return inner

    return wrap


@contextlib.contextmanager
def lock(name):
    """Re-definition of oslo_concurrency.lockutils.lock that does not apply
    intra-worker locks. Only inter-worker locks are applied.
    """
    from tobiko import config
    lock_path = os.path.expanduser(config.CONF.tobiko.common.lock_dir)

    LOG.debug('Acquired lock "%(lock)s"', {'lock': name})

    try:
        ext_lock = lockutils.external_lock(name,
                                           lock_file_prefix='tobiko',
                                           lock_path=lock_path)
        gotten = ext_lock.acquire(delay=0.01, blocking=True)
        if not gotten:
            raise lockutils.AcquireLockFailedException(name)
        LOG.debug('Acquired external semaphore "%(lock)s"',
                  {'lock': name})
        try:
            yield ext_lock
        finally:
            ext_lock.release()
    finally:
        LOG.debug('Releasing lock "%(lock)s"', {'lock': name})
