# Copyright 2026 Red Hat
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
from unittest import mock

import testtools

from tobiko.common import _lockutils


class InterworkerSynchedTest(testtools.TestCase):

    def test_lock_name_includes_class_name(self):
        """Verify that interworker_synched includes fully qualified class name
        in lock"""

        captured_lock_names = []

        # Mock the lock function to capture the lock name
        def mock_lock(name):
            captured_lock_names.append(name)
            return contextlib.nullcontext()

        # Define test fixtures
        class BaseFixture:
            @_lockutils.interworker_synched('test_lock')
            def setup_fixture(self):
                return f"Setting up {self.__class__.__name__}"

        class ChildFixture1(BaseFixture):
            pass

        class ChildFixture2(BaseFixture):
            pass

        # Patch the lock function
        with mock.patch.object(_lockutils, 'lock', side_effect=mock_lock):
            # Create instances and call setup_fixture
            base = BaseFixture()
            child1 = ChildFixture1()
            child2 = ChildFixture2()

            base.setup_fixture()
            child1.setup_fixture()
            child2.setup_fixture()

        # Verify we got 3 lock names
        self.assertEqual(len(captured_lock_names), 3)

        # Verify all lock names are unique
        self.assertEqual(len(set(captured_lock_names)), 3,
                         "All lock names should be unique")

        # Verify each lock name starts with the base name and ends with
        # the class name
        self.assertTrue(captured_lock_names[0].startswith('test_lock:'))
        self.assertTrue(captured_lock_names[0].endswith('.BaseFixture'))
        self.assertTrue(captured_lock_names[1].endswith('.ChildFixture1'))
        self.assertTrue(captured_lock_names[2].endswith('.ChildFixture2'))

        # Verify the lock name includes the module path
        for lock_name in captured_lock_names:
            self.assertIn('tobiko.tests.unit.test_lockutils', lock_name)

    def test_lock_name_without_instance(self):
        """Verify that lock works when called without instance (no args)"""

        captured_lock_names = []

        # Mock the lock function to capture the lock name
        def mock_lock(name):
            captured_lock_names.append(name)
            return contextlib.nullcontext()

        # Define a function (not a method) with the decorator
        @_lockutils.interworker_synched('function_lock')
        def standalone_function():
            return "standalone"

        # Patch the lock function
        with mock.patch.object(_lockutils, 'lock', side_effect=mock_lock):
            standalone_function()

        # When called without instance, should use base lock name
        self.assertEqual(['function_lock'], captured_lock_names)

    def test_different_fixtures_get_different_locks(self):
        """Verify different fixture classes don't block each other"""

        # This test verifies the fix for the timeout issue where
        # AdvancedServerStackFixture and AdvancedExternalServerStackFixture
        # were blocked by the same lock

        captured_lock_names = []

        def mock_lock(name):
            captured_lock_names.append(name)
            return contextlib.nullcontext()

        class ServerFixture:
            @_lockutils.interworker_synched('server_setup')
            def setup_fixture(self):
                pass

        class ExternalServerFixture(ServerFixture):
            pass

        class PeerServerFixture(ServerFixture):
            pass

        with mock.patch.object(_lockutils, 'lock', side_effect=mock_lock):
            server = ServerFixture()
            external = ExternalServerFixture()
            peer = PeerServerFixture()

            server.setup_fixture()
            external.setup_fixture()
            peer.setup_fixture()

        # All three should have different lock names
        self.assertEqual(len(captured_lock_names), 3)
        self.assertEqual(len(set(captured_lock_names)), 3,
                         "All lock names should be unique")

        # Verify each lock name contains the base name and class name
        self.assertTrue(captured_lock_names[0].startswith('server_setup:'))
        self.assertTrue(captured_lock_names[0].endswith('.ServerFixture'))
        self.assertTrue(
            captured_lock_names[1].endswith('.ExternalServerFixture'))
        self.assertTrue(captured_lock_names[2].endswith('.PeerServerFixture'))

        # Verify all contain the module path
        for lock_name in captured_lock_names:
            self.assertIn('tobiko.tests.unit.test_lockutils', lock_name)
