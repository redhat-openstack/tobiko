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

import sys

import testtools

import tobiko
from tobiko.tests import unit


class SomeException(tobiko.TobikoException):
    message = "message formatted with {b} and {a}"


class TestException(unit.TobikoUnitTest):

    def test_init(self, message=None, **properties):
        ex = SomeException(message, **properties)
        expected_str = message or SomeException.message
        if properties:
            expected_str = expected_str.format(**properties)
        self.assertEqual(expected_str, str(ex))
        for k, v in properties.items():
            self.assertEqual(v, getattr(ex, k))

    def test_init_with_properties(self):
        self.test_init(a='a', b='b')

    def test_init_with_message(self):
        self.test_init('{other} message', other='another')

    def test_raise(self):
        def _raise_my_exception(**kwargs):
            raise SomeException(**kwargs)
        ex = self.assertRaises(SomeException, _raise_my_exception, b=1, a=2)
        self.assertEqual('message formatted with 1 and 2', str(ex))

    def test_repr(self):
        ex = SomeException('some reason')
        self.assertEqual("SomeException('some reason')", repr(ex))

    def test_get_invalid_property(self):
        ex = SomeException(a='1', b='2')

        def _get_invalid_property():
            return ex.invalid_attribute_name

        ex = self.assertRaises(AttributeError, _get_invalid_property)
        self.assertEqual(
            "SomeException('message formatted with 2 and 1') object has no "
            "attribute 'invalid_attribute_name'", str(ex))

    def test_docstring_example(self):

        class MyException(tobiko.TobikoException):
            message = "This exception occurred because of {reason}"

        try:
            raise MyException(reason="something went wrong")
        except MyException as ex:
            self.assertEqual(
                'This exception occurred because of something went wrong',
                str(ex))
            self.assertEqual('something went wrong', ex.reason)


class TestCheckValidType(unit.TobikoUnitTest):

    def test_check_valid_type_with_no_type(self):
        self._test_check_is_valid_type_when_invalid(object())

    def test_check_valid_type_with_one_type(self):
        self._test_check_is_valid_type_when_valid(object(), object)

    def test_check_valid_type_with_two_types(self):
        self._test_check_is_valid_type_when_valid(object(), bool, object)

    def test_check_valid_type_with_one_wrong_type(self):
        self._test_check_is_valid_type_when_invalid(object(), bool)

    def test_check_valid_type_with_two_wrong_types(self):
        self._test_check_is_valid_type_when_invalid(object(), bool, int)

    def _test_check_is_valid_type_when_valid(self, obj, *valid_types):
        result = tobiko.check_valid_type(obj, *valid_types)
        self.assertIs(obj, result)

    def _test_check_is_valid_type_when_invalid(self, obj, *valid_types):
        ex = self.assertRaises(TypeError, tobiko.check_valid_type, obj,
                               *valid_types)
        tyes_str = ', '.join([str(t) for t in valid_types])
        message = ("Object {!s} is not of a valid type ({!s})"
                   ).format(repr(obj), tyes_str)

        self.assertEqual(message, str(ex))


class TestExcInfo(unit.TobikoUnitTest):

    def test_exc_info(self):
        exc_type, exc_value, traceback = None, None, None
        exc_info = None
        try:
            raise RuntimeError('some error')
        except RuntimeError:
            exc_info = tobiko.exc_info()
            exc_type, exc_value, traceback = sys.exc_info()

        self.assertEqual((exc_type, exc_value, traceback), exc_info)
        self.assertIs(RuntimeError, exc_info.type)
        self.assertIs(exc_value, exc_info.value)
        self.assertIs(traceback, exc_info.traceback)

        reraised = self.assertRaises(RuntimeError, exc_info.reraise)
        self.assertIs(exc_value, reraised)


