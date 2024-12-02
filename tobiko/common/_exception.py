# Copyright 2018 Red Hat
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
import collections
import sys
import typing  # noqa

from oslo_log import log
import testtools


LOG = log.getLogger(__name__)


class TobikoException(Exception):
    """Base Tobiko Exception.

    To use this class, inherit from it and define attribute 'message' string.
    If ``properties`` parameters is given, then it will format message string
    using properties as key-word arguments.

    Example::

        class MyException(TobikoException):
            message = "This exception occurred because of {reason}"

        try:
            raise MyException(reason="something went wrong")
        except MyException as ex:

            # It should print:
            #   This exception occurred because of something went wrong
            print(ex)

            # It should print:
            #   something went wrong
            print(ex.reason)

    :attribute message: the message to be printed out.
    """

    message = "unknown reason"

    def __init__(self, message=None, **properties):
        message = message or self.message
        if properties:
            message = message.format(**properties)
        self.message = message
        self._properties = properties or {}
        super(TobikoException, self).__init__(message)

    def __getattr__(self, name):
        try:
            return self._properties[name]
        except KeyError as ex:
            raise AttributeError(f"{self!r} object has no attribute "
                                 f"'{name}'") from ex

    def __repr__(self):
        return "{class_name}({message!r})".format(
            class_name=type(self).__name__,
            message=self.message)

    def __eq__(self, other):
        return type(self) is type(other) and str(self) == str(other)

    def __hash__(self):
        return hash(type(self)) + hash(str(self))


def check_valid_type(obj, *valid_types):
    if not isinstance(obj, valid_types):
        types_str = ", ".join(str(t) for t in valid_types)
        message = f"Object {obj!r} is not of a valid type ({types_str})"
        raise TypeError(message)
    return obj


class ExceptionInfo(collections.namedtuple('ExceptionInfo',
                                           ['type', 'value', 'traceback'])):

    reraise_on_exit = True

    def __enter__(self):
        return self

    def __bool__(self):
        return self.type is not None

    def __exit__(self, _type, _value, _traceback):
        if self.reraise_on_exit:
            self.reraise()

    def reraise(self):
        if self.type is not None:
            reraise(*self)


def reraise(tp, value, tb=None):
    try:
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
    finally:
        value = None
        tb = None


def exc_info(reraise=True):
    # pylint: disable=redefined-outer-name
    info = ExceptionInfo(*sys.exc_info())
    info.reraise_on_exit = reraise
    return info


def log_unhandled_exception(exc_type, exc_value, ex_tb):
    LOG.exception("Unhandled exception",
                  exc_info=(exc_type, exc_value, ex_tb))


@contextlib.contextmanager
def handle_multiple_exceptions(handle_exception=log_unhandled_exception):
    exception: typing.Optional[typing.Tuple] = None
    try:
        yield
    except testtools.MultipleExceptions as ex:
        exc_infos = list_exc_infos()
        if exc_infos:
            exception = exc_infos[0]
            for info in exc_infos[1:]:
                try:
                    handle_exception(*info)
                except Exception:
                    LOG.exception("Error handling multiple exceptions")
        else:
            LOG.debug(f"Empty MultipleExceptions: '{ex}'")

    if exception is not None:
        reraise(*exception)


def list_exc_infos(exc_info=None):
    # pylint: disable=redefined-outer-name
    exc_info = exc_info or sys.exc_info()
    result = []
    if exc_info[0]:
        visited = set()
        visiting = [exc_info]
        while visiting:
            exc_info = visiting.pop()
            _, exc, _ = exc_info
            if exc not in visited:
                visited.add(exc)
                if isinstance(exc, testtools.MultipleExceptions):
                    visiting.extend(reversed(exc.args))
                else:
                    result.append(exc_info)
    return result
