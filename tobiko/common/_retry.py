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

import functools
import itertools
import typing

from oslo_log import log

from tobiko.common import _exception
from tobiko.common import _time


LOG = log.getLogger(__name__)


class RetryException(_exception.TobikoException):
    pass


class RetryLimitError(RetryException):
    message = ("Retry limit exceeded ({attempt.details})")


class RetryCountLimitError(RetryLimitError):
    message = ("Retry count limit exceeded ({attempt.details})")


class RetryTimeLimitError(RetryLimitError):
    message = ("Retry time limit exceeded ({attempt.details})")


class RetryAttempt(object):

    def __init__(self,
                 number: int,
                 start_time: float,
                 elapsed_time: float,
                 count: typing.Optional[int] = None,
                 timeout: _time.Seconds = None,
                 sleep_time: _time.Seconds = None,
                 interval: _time.Seconds = None):
        self.number = number
        self.start_time = start_time
        self.elapsed_time = elapsed_time
        self.count = count
        self.timeout = _time.to_seconds(timeout)
        self.sleep_time = _time.to_seconds(sleep_time)
        self.interval = _time.to_seconds(interval)

    def __eq__(self, other):
        return (other.number == self.number and
                other.start_time == self.start_time and
                other.elapsed_time == self.elapsed_time and
                other.count == self.count and
                other.timeout == self.timeout and
                other.sleep_time == self.sleep_time and
                other.interval == self.interval)

    def __hash__(self):
        raise NotImplementedError

    @property
    def count_left(self) -> typing.Optional[int]:
        if self.count is None:
            return None
        else:
            return max(0, self.count - self.number)

    def check_count_left(self) -> _time.Seconds:
        if self.count_left == 0:
            _exception.exc_info().reraise()
            raise RetryCountLimitError(attempt=self)
        return self.count_left

    @property
    def time_left(self) -> _time.Seconds:
        if self.timeout is None:
            return None
        else:
            return max(0., self.timeout - self.elapsed_time)

    def check_time_left(self) -> _time.Seconds:
        if self.time_left == 0.:
            _exception.exc_info().reraise()
            raise RetryTimeLimitError(attempt=self)
        return self.time_left

    def check_limits(self):
        self.check_count_left()
        self.check_time_left()

    @property
    def details(self) -> str:
        details = [f"number={self.number}"]
        if self.count is not None:
            details.append(f"count={self.count}")
        details.append(f"elapsed_time={self.elapsed_time}")
        if self.timeout is not None:
            details.append(f"timeout={self.timeout}")
        if self.sleep_time is not None:
            details.append(f"sleep_time={self.sleep_time}")
        if self.interval is not None:
            details.append(f"interval={self.interval}")
        return ', '.join(details)

    @property
    def is_first(self) -> bool:
        return self.number == 0

    @property
    def is_last(self) -> bool:
        try:
            self.check_limits()
        except Exception:
            return True
        else:
            return False

    def __repr__(self):
        return f"retry_attempt({self.details})"


def retry_attempt(number: int = 0,
                  start_time: float = 0.,
                  elapsed_time: float = 0.,
                  count: typing.Optional[int] = None,
                  timeout: _time.Seconds = None,
                  sleep_time: _time.Seconds = None,
                  interval: _time.Seconds = None) -> RetryAttempt:
    return RetryAttempt(number=number,
                        count=count,
                        start_time=start_time,
                        elapsed_time=elapsed_time,
                        timeout=timeout,
                        sleep_time=sleep_time,
                        interval=interval)


