# Copyright (c) 2022 Red Hat, Inc.
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
import io
import multiprocessing
import os
import signal
import typing

from oslo_log import log

from tobiko import _exception
from tobiko import _fixture
from tobiko import _retry
from tobiko import _time


LOG = log.getLogger(__name__)


@contextlib.contextmanager
def pause_background_process(target: typing.Callable,
                             *args,
                             process_name: str = None,
                             pid_file: str = None,
                             retry_timeout: _time.Seconds = None,
                             retry_interval: _time.Seconds = None,
                             **kwargs):
    """It stops background process (if running), finally it restart it
    """
    if process_name is None:
        process_name = _fixture.get_object_name(target)
    if pid_file is None:
        pid_file = get_pid_file(process_name)
    stop_background_process(pid_file=pid_file,
                            retry_timeout=retry_timeout,
                            retry_interval=retry_interval)
    try:
        yield
    finally:
        start_background_process(target,
                                 *args,
                                 process_name=process_name,
                                 pid_file=pid_file,
                                 retry_timeout=retry_timeout,
                                 retry_interval=retry_interval,
                                 **kwargs)


class StartBackgroundProcessError(_exception.TobikoException):
    message = ("Error starting background process:\n"
               "  target: {target_name}\n"
               "  process name: {process_name}\n"
               "  PID file: {pid_file}\n"
               "  args: {args}\n"
               "  kwargs: {kwargs}\n"
               "  reason: {reason}\n")


def start_background_process(target: typing.Callable,
                             *args,
                             process_name: str = None,
                             pid_file: str = None,
                             retry_timeout: _time.Seconds = None,
                             retry_interval: _time.Seconds = None,
                             max_pids: typing.Optional[int] = 1,
                             **kwargs) -> bool:
    target_name = _fixture.get_object_name(target)
    if process_name is None:
        process_name = target_name
    if pid_file is None:
        pid_file = get_pid_file(process_name)

    initial_pids = check_background_process(pid_file=pid_file)
    if max_pids is not None:
        if len(initial_pids) >= max_pids:
            LOG.debug('Process already started:\n'
                      f"  target: {target_name}\n"
                      f"  process name: {process_name}\n"
                      f"  PID file: {pid_file}\n"
                      f"  PIDs: {initial_pids}\n"
                      f"  max PIDs: {max_pids}\n")
            return False

    LOG.debug('Starting parent background process...\n'
              f"  target: {target_name}\n"
              f"  process name: {process_name}\n"
              f"  PID file: {pid_file}\n"
              f"  args: {args}\n"
              f"  kwargs {kwargs}\n")
    # start parent process, nested with a started child process
    # then kill the parent
    parameters = BackgroundProcessParameters(target=target,
                                             args=args,
                                             kwargs=kwargs,
                                             process_name=process_name,
                                             pid_file=pid_file,
                                             max_pids=max_pids)
    process = multiprocessing.Process(target=_run_parent_background_process,
                                      name=process_name,
                                      args=(parameters,),
                                      daemon=False)
    process.start()
    LOG.debug(f'Parent background process started (PID={process.pid}).')
    try:
        for attempt in _retry.retry(timeout=retry_timeout,
                                    interval=retry_interval,
                                    default_timeout=15.,
                                    default_interval=.5):
            final_pids = check_background_process(pid_file=pid_file)
            new_pids = sorted(set(final_pids) - set(initial_pids))
            if new_pids:
                LOG.debug(f'New background process started (PIDs={new_pids})')
                break
            if attempt.is_last:
                raise StartBackgroundProcessError(target_name=target_name,
                                                  process_name=process_name,
                                                  pid_file=pid_file,
                                                  args=args,
                                                  kwargs=kwargs,
                                                  reason="timed out")
    finally:
        process.terminate()
        LOG.debug('Background process orphaned')
    return True


def _run_parent_background_process(parameters: 'BackgroundProcessParameters'):
    target_name = _fixture.get_object_name(parameters.target)
    LOG.debug('Starting background process...\n'
              f'  target: {target_name}\n'
              f"  process name: {parameters.process_name}\n"
              f"  PID file: {parameters.pid_file}\n"
              f"  args: {parameters.args}\n"
              f"  kwargs {parameters.kwargs}\n")
    process = multiprocessing.Process(target=_run_background_process,
                                      name=parameters.process_name,
                                      args=(parameters,))
    process.start()
    LOG.debug('Background process started\n'
              f'  target: {target_name}\n'
              f"  process name: {parameters.process_name}\n"
              f"  PID file: {parameters.pid_file}\n"
              f"  PID: {process.pid}\n"
              f"  args: {parameters.args}\n"
              f"  kwargs {parameters.kwargs}\n")
    process.join()


