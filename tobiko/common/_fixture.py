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

import json
import os
import inspect
import sys
import typing

import fixtures
from oslo_log import log
import testtools

from tobiko.common import _case
from tobiko.common import _detail
from tobiko.common import _exception
from tobiko.common import _loader


LOG = log.getLogger(__name__)

F = typing.TypeVar('F', 'SharedFixture', fixtures.Fixture)
G = typing.TypeVar('G', bound=fixtures.Fixture)

FixtureType = typing.Union[F, typing.Type[F], str]


def is_fixture(obj: typing.Any) -> bool:
    """It returns whenever obj is a fixture or not"""
    return (getattr(obj, '__tobiko_fixture__', False) or
            isinstance(obj, fixtures.Fixture) or
            (inspect.isclass(obj) and issubclass(obj, fixtures.Fixture)))


@typing.overload
def get_fixture(obj: typing.Type[F],
                fixture_id: typing.Any = None,
                manager: 'FixtureManager' = None,
                **kwargs) -> F:
    pass


@typing.overload
def get_fixture(obj: F,
                fixture_id: typing.Any = None,
                manager: 'FixtureManager' = None,
                **kwargs) -> F:
    pass


@typing.overload
def get_fixture(obj: str,
                fixture_id: typing.Any = None,
                manager: 'FixtureManager' = None,
                **kwargs) -> fixtures.Fixture:
    pass


def get_fixture(obj: FixtureType,
                fixture_id: typing.Any = None,
                manager: 'FixtureManager' = None,
                **kwargs) -> F:
    """Returns a fixture identified by given :param obj:

    It returns registered fixture for given :param obj:. If none has been
    registered it creates a new one.

    :param obj: can be:
      - an instance of fixtures.Fixture class: on such case it would return
        obj itself
      - the unique fully qualified name or an object that refers to a fixture
        class or an instance to a fixture.
      - the class of the fixture. It must be a subclass of fixtures.Fixture
        sub-class.

    :param fixture_id
      - an identifier that allows to instanciate and identify other fixtures
        than default one (fixture_id=None) for given fixture class

    :param manager
      - (optional) a FixtureManager instance

    :returns: an instance of fixture class identified by obj, or obj itself
    if it is instance of fixtures.Fixture class.

    """
    if isinstance(obj, fixtures.Fixture):
        return typing.cast(F, obj)
    return fixture_manager(obj, manager).get_fixture(
        obj, fixture_id=fixture_id, **kwargs)


def get_fixture_name(obj) -> str:
    """It gets unique fixture name"""
    name = getattr(obj, '__tobiko_fixture_name__', None)
    if name is None:
        if not is_fixture(obj):
            raise TypeError('Object {obj!r} is not a fixture.'.format(obj=obj))
        name = get_object_name(obj)
        if not inspect.isclass(obj):
            obj.__tobiko_fixture__ = True
            obj.__tobiko_fixture_name__ = name
    return name


def get_fixture_class(obj: FixtureType) -> typing.Type[fixtures.Fixture]:
    """It gets fixture class"""
    if isinstance(obj, str):
        obj = _loader.load_object(obj)

    if not inspect.isclass(obj):
        obj = type(obj)

    assert issubclass(obj, fixtures.Fixture)
    return obj


def get_fixture_dir(obj: FixtureType) -> str:
    '''Get directory of fixture class source code file'''
    return os.path.dirname(inspect.getfile(get_fixture_class(obj)))


@typing.overload
def remove_fixture(obj: typing.Type[F],
                   fixture_id: typing.Any = None,
                   manager: 'FixtureManager' = None) -> typing.Optional[F]:
    pass


@typing.overload
def remove_fixture(obj: F,
                   fixture_id: typing.Any = None,
                   manager: 'FixtureManager' = None) -> typing.Optional[F]:
    pass


def remove_fixture(obj: FixtureType,
                   fixture_id: typing.Any = None,
                   manager: 'FixtureManager' = None) -> typing.Optional[F]:
    """Unregister fixture identified by given :param obj: if any"""
    return fixture_manager(obj, manager).remove_fixture(
        obj, fixture_id=fixture_id)


@typing.overload
def setup_fixture(obj: typing.Type[F],
                  fixture_id: typing.Any = None,
                  manager: 'FixtureManager' = None,
                  **kwargs) -> F:
    pass


@typing.overload
def setup_fixture(obj: F,
                  fixture_id: typing.Any = None,
                  manager: 'FixtureManager' = None,
                  **kwargs) -> F:
    pass