class Retry(object):

    def __init__(self,
                 count: typing.Optional[int] = None,
                 timeout: _time.Seconds = None,
                 sleep_time: _time.Seconds = None,
                 interval: _time.Seconds = None):
        self.count = count
        self.timeout = _time.to_seconds(timeout)
        self.sleep_time = _time.to_seconds(sleep_time)
        self.interval = _time.to_seconds(interval)

    def __eq__(self, other):
        return (other.count == self.count and
                other.timeout == self.timeout and
                other.sleep_time == self.sleep_time and
                other.interval == self.interval)

    def __hash__(self):
        raise NotImplementedError

    def __iter__(self) -> typing.Iterator[RetryAttempt]:
        start_time = _time.time()
        elapsed_time = 0.
        for number in itertools.count(1):
            attempt = retry_attempt(number=number,
                                    count=self.count,
                                    start_time=start_time,
                                    elapsed_time=elapsed_time,
                                    timeout=self.timeout,
                                    sleep_time=self.sleep_time,
                                    interval=self.interval)

            yield attempt

            attempt.check_limits()

            elapsed_time = _time.time() - start_time
            sleep_time = self.sleep_time
            if sleep_time is None and self.interval is not None:
                sleep_time = attempt.number * self.interval - elapsed_time

            if sleep_time is not None:
                sleep_time = max(0., sleep_time)
                time_left = attempt.time_left
                if sleep_time > 0.:
                    if time_left is None or time_left > sleep_time:
                        LOG.debug(f"Wait for {sleep_time} seconds before "
                                  f"retrying... ({attempt.details})")
                        _time.sleep(sleep_time)
                        elapsed_time = _time.time() - start_time

            if not sleep_time:  # sleep_time is None or 0.
                LOG.debug(f"retrying without waiting... ({attempt.details})")

    @property
    def details(self) -> str:
        details = []
        if self.count is not None:
            details.append(f"count={self.count}")
        if self.timeout is not None:
            details.append(f"timeout={self.timeout}")
        if self.sleep_time is not None:
            details.append(f"sleep_time={self.sleep_time}")
        if self.interval is not None:
            details.append(f"interval={self.interval}")
        return ', '.join(details)

    def __repr__(self):
        return f"retry({self.details})"


def retry(other_retry: typing.Optional[Retry] = None,
          count: typing.Optional[int] = None,
          timeout: _time.Seconds = None,
          sleep_time: _time.Seconds = None,
          interval: _time.Seconds = None,
          default_count: typing.Optional[int] = None,
          default_timeout: _time.Seconds = None,
          default_sleep_time: _time.Seconds = None,
          default_interval: _time.Seconds = None) -> Retry:

    if other_retry is not None:
        # Apply default values from the other Retry object
        _exception.check_valid_type(other_retry, Retry)
        count = count or other_retry.count
        timeout = timeout or other_retry.timeout
        sleep_time = sleep_time or other_retry.sleep_time
        interval = interval or other_retry.interval

    # Apply default values
    count = count or default_count
    timeout = timeout or default_timeout
    sleep_time = sleep_time or default_sleep_time
    interval = interval or default_interval

    return Retry(count=count,
                 timeout=timeout,
                 sleep_time=sleep_time,
                 interval=interval)


def retry_on_exception(
        exception: Exception,
        *exceptions: Exception,
        other_retry: typing.Optional[Retry] = None,
        count: typing.Optional[int] = None,
        timeout: _time.Seconds = None,
        sleep_time: _time.Seconds = None,
        interval: _time.Seconds = None,
        default_count: typing.Optional[int] = None,
        default_timeout: _time.Seconds = None,
        default_sleep_time: _time.Seconds = None,
        default_interval: _time.Seconds = None,
        on_exception: typing.Optional[typing.Callable] = None) -> \
        typing.Callable[[typing.Callable], typing.Callable]:

    retry_object = retry(other_retry=other_retry,
                         count=count,
                         timeout=timeout,
                         sleep_time=sleep_time,
                         interval=interval,
                         default_count=default_count,
                         default_timeout=default_timeout,
                         default_sleep_time=default_sleep_time,
                         default_interval=default_interval)
    exceptions = (exception,) + exceptions

    def decorator(func):
        if typing.TYPE_CHECKING:
            # Don't need to wrap the function when going to check argument
            # types
            return func

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # pylint: disable=catching-non-exception
            for attempt in retry_object:
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    attempt.check_limits()
                    if on_exception is not None:
                        on_exception(attempt, *args, **kwargs)
        return wrapper

    return decorator