def _run_background_process(parameters: 'BackgroundProcessParameters'):
    # In order to ensure max_pids counter is respected I must check
    target_name = _fixture.get_object_name(parameters.target)
    if parameters.max_pids is not None:
        pids = check_background_process(pid_file=parameters.pid_file)
        if len(pids) >= parameters.max_pids:
            LOG.debug('Aborting background process execution:\n'
                      f"  target: {target_name}\n"
                      f"  process name: {parameters.process_name}\n"
                      f"  PID file: {parameters.pid_file}\n"
                      f"  PIDs: {pids}\n"
                      f"  max PIDs: {parameters.max_pids}\n")
            raise RuntimeError("Background job execution aborted")

    pid = os.getpid()
    with open_pid_file(parameters.pid_file, "at") as fd:
        fd.write(f"{pid}\n")

    assert not is_background_process()
    set_background_process_parameters(parameters)
    assert is_background_process()
    LOG.info(f'Background process is running:\n:'
             f'  target: {target_name}\n'
             f'  name: {parameters.process_name}\n'
             f'  PID file: {parameters.pid_file}\n'
             f'  PID: {pid}\n'
             f"  args: {parameters.args}\n"
             f"  kwargs {parameters.kwargs}\n")
    try:
        result = parameters.target(*parameters.args, **parameters.kwargs)
    except Exception:
        LOG.exception(f'Background process is failed:\n:'
                      f'  target: {target_name}\n'
                      f'  name: {parameters.process_name}\n'
                      f'  PID file: {parameters.pid_file}\n'
                      f'  PID: {pid}\n'
                      f"  args: {parameters.args}\n"
                      f"  kwargs: {parameters.kwargs}\n")
        raise
    else:
        LOG.info(f'Background process has terminated:\n:'
                 f'  target: {target_name}\n'
                 f'  name: {parameters.process_name}\n'
                 f'  PID file: {parameters.pid_file}\n'
                 f'  PID: {pid}\n'
                 f"  args: {parameters.args}\n"
                 f"  kwargs: {parameters.kwargs}\n"
                 f"  result: {result}\n")
        return result


def stop_background_process(*pids: int,
                            pid_file: str = None,
                            terminate_signal=signal.SIGTERM,
                            kill_signal=signal.SIGKILL,
                            retry_timeout: _time.Seconds = None,
                            retry_interval: _time.Seconds = None):
    signaled_pids = signal_background_process(*pids,
                                              pid_file=pid_file,
                                              signal_number=terminate_signal)
    if pid_file is not None:
        remove_pid_file(pid_file)
    if signaled_pids:
        try:
            for attempt in _retry.retry(timeout=retry_timeout,
                                        interval=retry_interval,
                                        default_timeout=15.,
                                        default_interval=.5):
                signaled_pids = check_background_process(*signaled_pids)
                if attempt.is_last or not signaled_pids:
                    break
                LOG.debug(f"Waiting for processes to terminate: "
                          f"{signaled_pids}...")
        finally:
            signal_background_process(*signaled_pids,
                                      signal_number=kill_signal)


def read_pid_file(pid_file: str) -> typing.Tuple[int, ...]:
    """list PIDs of specified bg_process_name file"""
    pids = []
    try:
        fd = open_pid_file(pid_file=pid_file, mode='rt')
    except FileNotFoundError:
        pass
    else:
        with fd:
            for line_number, line in enumerate(fd.readlines(), start=1):
                line = line.strip()
                pid = None
                if line:
                    try:
                        pid = int(line.rstrip())
                    except (TypeError, ValueError):
                        LOG.exception(f"{pid_file}:{line_number}: value is "
                                      f"not an integer ({line}).")
                        continue
                if not pid:
                    continue
                pids.append(pid)
    return tuple(pids)


def get_pid_file(process_name: str) -> str:
    return os.path.expanduser(f'~/.tobiko/pid/{process_name}.pid')


def remove_pid_file(pid_file: str):
    try:
        os.remove(pid_file)
    except FileNotFoundError:
        pass
    else:
        LOG.debug(f"PID file '{pid_file}' removed")