def setup_fixture(obj: FixtureType,
                  fixture_id: typing.Any = None,
                  manager: 'FixtureManager' = None,
                  alternative: FixtureType = None,
                  **kwargs) \
        -> F:
    """I setups registered fixture

    """
    if alternative is None:
        objs = [obj]
    else:
        objs = [obj, alternative]
    with _exception.handle_multiple_exceptions(
            handle_exception=handle_setup_error):
        errors = []
        for _obj in objs:
            fixture: F = typing.cast(F,
                                     get_fixture(_obj,
                                                 fixture_id=fixture_id,
                                                 manager=manager,
                                                 **kwargs))
            try:
                fixture.setUp()
                break
            except testtools.MultipleExceptions:
                errors.append(sys.exc_info())
        else:
            raise testtools.MultipleExceptions(*errors)

    return fixture


def handle_setup_error(ex_type, ex_value, ex_tb):
    if issubclass(ex_type, fixtures.SetupError):
        details = ex_value.args[0]
        if details:
            details = {k: v.as_text() for k, v in details.items()}
            pretty_details = json.dumps(details, indent=4, sort_keys=True)
            LOG.debug(f"Fixture setup error details:\n{pretty_details}\n")
    else:
        LOG.exception("Unhandled setup exception",
                      exc_info=(ex_type, ex_value, ex_tb))


@typing.overload
def reset_fixture(obj: typing.Type[F],
                  fixture_id: typing.Any = None,
                  manager: 'FixtureManager' = None,
                  **kwargs) -> F:
    pass


@typing.overload
def reset_fixture(obj: F,
                  fixture_id: typing.Any = None,
                  manager: 'FixtureManager' = None,
                  **kwargs) -> F:
    pass


def reset_fixture(obj: FixtureType,
                  fixture_id: typing.Any = None,
                  manager: 'FixtureManager' = None,
                  **kwargs) -> F:
    """It cleanups and setups registered fixture"""
    fixture: F = get_fixture(
        obj, fixture_id=fixture_id, manager=manager, **kwargs)
    with _exception.handle_multiple_exceptions():
        fixture.reset()
    return fixture


@typing.overload
def cleanup_fixture(obj: typing.Type[F],
                    fixture_id: typing.Any = None,
                    manager: 'FixtureManager' = None) -> F:
    pass


@typing.overload
def cleanup_fixture(obj: F,
                    fixture_id: typing.Any = None,
                    manager: 'FixtureManager' = None) -> F:
    pass


def cleanup_fixture(obj: FixtureType,
                    fixture_id: typing.Any = None,
                    manager: 'FixtureManager' = None) -> F:
    """It cleans up registered fixture"""
    fixture = get_fixture(obj, fixture_id=fixture_id, manager=manager)
    with _exception.handle_multiple_exceptions():
        fixture.cleanUp()
    return fixture


@typing.overload
def use_fixture(obj: typing.Type[F],
                fixture_id: typing.Any = None,
                manager: 'FixtureManager' = None,
                **kwargs) -> F:
    pass


@typing.overload
def use_fixture(obj: F,
                fixture_id: typing.Any = None,
                manager: 'FixtureManager' = None,
                **kwargs) -> F:
    pass


def use_fixture(obj: FixtureType,
                fixture_id: typing.Any = None,
                manager: 'FixtureManager' = None,
                **kwargs) -> F:
    """It setups registered fixture and then register it for cleanup

    At the end of the test case execution it will call cleanup_fixture
    with on the fixture
    """
    fixture = setup_fixture(
        obj, fixture_id=fixture_id, manager=manager, **kwargs)
    _case.add_cleanup(cleanup_fixture, fixture)
    return fixture


@typing.overload
def get_name_and_object(obj: typing.Type[F]) -> typing.Tuple[str, F]:
    pass


@typing.overload
def get_name_and_object(obj: F) -> typing.Tuple[str, F]:
    pass


def get_name_and_object(obj: typing.Any) -> typing.Tuple[str, typing.Any]:
    '''Get (name, obj) tuple identified by given :param obj:'''
    if isinstance(obj, str):
        return obj, _loader.load_object(obj)
    else:
        return get_object_name(obj), obj


def visit_objects(objects):
    if not isinstance(objects, list):
        raise TypeError("parameter 'objects' is not a list")

    visited = set()
    while objects:
        obj = objects.pop()
        try:
            name, obj = get_name_and_object(obj)
        except Exception:
            LOG.exception('Unable to get (name, object) pair from {!r}'.format(
                obj))
        else:
            if name not in visited:
                visited.add(name)
                yield name, obj


def list_required_fixtures(objects):
    '''List fixture names required by given objects'''
    result = []
    objects = list(objects)
    for name, obj in visit_objects(objects):
        if is_fixture(obj):
            result.append(name)
            if not inspect.isclass(obj):
                obj = type(obj)

        elif is_test_method(obj):
            # Test methods also require test class fixtures
            if '.' in name:
                parent_name = name.rsplit('.', 1)[0]
                objects.append(parent_name)

        objects.extend(get_required_fixtures(obj))

    result.sort()
    return result