class TestListExcInfo(unit.TobikoUnitTest):

    def test_list_exc_info(self):
        result = tobiko.list_exc_infos()
        self.assertEqual([], result)

    def test_list_exc_info_with_info(self):
        error = make_exception(RuntimeError, 'error')
        result = tobiko.list_exc_infos(exc_info=error)
        self.assertEqual([error], result)

    def test_list_exc_info_handling_exception(self):
        try:
            raise RuntimeError('error')
        except RuntimeError:
            result = tobiko.list_exc_infos()
            self.assertEqual([sys.exc_info()], result)

    def test_list_exc_info_handling_empty_multiple_exceptions(self):
        error = make_exception(testtools.MultipleExceptions)
        result = tobiko.list_exc_infos(exc_info=error)
        self.assertEqual([], result)

    def test_list_exc_info_handling_multiple_exceptions(self):
        a = make_exception(RuntimeError, 'a')
        b = make_exception(ValueError, 'b')
        c = make_exception(TypeError, 'c')
        multi = make_exception(testtools.MultipleExceptions, a, b, c)
        result = tobiko.list_exc_infos(exc_info=multi)
        self.assertEqual([a, b, c], result)

    def test_list_exc_info_handling_nested_multiple_exceptions(self):
        a = make_exception(RuntimeError, 'a')
        b = make_exception(ValueError, 'b')
        c = make_exception(TypeError, 'c')
        d = make_exception(IndexError, 'd')
        inner = make_exception(testtools.MultipleExceptions, b, c)
        multi = make_exception(testtools.MultipleExceptions, a, inner, d)
        result = tobiko.list_exc_infos(exc_info=multi)
        self.assertEqual([a, b, c, d], result)


class TestHandleMultipleExceptions(unit.TobikoUnitTest):

    def test_handle_multiple_exceptions(self):
        with tobiko.handle_multiple_exceptions():
            pass

    def test_handle_multiple_exceptions_with_exception(self):
        def run():
            with tobiko.handle_multiple_exceptions():
                raise RuntimeError('error')
        self.assertRaises(RuntimeError, run)

    def test_handle_multiple_exceptions_with_empty_multiple_exception(self):
        with tobiko.handle_multiple_exceptions():
            raise testtools.MultipleExceptions()

    def test_handle_multiple_exceptions_with_multiple_exceptions(self):
        a = make_exception(TypeError, 'a')
        b = make_exception(ValueError, 'b')
        c = make_exception(RuntimeError, 'c')

        def run():
            with tobiko.handle_multiple_exceptions():
                raise testtools.MultipleExceptions(a, b, c)

        ex = self.assertRaises(TypeError, run)
        self.assertEqual(a[1], ex)

    def test_handle_multiple_exceptions_with_nested_multiple_exceptions(self):
        a = make_exception(RuntimeError, 'a')
        b = make_exception(ValueError, 'b')
        c = make_exception(TypeError, 'c')
        d = make_exception(IndexError, 'd')
        inner = make_exception(testtools.MultipleExceptions, b, c)

        def run():
            with tobiko.handle_multiple_exceptions():
                raise testtools.MultipleExceptions(a, inner, d)

        ex = self.assertRaises(RuntimeError, run)
        self.assertEqual(a[1], ex)

    def test_handle_multiple_exceptions_with_handle_exceptions(self):
        a = make_exception(RuntimeError, 'a')
        b = make_exception(ValueError, 'b')
        c = make_exception(TypeError, 'c')
        d = make_exception(IndexError, 'd')
        inner = make_exception(testtools.MultipleExceptions, b, c)

        handled_exceptions = []

        def handle_exception(ex_type, ex_value, ex_tb):
            self.assertIsInstance(ex_value, ex_type)
            handled_exceptions.append((ex_type, ex_value, ex_tb))

        def run():
            with tobiko.handle_multiple_exceptions(
                    handle_exception=handle_exception):
                raise testtools.MultipleExceptions(a, inner, d)

        ex = self.assertRaises(RuntimeError, run)
        self.assertIs(a[1], ex)
        self.assertEqual([b, c, d], handled_exceptions)


def make_exception(cls, *args, **kwargs):
    try:
        raise cls(*args, **kwargs)
    except cls:
        return sys.exc_info()