def open_pid_file(pid_file: str, mode: str):
    if set('aw') & set(mode):
        # Ensure pids directory exists
        os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    return io.open(pid_file, mode)


def check_background_process(*pids: int,
                             pid_file: str = None) -> typing.Tuple[int, ...]:
    return signal_background_process(*pids, pid_file=pid_file, signal_number=0)


def signal_background_process(*pids: int,
                              pid_file: str = None,
                              signal_number: int = signal.SIGTERM) \
        -> typing.Tuple[int, ...]:
    if pid_file:
        pids += read_pid_file(pid_file)
    if not pids:
        return tuple()

    signaled_pids: typing.List[int] = []
    for pid in pids:
        try:
            os.kill(pid, signal_number)
            signaled_pids.append(pid)
        except ProcessLookupError:
            pass

    LOG.debug(f"Signal {signal_number} sent to process (PIDs={pids})")
    return tuple(signaled_pids)


def is_background_process() -> bool:
    return get_background_process_parameters() is not None


class BackgroundProcessParameters(typing.NamedTuple):
    target: typing.Callable
    args: typing.Tuple
    kwargs: typing.Dict[str, typing.Any]
    process_name: str
    pid_file: str
    max_pids: typing.Optional[int]


BACKGROUND_PROCESS_PARAMETERS: \
    typing.Optional[BackgroundProcessParameters] = None


def get_background_process_parameters() \
        -> typing.Optional[BackgroundProcessParameters]:
    return BACKGROUND_PROCESS_PARAMETERS


def set_background_process_parameters(parameters: BackgroundProcessParameters):
    # pylint: disable=global-statement
    global BACKGROUND_PROCESS_PARAMETERS
    BACKGROUND_PROCESS_PARAMETERS = parameters


class BackgroundProcessFixture(_fixture.SharedFixture):

    def __init__(self,
                 *args,
                 target: typing.Callable = None,
                 process_name: str = None,
                 pid_file: str = None,
                 retry_timeout: _time.Seconds = None,
                 retry_interval: _time.Seconds = None,
                 terminate_signal=signal.SIGTERM,
                 kill_signal=signal.SIGTERM,
                 **kwargs):
        super().__init__()
        if target is None:
            target = self.run
            if process_name is None:
                process_name = _fixture.get_fixture_name(self)
        elif process_name is None:
            process_name = _fixture.get_object_name(target)
        if pid_file is None:
            pid_file = get_pid_file(process_name)
        self._target = target
        self._process_name = process_name
        self._pid_file = pid_file
        self._target = target
        self._args = args
        self._kwargs = kwargs
        self._retry_timeout = retry_timeout
        self._retry_interval = retry_interval
        self._terminate_signal = terminate_signal
        self._kill_signal = kill_signal

    def setup_fixture(self):
        if not is_background_process():
            start_background_process(type(self)._run,
                                     *self._args,
                                     process_name=self._process_name,
                                     pid_file=self._pid_file,
                                     retry_timeout=self._retry_timeout,
                                     retry_interval=self._retry_interval,
                                     **self._kwargs)

    def cleanup_fixture(self):
        stop_background_process(pid_file=self._pid_file,
                                terminate_signal=self._terminate_signal,
                                kill_signal=self._kill_signal,
                                retry_timeout=self._retry_timeout,
                                retry_interval=self._retry_interval)

    @contextlib.contextmanager
    def pause(self):
        return pause_background_process(target=self._target,
                                        process_name=self._process_name,
                                        pid_file=self._pid_file,
                                        args=self._args,
                                        kwargs=self._kwargs,
                                        retry_timeout=self._retry_timeout,
                                        retry_interval=self._retry_interval)

    def start(self):
        _fixture.setup_fixture(self)

    def stop(self):
        _fixture.cleanup_fixture(self)

    def kill(self):
        signal_background_process(pid_file=self._pid_file,
                                  signal_number=self._kill_signal)
        _fixture.cleanup_fixture(self)

    def check(self):
        return check_background_process(pid_file=self._pid_file)

    @property
    def is_alive(self) -> bool:
        return bool(self.check())

    @classmethod
    def _run(cls, *args, **kwargs):
        # pylint: disable=protected-access
        assert is_background_process()
        return _fixture.setup_fixture(cls)._target(*args, **kwargs)

    def run(self, *args, **kwargs):
        raise NotImplementedError