def is_test_method(obj) -> bool:
    '''Returns whenever given object is a test method'''
    return ((inspect.isfunction(obj) or inspect.ismethod(obj)) and
            obj.__name__.startswith('test_'))


def get_required_fixtures(obj):
    '''Get fixture names required by given :param obj:'''
    required_names = getattr(obj, '__tobiko_required_fixtures__', None)
    if required_names is None:
        if is_test_method(obj):
            # Get fixtures from default values that are fixtures
            defaults = getattr(obj, '__defaults__', None) or []
            required = {default
                        for default in defaults
                        if is_fixture(default)}

        elif inspect.isclass(obj):
            # Get fixtures from members of type RequiredFixtureProperty
            required = {prop.fixture
                        for prop in get_required_fixture_properties(obj)}
        else:
            # Other types have no fixtures
            required = set()

        # Return every fixture name only once
        required_names = sorted([get_fixture_name(fixture)
                                 for fixture in required])
        try:
            # try to cache list for later use
            obj.__tobiko_required_fixtures__ = required_names
        except AttributeError:
            pass

    return required_names


def get_required_fixture_properties(cls):
    """Get list of members of type RequiredFixtureProperty of given class"""

    # inspect.getmembers() would iterate over such many testtools.TestCase
    # members too, so let exclude members from those very common base classes
    # that we know doesn't have members of type RequiredFixtureProperty
    base_classes = cls.__mro__
    for base_class in [testtools.TestCase, SharedFixture]:
        if issubclass(cls, base_class):
            base_classes = base_classes[:base_classes.index(base_class)]
            break

    # Get all members for selected class without calling properties or methods
    members = {}
    for base_class in reversed(base_classes):
        members.update(base_class.__dict__)

    # Return all members that are instances of RequiredFixtureProperty
    return [member
            for _, member in sorted(members.items())
            if isinstance(member, RequiredFixture)]


def init_fixture(obj: typing.Union[typing.Type[F], F],
                 name: str,
                 fixture_id: typing.Any = None,
                 **kwargs) -> F:
    fixture: F
    if isinstance(obj, fixtures.Fixture):
        fixture = obj(**kwargs)
    elif inspect.isclass(obj) and issubclass(obj, fixtures.Fixture):
        try:
            fixture = obj(**kwargs)
        except Exception as ex:
            raise TypeError(f"Error creating fixture '{name}' from class "
                            f"{obj!r}.") from ex
    else:
        raise TypeError(f"Invalid fixture object type: '{obj!r}'")
    fixture.__tobiko_fixture__ = True
    fixture.__tobiko_fixture_name__ = name
    fixture.__tobiko_fixture_id__ = fixture_id
    return fixture


def fixture_property(*args, **kwargs):
    return FixtureProperty(*args, **kwargs)


def required_fixture(cls: typing.Type[G], setup=True, **params) \
        -> 'RequiredFixture[G]':
    """Creates a property that gets fixture identified by given :param cls:
    """
    return RequiredFixture[F](cls, setup=setup, **params)


def get_fixture_id(obj: typing.Any) -> typing.Any:
    return getattr(obj, '__tobiko_fixture_id__', None)


def get_object_name(obj) -> str:
    '''Gets a fully qualified name for given :param obj:'''
    if isinstance(obj, str):
        return obj

    name = getattr(obj, '__tobiko_fixture_name__', None)
    if isinstance(name, str):
        assert isinstance(name, str)
        return name

    assert name is None, f"{name} is not None"
    if (not inspect.isfunction(obj) and
            not inspect.ismethod(obj) and
            not inspect.isclass(obj)):
        obj = type(obj)

    module = inspect.getmodule(obj)
    if module is not None:
        name = getattr(obj, '__qualname__', None)
        if isinstance(name, str):
            return module.__name__ + '.' + name

    raise TypeError(f"Unable to get fixture name from object {obj!r}")


class FixtureManager:

    def __init__(self):
        self.fixtures: typing.Dict[str, F] = {}

    def get_fixture(self,
                    obj: FixtureType,
                    fixture_id: typing.Any = None,
                    **kwargs) -> F:
        name, obj = get_name_and_object(obj)
        if fixture_id:
            name += f'-{fixture_id}'
        try:
            return self.fixtures[name]
        except KeyError:
            fixture: F = self.init_fixture(obj=obj,
                                           name=name,
                                           fixture_id=fixture_id,
                                           **kwargs)
            assert isinstance(fixture, fixtures.Fixture)
            self.fixtures[name] = fixture
            return fixture

    def init_fixture(self, obj: typing.Union[typing.Type[F], F],
                     name: str,
                     fixture_id: typing.Any,
                     **kwargs) -> F:
        return init_fixture(obj=obj,
                            name=name,
                            fixture_id=fixture_id,
                            **kwargs)

    def remove_fixture(self,
                       obj: FixtureType,
                       fixture_id: typing.Any = None) -> typing.Optional[F]:
        name = get_object_name(obj)
        if fixture_id:
            name += '-' + str(fixture_id)
        return self.fixtures.pop(name, None)


