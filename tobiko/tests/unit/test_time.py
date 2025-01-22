# Copyright 2020 Red Hat
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

from unittest import mock

import tobiko
from tobiko.tests import unit


class TimeTest(unit.TobikoUnitTest):

    def test_time(self):
        mock_time = self.patch_time()
        initial_time = mock_time.current_time

        self.assertEqual(mock_time.current_time, tobiko.time())
        self.assertEqual(mock_time.current_time, tobiko.time())
        self.assertEqual(mock_time.current_time, tobiko.time())

        final_time = mock_time.current_time
        self.assertEqual(3 * mock_time.time_increment,
                         final_time - initial_time)
        mock_time.time.assert_has_calls([mock.call()] * 3, any_order=True)

    def test_sleep_with_float(self):
        self._test_sleep(20.)

    def test_sleep_with_int(self):
        self._test_sleep(10)

    def test_sleep_with_str(self):
        self._test_sleep('5.')

    def test_sleep_with_bytes(self):
        self._test_sleep(b"15")

    def test_sleep_with_zero(self):
        self._test_sleep(0.)

    def test_sleep_with_inf(self):
        self._test_sleep(float('inf'))

    def test_sleep_with_negative(self):
        self._test_sleep(-1.)

    def test_sleep_with_none(self):
        self._test_sleep(None)

    def _test_sleep(self, seconds: tobiko.Seconds):
        mock_time = self.patch_time()
        initial_time = mock_time.current_time

        tobiko.sleep(seconds)

        expected = seconds and max(0., float(seconds)) or 0.
        final_time = mock_time.current_time
        mock_time.sleep.assert_called_once_with(expected)
        self.assertEqual(expected, final_time - initial_time)

    def test_to_seconds_with_float(self):
        self._test_to_seconds(20.)

    def test_to_seconds_with_int(self):
        self._test_to_seconds(20)

    def test_to_seconds_with_str(self):
        self._test_to_seconds("5")

    def test_to_seconds_with_bytes(self):
        self._test_to_seconds(b"15")

    def test_to_seconds_with_zero(self):
        self._test_to_seconds(0.)

    def test_to_seconds_with_inf(self):
        self._test_to_seconds(float('inf'))

    def test_to_seconds_with_negative(self):
        self._test_to_seconds(-1.)

    def test_to_seconds_with_none(self):
        self._test_to_seconds(None)

    def _test_to_seconds(self, seconds: tobiko.Seconds):
        result = tobiko.to_seconds(seconds)
        if seconds is None:
            self.assertIsNone(result)
        else:
            self.assertEqual(max(0., float(seconds)), result)

    def test_to_seconds_float_with_float(self):
        self._test_to_seconds_float(20.)

    def test_to_seconds_float_with_int(self):
        self._test_to_seconds_float(20)

    def test_to_seconds_float_with_str(self):
        self._test_to_seconds_float("5")

    def test_to_seconds_float_with_bytes(self):
        self._test_to_seconds_float(b"15")

    def test_to_seconds_float_with_zero(self):
        self._test_to_seconds_float(0.)

    def test_to_seconds_float_with_inf(self):
        self._test_to_seconds_float(float('inf'))

    def test_to_seconds_float_with_negative(self):
        self._test_to_seconds_float(-1.)

    def test_to_seconds_float_with_none(self):
        self._test_to_seconds_float(None)

    def _test_to_seconds_float(self, seconds: tobiko.Seconds):
        result = tobiko.to_seconds_float(seconds)
        expected = seconds and max(0., float(seconds)) or 0.
        self.assertEqual(expected, result)

    def test_true_seconds(self):
        self.assertEqual([], tobiko.true_seconds())
        self.assertEqual([], tobiko.true_seconds(None))
        self.assertEqual([], tobiko.true_seconds(None, None))
        self.assertEqual([1., 2., 3., 4.],
                         tobiko.true_seconds(None, 1, None, 2., '3', None, 4,
                                             None))

    def test_min_seconds(self):
        self.assertIsNone(tobiko.min_seconds())
        self.assertIsNone(tobiko.min_seconds(None))
        self.assertIsNone(tobiko.min_seconds(None, None))
        self.assertEqual(1.5, tobiko.min_seconds(3, 2., '1.5'))

    def test_max_seconds(self):
        self.assertIsNone(tobiko.max_seconds())
        self.assertIsNone(tobiko.max_seconds(None))
        self.assertIsNone(tobiko.max_seconds(None, None))
        self.assertEqual(3., tobiko.max_seconds(2., 3, '1.5'))
