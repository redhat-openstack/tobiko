# Copyright 2019 Red Hat
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

import time
from unittest import mock

import tobiko
from tobiko import common


class PatchMixin(object):
    """Mixin class with mock method helpers"""

    def patch(self, obj, attribute, value=mock.DEFAULT, spec=None,
              create=False, spec_set=None, autospec=None,
              new_callable=None, **kwargs):
        # pylint: disable=arguments-differ
        context = mock.patch.object(target=obj, attribute=attribute, new=value,
                                    spec=spec, create=create,
                                    spec_set=spec_set, autospec=autospec,
                                    new_callable=new_callable, **kwargs)
        mocked = context.start()
        self.addCleanup(context.stop)
        return mocked

    def patch_time(self, current_time=None, time_increment=None):
        if not hasattr(self, 'mock_time'):
            self.mock_time = PatchTimeFixture(current_time=current_time,
                                              time_increment=time_increment)
        else:
            self.mock_time.patch_time(current_time=current_time,
                                      time_increment=time_increment)
        return self.useFixture(self.mock_time)


class PatchFixture(PatchMixin, tobiko.SharedFixture):
    """Fixture class with mock method helpers"""


class PatchTimeFixture(PatchFixture):

    start_time = 0.
    current_time = 0.
    time_increment = 1.

    def __init__(self, current_time=None, time_increment=.1):
        self.time = mock.MagicMock(specs=time.time, side_effect=self._time)
        self.sleep = mock.MagicMock(specs=time.sleep, side_effect=self._sleep)
        self.patch_time(current_time=current_time,
                        time_increment=time_increment)

    def setup_fixture(self):
        # pylint: disable=protected-access
        self.patch(common._time, '_time', self)

    def _time(self):
        result = self.current_time
        self.current_time += self.time_increment
        return result

    def _sleep(self, seconds):
        self.current_time += seconds

    def patch_time(self, current_time=0., time_increment=.1):
        if current_time is not None:
            self.start_time = self.current_time = current_time
        if time_increment is not None:
            self.time_increment = time_increment
