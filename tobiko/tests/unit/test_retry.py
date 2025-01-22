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

import itertools
from unittest import mock

import testtools

import tobiko
from tobiko.tests import unit


class RetryTest(unit.TobikoUnitTest):

    def test_retry_when_succeed(self,):
        mock_time = self.patch_time()
        attempts = []

        for attempt in tobiko.retry():
            attempts.append(attempt)
            break  # this marks a success

        expected = [tobiko.retry_attempt(number=1,
                                         start_time=mock_time.start_time,
                                         elapsed_time=0.)]
        self.assertEqual(expected, attempts)
        mock_time.sleep.assert_not_called()

    def test_retry_untill_succeed(self):
        mock_time = self.patch_time()
        attempts = []

        for attempt in tobiko.retry():
            attempts.append(attempt)
            if attempt.number >= 3:
                break

        time_increment = mock_time.time_increment
        expected = [tobiko.retry_attempt(number=i+1,
                                         start_time=mock_time.start_time,
                                         elapsed_time=i * time_increment)
                    for i in range(3)]
        self.assertEqual(expected, attempts)
        mock_time.sleep.assert_not_called()

    def test_retry_with_count(self):
        mock_time = self.patch_time()
        attempts = []

        try:
            for attempt in tobiko.retry(count=2):
                attempts.append(attempt)
        except tobiko.RetryCountLimitError as ex:
            self.assertEqual("Retry count limit exceeded "
                             f"({attempt.details})", str(ex))
        else:
            self.fail("RetryCountLimitError not raised")

        time_increment = mock_time.time_increment
        expected = [tobiko.retry_attempt(number=i+1,
                                         count=2,
                                         start_time=mock_time.start_time,
                                         elapsed_time=i * time_increment)
                    for i in range(2)]
        self.assertEqual(expected, attempts)
        mock_time.sleep.assert_not_called()

    def test_retry_with_timeout(self):
        mock_time = self.patch_time()
        attempts = []

        try:
            for attempt in tobiko.retry(timeout=2.5):
                attempts.append(attempt)
        except tobiko.RetryTimeLimitError as ex:
            self.assertEqual("Retry time limit exceeded "
                             f"({attempt.details})", str(ex))
        else:
            self.fail("RetryTimeLimitError not raised")

        time_increment = mock_time.time_increment
        expected = [tobiko.retry_attempt(number=i+1,
                                         timeout=2.5,
                                         start_time=mock_time.start_time,
                                         elapsed_time=i * time_increment)
                    for i in range(4)]
        self.assertEqual(expected, attempts)
        mock_time.sleep.assert_not_called()

    def test_retry_with_interval(self):
        mock_time = self.patch_time()
        attempts = []

        for attempt in tobiko.retry(interval=5.):
            attempts.append(attempt)
            if attempt.number >= 3:
                break

        expected = [tobiko.retry_attempt(number=i+1,
                                         interval=5.,
                                         start_time=mock_time.start_time,
                                         elapsed_time=elapsed_time)
                    for i, elapsed_time in enumerate([0., 6., 11.])]
        self.assertEqual(expected, attempts)
        mock_time.sleep.assert_has_calls([mock.call(4.),
                                          mock.call(3.)])

    def test_retry_with_timeout_and_small_interval(self):
        mock_time = self.patch_time()
        attempts = []

        try:
            for attempt in tobiko.retry(timeout=2.5, interval=0.5):
                attempts.append(attempt)
        except tobiko.RetryTimeLimitError as ex:
            self.assertEqual("Retry time limit exceeded "
                             f"({attempt.details})", str(ex))
        else:
            self.fail("RetryTimeLimitError not raised")

        expected = [tobiko.retry_attempt(number=i+1,
                                         timeout=2.5,
                                         interval=0.5,
                                         start_time=mock_time.start_time,
                                         elapsed_time=elapsed_time)
                    for i, elapsed_time in enumerate([0., 1., 2., 3.])]
        self.assertEqual(expected, attempts)
        mock_time.sleep.assert_not_called()

    def test_retry_with_timeout_and_big_interval(self):
        mock_time = self.patch_time()
        attempts = []

        try:
            for attempt in tobiko.retry(timeout=9., interval=3.):
                attempts.append(attempt)
        except tobiko.RetryTimeLimitError as ex:
            self.assertEqual("Retry time limit exceeded "
                             f"({attempt.details})", str(ex))
        else:
            self.fail("RetryTimeLimitError not raised")

        expected = [tobiko.retry_attempt(number=i+1,
                                         timeout=9.,
                                         interval=3.,
                                         start_time=mock_time.start_time,
                                         elapsed_time=elapsed_time)
                    for i, elapsed_time in enumerate([0., 4., 7., 10.])]
        self.assertEqual(expected, attempts)
        mock_time.sleep.assert_has_calls([mock.call(2.),
                                          mock.call(1.),
                                          mock.call(1.)])

    def test_retry_on_exception_when_succeed(self):
        count_calls = itertools.count()

        @tobiko.retry_on_exception(ValueError)
        def func(a, b):
            next(count_calls)
            return a + b

        result = func(3, 4)
        self.assertEqual(1, next(count_calls))
        self.assertEqual(7, result)

    def test_retry_on_exception_when_fails(self):
        count_calls = itertools.count()

        @tobiko.retry_on_exception(ValueError)
        def func(a, b):
            next(count_calls)
            raise RuntimeError(f"{a + b}")

        ex = self.assertRaises(RuntimeError, func, 3, 4)
        self.assertEqual(1, next(count_calls))
        self.assertEqual('7', str(ex))

    def test_retry_on_exception_untill_succeed(self):
        count_calls = itertools.count()

        @tobiko.retry_on_exception(ValueError, TypeError)
        def func(a, b):
            count = next(count_calls)
            if count == 0:
                raise ValueError
            if count == 1:
                raise TypeError
            return a + b

        result = func(3, 4)
        self.assertEqual(3, next(count_calls))
        self.assertEqual(7, result)

    def test_retry_on_exception_with_count(self):
        count_calls = itertools.count()

        @tobiko.retry_on_exception(RuntimeError, count=3)
        def func(_a, _b):
            count = next(count_calls)
            raise RuntimeError(f"{count}")

        ex = self.assertRaises(RuntimeError, func, 3, 4)
        self.assertEqual(3, next(count_calls))
        self.assertEqual("2", str(ex))

    def test_retry_on_exception_with_timeout(self):
        mock_time = self.patch_time()
        count_calls = itertools.count()

        @tobiko.retry_on_exception(ValueError, timeout=3.)
        def func(_a, _b):
            count = next(count_calls)
            raise ValueError(f"{count}")

        ex = self.assertRaises(ValueError, func, 3, 4)
        self.assertEqual(4, next(count_calls))
        self.assertEqual("3", str(ex))
        self.assertEqual(4., mock_time.current_time)
        mock_time.sleep.assert_not_called()

    def test_retry_on_exception_with_interval(self):
        mock_time = self.patch_time()
        count_calls = itertools.count()

        @tobiko.retry_on_exception(ValueError, interval=5.)
        def func(a, b):
            count = next(count_calls)
            if count > 2:
                return a + b
            raise ValueError(f"{count}")

        result = func(3, 4)
        self.assertEqual(4, next(count_calls))
        self.assertEqual(7, result)
        self.assertEqual(17., mock_time.current_time)
        mock_time.sleep.assert_has_calls([mock.call(4.),
                                          mock.call(3.),
                                          mock.call(3.)])

    def test_retry_test_case_when_succeed(self):

        class MyTest(testtools.TestCase):

            @tobiko.retry_test_case()
            def test_success(self):
                pass

        result = testtools.TestResult()
        test_case = MyTest('test_success')
        test_case.run(result)

        self.assertEqual(1, result.testsRun)
        self.assertEqual([], result.failures)
        self.assertEqual([], result.errors)
        self.assertEqual({}, result.skip_reasons)

    def test_retry_test_case_when_fails(self):

        class MyTest(testtools.TestCase):

            @tobiko.retry_test_case()
            def test_failure(self):
                try:
                    self.fail("this is failing")
                except tobiko.FailureException as ex:
                    failures.append(ex)
                    raise

        failures = []
        result = testtools.TestResult()
        test_case = MyTest('test_failure')
        test_case.run(result)

        self.assertEqual(1, result.testsRun)
        self.assertEqual([], result.errors)
        self.assertEqual({}, result.skip_reasons)

        self.assertEqual(3, len(failures))
        self.assertEqual(1, len(result.failures))
        failed_test_case, traceback = result.failures[0]
        self.assertIs(test_case, failed_test_case)
        self.assertIn(str(failures[-1]), traceback)

    def test_retry_test_case_when_fails_once(self):

        class MyTest(testtools.TestCase):

            @tobiko.retry_test_case()
            def test_one_failure(self):
                count = next(count_calls)
                self.assertNotEqual(0, count)

        count_calls = itertools.count()
        result = testtools.TestResult()
        test_case = MyTest('test_one_failure')
        test_case.run(result)

        self.assertEqual(2, next(count_calls))
        self.assertEqual(1, result.testsRun)
        self.assertEqual([], result.failures)
        self.assertEqual([], result.errors)
        self.assertEqual({}, result.skip_reasons)

    def test_retry_test_case_when_raises_errors(self):

        class MyTest(testtools.TestCase):

            @tobiko.retry_test_case()
            def test_errors(self):
                ex = ValueError('pippo')
                errors.append(ex)
                raise ex

        errors = []
        result = testtools.TestResult()
        test_case = MyTest('test_errors')
        test_case.run(result)

        self.assertEqual(1, result.testsRun)
        self.assertEqual([], result.failures)
        self.assertEqual({}, result.skip_reasons)

        self.assertEqual(1, len(errors))
        self.assertEqual(1, len(result.errors))
        failed_test_case, traceback = result.errors[0]
        self.assertIs(test_case, failed_test_case)
        self.assertIn(str(errors[-1]), traceback)

    def test_retry_test_case_when_skip(self):

        class MyTest(testtools.TestCase):

            @tobiko.retry_test_case()
            def test_skip(self):
                next(count_calls)
                self.skip("Not the right day!")

        count_calls = itertools.count()
        result = testtools.TestResult()
        test_case = MyTest('test_skip')
        test_case.run(result)

        self.assertEqual(1, next(count_calls))
        self.assertEqual(1, result.testsRun)
        self.assertEqual([], result.failures)
        self.assertEqual([], result.errors)
        self.assertEqual({"Not the right day!": [test_case]},
                         result.skip_reasons)

    def test_attempt_is_last_with_count(self):
        self.assertFalse(tobiko.retry_attempt(number=2,
                                              count=3).is_last)
        self.assertTrue(tobiko.retry_attempt(number=2,
                                             count=2).is_last)

    def test_attempt_is_last_with_timeout(self):
        self.assertFalse(tobiko.retry_attempt(elapsed_time=2.,
                                              timeout=3.).is_last)
        self.assertTrue(tobiko.retry_attempt(elapsed_time=2.,
                                             timeout=2.).is_last)
