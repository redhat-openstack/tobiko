# Copyright 2021 Red Hat
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
import functools
import inspect
import types
import typing

import decorator


P = typing.TypeVar('P')

GenericMetaBase = abc.ABCMeta
if hasattr(typing, 'GenericMeta'):
    class GenericMetaBase(  # type: ignore[no-redef]
            typing.GenericMeta,  # type: ignore[name-defined]
            abc.ABCMeta):
        # pylint: disable=function-redefined,no-member
        pass


class GenericMeta(GenericMetaBase):

    @functools.lru_cache(maxsize=4096)
    def __getitem__(self, item):
        # pylint: disable=not-callable
        cls = self
        getitem = getattr(super(), '__getitem__', None)
        if callable(getitem):
            cls = getitem(item)
        class_getitem = getattr(cls, '__class_getitem__', None)
        if callable(class_getitem):
            if inspect.ismethod(class_getitem):
                cls = class_getitem(item)
            else:
                cls = class_getitem(cls, item)
        return cls


class Generic(typing.Generic[P], metaclass=GenericMeta):
    pass


PredicateFunction = typing.Callable[[typing.Any], bool]


def is_public_function(obj) -> bool:
    return (inspect.isfunction(obj) and
            getattr(obj, '__name__', '_')[0] != '_')


def is_public_abstract_method(obj) -> bool:
    return (is_public_function(obj) and
            getattr(obj, "__isabstractmethod__", False))


class CallHandler(abc.ABC):

    @abc.abstractmethod
    def _handle_call(self, method: typing.Callable, *args, **kwargs) \
            -> typing.Any:
        raise NotImplementedError


# pylint: disable=inherit-non-class
class CallProxyBase(CallHandler, Generic[P], abc.ABC):

    def __class_getitem__(cls, item: typing.Type[P]):
        if isinstance(item, type):
            return create_call_proxy_class(protocols=(item,),
                                           class_name=cls.__name__,
                                           bases=(cls, item),
                                           predicate=cls._is_proxy_method)
        else:
            return cls

    @classmethod
    def _is_proxy_method(cls, obj) -> bool:
        return is_public_abstract_method(obj)


# pylint: disable=inherit-non-class
class CallProxy(CallProxyBase, Generic[P]):

    def __init__(self, handle_call: typing.Callable):
        super(CallProxy, self).__init__()
        assert callable(handle_call)
        self._handle_call = handle_call  # type: ignore

    def _handle_call(self, method: typing.Callable, *args, **kwargs):
        raise NotImplementedError


def create_call_proxy_class(
        protocols: typing.Tuple[type, ...],
        class_name: str,
        bases: typing.Tuple[type, ...] = None,
        namespace: dict = None,
        predicate: PredicateFunction = None) -> type:
    if bases is None:
        bases = tuple()
    if predicate is None:
        predicate = is_public_abstract_method

    def exec_body(ns: typing.Dict[str, typing.Any]):
        if namespace is not None:
            ns.update(namespace)
        for cls in protocols:
            for member_name, member in inspect.getmembers(cls, predicate):
                if member_name not in ns:
                    method = create_call_proxy_method(member)
                    ns[member_name] = method

    return types.new_class(name=class_name,
                           bases=bases,
                           exec_body=exec_body)


def create_call_proxy(handle_call: typing.Callable,
                      *protocols: typing.Type[P]) -> P:
    cls = create_call_proxy_class(protocols=protocols,
                                  class_name='CallProxy',
                                  bases=(CallProxy,) + protocols)
    return cls(handle_call)  # type: ignore[call-arg]


def list_abstract_classes(cls: typing.Type) \
        -> typing.Tuple[typing.Type[P], ...]:
    subclasses = inspect.getmro(cls)
    protocols = tuple(cls
                      for cls in subclasses
                      if inspect.isabstract(cls))
    return typing.cast(typing.Tuple[typing.Type[P], ...], protocols)


def list_abstract_methods(cls: typing.Type) \
        -> typing.List[typing.Tuple[str, typing.Callable]]:
    methods: typing.List[typing.Tuple[str, typing.Callable]] = []
    for name, member in inspect.getmembers(cls, inspect.isfunction):
        if getattr(member, "__isabstractmethod__", False):
            methods.append((name, member))
    return methods


def create_call_proxy_method(func: typing.Callable) -> typing.Callable:
    method = decorator.decorate(func, _call_proxy_method)
    assert method is not func
    setattr(method, "__isabstractmethod__", False)
    return method


def _call_proxy_method(func, self: CallProxy, *args, **kwargs):
    # pylint: disable=protected-access
    return self._handle_call(func, *args, **kwargs)