def fixture_manager(obj: FixtureType,
                    manager: FixtureManager = None) -> FixtureManager:
    if manager is None:
        if isinstance(obj, str):
            obj = _loader.load_object(obj)
        if hasattr(obj, 'get_fixture_manager'):
            manager = obj.get_fixture_manager()
        else:
            manager = FIXTURES
    return _exception.check_valid_type(manager, FixtureManager)


FIXTURES = FixtureManager()


class SharedFixture(fixtures.Fixture):
    """Base class for fixtures intended to be shared between multiple tests

    Make sure that fixture setUp method can be called more than once, but
    actually executing _setUp method only the first time. This allows the
    fixture to be passed to useFixture methods multiple times without caring
    about if has already been used before.

    Fixture set up can anyway be forced by calling 'setup_shared_fixture'
    method.

    Because cleanup policy in a shared fixture is different from a common
    fixture, cleanUp method simply doesn't nothing.

    Actual fixture cleanup is executed by calling
    cleanup_shared_fixture method.

    """

    _setup_executed = False
    _cleanup_executed = False

    __tobiko_fixture__ = True
    __tobiko_fixture_name__: typing.Optional[str] = None
    __tobiko_fixture_id__: typing.Any = None

    @classmethod
    def get_fixture_manager(cls) -> FixtureManager:
        return FIXTURES

    def __init__(self):
        super().__init__()
        # make sure class states can be used before setUp
        self._clear_cleanups()

    @classmethod
    def get(cls, manager=None, fixture_id=None):
        return get_fixture(cls, manager=manager, fixture_id=fixture_id)

    def _remove_state(self):
        # make sure class states can be used after cleanUp
        super(SharedFixture, self)._clear_cleanups()

    def setUp(self):
        """Executes _setUp/setup_fixture method only the first time is called

        """
        if not self._setup_executed:
            LOG.debug('Set up fixture %r', self.fixture_name)
            super(SharedFixture, self).setUp()
            self._cleanup_executed = False
            self._setup_executed = True

    def cleanUp(self, raise_first=True):
        """Executes registered cleanups if any"""
        from tobiko import config
        if config.get_bool_env('TOBIKO_PREVENT_CREATE'):
            LOG.debug('Skipping %r fixture cleanup due to '
                      'TOBIKO_PREVENT_CREATE', self.fixture_name)
        elif not self._cleanup_executed:
            LOG.debug('Clean up fixture %r', self.fixture_name)
            self.addCleanup(self.cleanup_fixture)
        result = super(SharedFixture, self).cleanUp(raise_first=raise_first)
        self._setup_executed = False
        self._cleanup_executed = True
        return result

    def __enter__(self):
        return setup_fixture(self)

    def __exit__(self, exc_type, exc_val, exc_tb):  # noqa
        cleanup_fixture(self)
        return False  # propagate exceptions from the with body.

    def _setUp(self):
        self.setup_fixture()

    @property
    def fixture_name(self):
        return get_fixture_name(self)

    @property
    def fixture_id(self):
        return get_fixture_id(self)

    def setup_fixture(self):
        pass

    def cleanup_fixture(self):
        pass


class FixtureProperty(property):

    def __get__(self, instance, owner):
        instance = instance or get_fixture(owner)
        return super(FixtureProperty, self).__get__(instance, owner)


class RequiredFixture(property, typing.Generic[G]):

    def __init__(self, cls: typing.Type[G], setup=True, **kwargs):
        self.cls = cls
        self.kwargs = kwargs
        if setup:
            fget = self.setup_fixture
        else:
            fget = self.get_fixture
        super().__init__(fget=fget)

    def get_fixture(self, _instance=None) -> G:
        return get_fixture(self.cls, **self.kwargs)
    fixture = property(fget=get_fixture)

    def setup_fixture(self, _instance=None) -> G:
        fixture = self.fixture
        setup_fixture(fixture, **self.kwargs)
        if (hasattr(_instance, 'addCleanup') and
                hasattr(_instance, 'getDetails')):
            _instance.addCleanup(_detail.gather_details,
                                 fixture.getDetails(),
                                 _instance.getDetails())
        return fixture

    @property
    def __tobiko_required_fixtures__(self) -> typing.List[typing.Type[G]]:
        return [self.cls]
