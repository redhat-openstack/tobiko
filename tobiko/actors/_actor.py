# Copyright (c) 2021 Red Hat, Inc.
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

import abc
import asyncio
import inspect
import logging
import typing
import uuid

from oslo_log import log

import tobiko
from tobiko.actors import _proxy
from tobiko.actors import _request


A = typing.TypeVar('A', bound='ActorBase')


# pylint: disable=inherit-non-class
class ActorRef(_proxy.CallProxyBase, _proxy.Generic[A]):

    _actor_class: typing.Type[A]

    def __class_getitem__(cls, item):
        # pylint: disable=too-many-function-args
        if isinstance(item, type):
            if issubclass(item, ActorBase):
                actor_class: typing.Type[ActorBase] = item
                base_name = cls.__name__.split('[', 1)[0]
                ref_class = _proxy.create_call_proxy_class(
                    protocols=(actor_class,),
                    class_name=f"{base_name}[{actor_class.__name__}]",
                    bases=(cls,),
                    namespace=dict(_actor_class=item),
                    predicate=is_actor_method)
                ref_class.__module__ = cls.__module__
                return ref_class
            else:
                raise TypeError(f'{item} is not subclass of {ActorBase}')

        ref_class = cls
        getitem = getattr(super(), '__class_getitem__')
        if callable(getitem):
            if inspect.ismethod(getitem):
                ref_class = getitem(item)
            else:
                ref_class = getitem(cls, item)
        return ref_class

    def __init__(self, actor: A):
        super().__init__()
        self._actor = tobiko.check_valid_type(actor, self._actor_class)

    def _handle_call(self, method: typing.Callable, *args, **kwargs) \
            -> asyncio.Future:
        arguments = inspect.signature(method).bind(
            None, *args, **kwargs).arguments
        arguments.pop('self', None)
        return self._actor.send_request(method.__name__, **arguments)

    def __repr__(self):
        return f'{type(self).__name__}({self._actor})'


def is_actor_method(obj):
    return getattr(obj, '__tobiko_actor_method__', False)


def actor_method(obj):
    if not callable(obj):
        raise TypeError(f"Actor method {obj} is not callable")

    if not inspect.iscoroutinefunction(obj):
        raise TypeError(f"Actor method {obj} is not async")

    if not _proxy.is_public_function(obj):
        raise TypeError(f"Actor method name {obj} can't start with '_'")

    name = getattr(obj, '__name__', None)
    if name is None or hasattr(ActorRef, name) or hasattr(Actor, name):
        raise TypeError(f"Invalid method name: '{name}'")

    obj.__tobiko_actor_method__ = True
    return obj


class _DummyActorProtocol(abc.ABC):
    pass


class ActorBase(tobiko.SharedFixture):
    max_queue_size: int = 0

    # Class methods ----------------------------------------------------------

    def __init_subclass__(cls,
                          *args,
                          **kwargs):
        super().__init_subclass__(*args, **kwargs)
        cls._actor_ref_class = ActorRef[cls]

    def __init__(self,
                 actor_id: str = None,
                 loop: asyncio.AbstractEventLoop = None,
                 log: logging.LoggerAdapter = None,
                 requests: _request.ActorRequestQueue = None):
        # pylint: disable=redefined-outer-name
        super().__init__()
        self.actor_id = actor_id
        if log is None:
            log = self._init_log()
        self.log = log
        if loop is None:
            loop = self._init_loop()
        self.loop = loop
        if requests is None:
            requests = self._init_requests()
        self.requests = requests
        self.setup_actor_future = self.loop.create_future()
        self.cleanup_actor_future = self.loop.create_future()
        self.cleanup_actor_future.set_result(None)

    def setup_fixture(self):
        if self.actor_id is None:
            self.actor_id = self._setup_actor_id()
        if self.setup_actor_future.done():
            self.setup_actor_future.cancel()
            self.setup_actor_future = self.loop.create_future()
        if self.cleanup_actor_future.done():
            self.cleanup_actor_future.cancel()
            self.cleanup_actor_future = self.loop.create_future()

    @property
    def ref(self) -> 'ActorRef':
        return self._actor_ref_class(actor=self)

    @property
    def actor_name(self) -> str:
        return tobiko.get_fixture_name(self)

    def send_request(self, method: str, **arguments) -> asyncio.Future:
        if self.actor_id is None:
            raise ValueError("Actor not set up yet")
        return self.requests.send_request(actor_id=self.actor_id,
                                          method=method,
                                          arguments=arguments)

    # Private instance methods -----------------------------------------------

    def _init_log(self):
        return log.getLogger(self.actor_name)

    @staticmethod
    def _init_loop() -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()

    def _init_requests(self) -> _request.ActorRequestQueue:
        return _request.create_request_queue(max_size=self.max_queue_size,
                                             loop=self.loop)

    @staticmethod
    def _setup_actor_id() -> str:
        return str(uuid.uuid4())


