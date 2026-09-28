# Copyright (c) 2019 Red Hat
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

import typing

import pytest

import tobiko
from tobiko.tests import unit


def condition(value: typing.Any):
    return value


class PositiveSkipMethodTest(unit.TobikoUnitTest):

    @tobiko.skip('must always skip')
    def test_skip(self):
        self.fail('Not skipped')

    @tobiko.skip_if('condition value was true', condition, True)
    def test_skip_if_condition_called_with_args(self):
        self.fail('Not skipped')

    @tobiko.skip_if('condition value was true', condition, value=True)
    def test_skip_if_condition_called_with_kwargs(self):
        self.fail('Not skipped')

    @tobiko.skip_unless('condition value was false', condition, False)
    def test_skip_unless_condition_called_with_args(self):
        self.fail('Not skipped')

    @tobiko.skip_unless('condition value was false', condition, value=False)
    def test_skip_unless_condition_called_with_kwargs(self):
        self.fail('Not skipped')


class NegativeSkipBase(unit.TobikoUnitTest):
    test_method_called = False

    def setUp(self):
        super(NegativeSkipBase, self).setUp()
        self.addCleanup(self.assert_test_method_called)

    def assert_test_method_called(self):
        self.assertTrue(self.test_method_called)


class NegativeSkipMethodTest(NegativeSkipBase):

    @tobiko.skip_if('condition value was false', condition, False)
    def test_skip_if_condition_called_with_args(self):
        self.test_method_called = True

    @tobiko.skip_if('condition value was false',
                    condition, value=False)
    def test_skip_if_condition_called_with_kwargs(self):
        self.test_method_called = True

    @tobiko.skip_unless('condition value was true', condition, True)
    def test_skip_unless_condition_called_with_args(self):
        self.test_method_called = True

    @tobiko.skip_unless('condition value was true', condition, value=True)
    def test_skip_unless_condition_called_with_kwargs(self):
        self.test_method_called = True


@tobiko.skip_if('condition value was true', condition, True)
class PositiveSkipIfConditionCalledWithArgsFixture(tobiko.SharedFixture):
    pass


@tobiko.skip_if('condition value was true', condition, value=True)
class PositiveSkipIfConditionCalledWithKwargsFixture(tobiko.SharedFixture):
    pass


@tobiko.skip_unless('condition value was false', condition, False)
class PositiveSkipUnlessConditionCalledWithArgsFixture(tobiko.SharedFixture):
    pass


@tobiko.skip_unless('condition value was false', condition, value=False)
class PositiveSkipUnlessConditionCalledWithKwargsFixture(tobiko.SharedFixture):
    pass


class PositiveSkipFixtureTest(unit.TobikoUnitTest):

    def test_skip_if_condition_called_with_args(self):
        ex = self.assertRaises(
            self.skipException, tobiko.setup_fixture,
            PositiveSkipIfConditionCalledWithArgsFixture)
        self.assertEqual('condition value was true', str(ex))

    def test_skip_if_condition_called_with_kwargs(self):
        ex = self.assertRaises(
            self.skipException, tobiko.setup_fixture,
            PositiveSkipIfConditionCalledWithKwargsFixture)
        self.assertEqual('condition value was true', str(ex))

    def test_skip_unless_condition_called_with_args(self):
        ex = self.assertRaises(
            self.skipException, tobiko.setup_fixture,
            PositiveSkipUnlessConditionCalledWithArgsFixture)
        self.assertEqual('condition value was false', str(ex))

    def test_skip_unless_condition_called_with_kwargs(self):
        ex = self.assertRaises(
            self.skipException, tobiko.setup_fixture,
            PositiveSkipUnlessConditionCalledWithKwargsFixture)
        self.assertEqual('condition value was false', str(ex))


@tobiko.skip_if('condition value was false', condition, False)
class NegativeSkipIfConditionCalledWithArgsFixture(tobiko.SharedFixture):
    pass


@tobiko.skip_if('condition value was false', condition, value=False)
class NegativeSkipIfConditionCalledWithKwargsFixture(tobiko.SharedFixture):
    pass


@tobiko.skip_unless('condition value was true', condition, True)
class NegativeSkipUnlessConditionCalledWithArgsFixture(tobiko.SharedFixture):
    pass


@tobiko.skip_unless('condition value was true', condition, value=True)
class NegativeSkipUnlessConditionCalledWithKwargsFixture(tobiko.SharedFixture):
    pass