class Actor(ActorBase):

    _stop_actor = False
    _run_actor_task: asyncio.Task

    # Class methods ----------------------------------------------------------

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__(*args, **kwargs)
        cls._actor_methods = dict(inspect.getmembers(cls, is_actor_method))

    @classmethod
    def get_fixture_manager(cls) -> tobiko.FixtureManager:
        from tobiko.actors import _manager
        return _manager.actor_manager()

    # Public methods ---------------------------------------------------------

    def setup_fixture(self):
        super().setup_fixture()
        self._run_actor_task = self.loop.create_task(
            self._run_actor())

    def cleanup_fixture(self):
        super().cleanup_fixture()
        self._stop_actor = True
        if hasattr(self, '_run_actor_task'):
            if not self._run_actor_task.done():
                # must weak up the actor with a message
                self.ref.ping_actor('cleanup')

    async def setup_actor(self):
        pass

    async def cleanup_actor(self):
        pass

    async def ping_actor(self, data: typing.Any = None) -> typing.Any:
        return data
    ping_actor.__tobiko_actor_method__ = True  # type: ignore[attr-defined]

    # Private methods --------------------------------------------------------

    async def _run_actor(self):
        await self._setup_actor()
        self._stop_actor = False
        while not self._stop_actor:
            request = await self.requests.receive_request()
            await self._receive_request(request)
        with tobiko.exc_info(reraise=True):
            await self._cleanup_actor()

    async def _setup_actor(self):
        try:
            self.log.debug(f'Actor setup started {self.actor_name}')
            await self.setup_actor()
        except Exception as ex:
            self.log.exception(
                f'Failed Setting up actor: {self.actor_name} '
                f'({self.actor_id})')
            self.setup_actor_future.set_exception(ex)
        else:
            self.setup_actor_future.set_result(None)
            self.log.debug(f'Actor setup succeeded: {self.actor_name} '
                           f'({self.actor_id}).')

    async def _cleanup_actor(self):
        try:
            self.log.debug(f'Actor cleanup started: {self.actor_name} '
                           f'({self.actor_id}).')
            await self.cleanup_actor()
        except Exception as ex:
            self.cleanup_actor_future.set_exception(ex)
            self.log.exception(
                f'Actor cleanup failed: {self.actor_name} '
                f'({self.actor_id}).')
        else:
            self.cleanup_actor_future.set_result(None)
            self.log.debug(f'Actor cleanup succeeded: {self.actor_name} '
                           f'({self.actor_id}).')
        finally:
            with tobiko.exc_info(reraise=True):
                await self.requests.cancel_requests(actor_id=self.actor_id)

    async def _receive_request(self, request: _request.ActorRequest):
        tobiko.check_valid_type(request, _request.ActorRequest)
        if request.actor_id != self.actor_id:
            raise ValueError(f"Invalid request actor_id: {request.actor_id}")
        method = self._get_actor_method(request.method)
        try:
            result = await method(self, **request.arguments)
        except Exception as ex:
            request.future.set_exception(ex)
        else:
            request.future.set_result(result)

    def _get_actor_method(self, name: str) -> typing.Callable:
        method = self._actor_methods.get(name)
        if method is None:
            raise ValueError(f"Invalid request method name: {name}")
        return method