class NegativeSkipFixtureTest(unit.TobikoUnitTest):

    def test_skip_if_condition_called_with_args(self):
        fixture = tobiko.setup_fixture(
            NegativeSkipIfConditionCalledWithArgsFixture)
        self.assertIsInstance(
            fixture, NegativeSkipIfConditionCalledWithArgsFixture)

    def test_skip_if_condition_called_with_kwargs(self):
        fixture = tobiko.setup_fixture(
            NegativeSkipIfConditionCalledWithKwargsFixture)
        self.assertIsInstance(
            fixture, NegativeSkipIfConditionCalledWithKwargsFixture)

    def test_skip_unless_condition_called_with_args(self):
        fixture = tobiko.setup_fixture(
            NegativeSkipUnlessConditionCalledWithArgsFixture)
        self.assertIsInstance(
            fixture, NegativeSkipUnlessConditionCalledWithArgsFixture)

    def test_skip_unless_condition_called_with_kwargs(self):
        fixture = tobiko.setup_fixture(
            NegativeSkipUnlessConditionCalledWithKwargsFixture)
        self.assertIsInstance(
            fixture, NegativeSkipUnlessConditionCalledWithKwargsFixture)


@tobiko.skip_if('condition value was true', condition, True)
class PositiveSkipIfConditionCalledWithArgsTest(unit.TobikoUnitTest):

    def test_fail(self):
        self.fail('Not skipped')


@tobiko.skip_if('condition value was true', condition, value=True)
class PositiveSkipIfConditionCalledWithKwargsTest(unit.TobikoUnitTest):

    def test_fail(self):
        self.fail('Not skipped')


@tobiko.skip_unless('condition value was false', condition, False)
class PositiveSkipUnlessConditionCalledWithArgsTest(unit.TobikoUnitTest):

    def test_fail(self):
        self.fail('Not skipped')


@tobiko.skip_unless('condition value was false', condition, value=False)
class PositiveSkipUnlessConditionCalledWithKwargsTest(unit.TobikoUnitTest):

    def test_fail(self):
        self.fail('Not skipped')


@tobiko.skip_if('condition value was true', condition, False)
class NegativeSkipIfConditionCalledWithArgsTest(NegativeSkipBase):

    def test_fail(self):
        self.test_method_called = True


@tobiko.skip_if('condition value was true', condition, value=False)
class NegativeSkipIfConditionCalledWithKwargsTest(NegativeSkipBase):

    def test_fail(self):
        self.test_method_called = True


@tobiko.skip_unless('condition value was false', condition, True)
class NegativeSkipUnlessConditionCalledWithArgsTest(NegativeSkipBase):

    def test_fail(self):
        self.test_method_called = True


@tobiko.skip_unless('condition value was false', condition, value=True)
class NegativeSkipUnlessConditionCalledWithKwargsTest(NegativeSkipBase):

    def test_fail(self):
        self.test_method_called = True


def raise_an_error(error: Exception):
    raise error


def raise_any_error():
    pass


@tobiko.skip_on_error('error raised: {cause}',
                      raise_an_error,
                      error_type=ValueError,
                      error=ValueError("It is all right"))
class PositiveSkipOnErrorTest(unit.TobikoUnitTest):

    def test_skip_on_error(self):
        self.fail('Not skipped')


class PositiveSkipOnErrorMethodTest(unit.TobikoUnitTest):

    @tobiko.skip_on_error('error raised: {cause}',
                          raise_an_error,
                          error_type=RuntimeError,
                          error=RuntimeError("It is all right"))
    def test_skip_on_error(self):
        self.fail('Not skipped')


@tobiko.skip_on_error('error not raised', raise_any_error,
                      error_type=ValueError)
class NegativeSkipOnErrorTest(NegativeSkipBase):
    def test_skip_on_error(self):
        self.test_method_called = True


class NegativeSkipOnErrorMethodTest(NegativeSkipBase):
    @tobiko.skip_on_error('error not raised', raise_any_error,
                          error_type=ValueError)
    def test_skip_on_error(self):
        self.test_method_called = True


class XfailedTest(unit.TobikoUnitTest):
    @pytest.mark.xfail(reason="Skip this test when it fails", strict=False)
    def test_xfailed_test(self):
        self.fail('Test fails')
