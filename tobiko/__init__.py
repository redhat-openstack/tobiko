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

import os
import sys

from tobiko.common import _cached
from tobiko.common import _case
from tobiko.common import _config
from tobiko.common import _detail
from tobiko.common import _exception
from tobiko.common import _fixture
from tobiko.common import _ini
from tobiko.common import _loader
from tobiko.common import _lockutils
from tobiko.common import _logging
from tobiko.common import _operation
from tobiko.common import _os
from tobiko.common import _retry
from tobiko.common import _select
from tobiko.common import _shelves
from tobiko.common import _skip
from tobiko.common import _time
from tobiko.common import _utils
from tobiko.common import _version
from tobiko.common import _yaml
from tobiko.common import _background


TOBIKO_PACKAGE_DIR = os.path.dirname(os.path.realpath(__file__))

# Ensure any tobiko package subdir is in sys.path
for path_dir in list(sys.path):
    path_dir = os.path.realpath(path_dir)
    if path_dir.startswith(TOBIKO_PACKAGE_DIR):
        sys.path.remove(path_dir)

BackgroundProcessFixture = _background.BackgroundProcessFixture

cached = _cached.cached
CachedProperty = _cached.CachedProperty

TestCase = _case.TestCase
TestCaseManager = _case.TestCaseManager
add_cleanup = _case.add_cleanup
assert_test_case_was_skipped = _case.assert_test_case_was_skipped
fail = _case.fail
FailureException = _case.FailureException
get_parent_test_case = _case.get_parent_test_case
get_sub_test_id = _case.get_sub_test_id
get_test_case = _case.get_test_case
pop_test_case = _case.pop_test_case
push_test_case = _case.push_test_case
retry_test_case = _case.retry_test_case
run_test = _case.run_test
sub_test = _case.sub_test

details_content = _detail.details_content

tobiko_config = _config.tobiko_config
tobiko_config_dir = _config.tobiko_config_dir
tobiko_config_path = _config.tobiko_config_path

TobikoException = _exception.TobikoException
check_valid_type = _exception.check_valid_type
exc_info = _exception.exc_info
ExceptionInfo = _exception.ExceptionInfo
handle_multiple_exceptions = _exception.handle_multiple_exceptions
list_exc_infos = _exception.list_exc_infos

is_fixture = _fixture.is_fixture
get_fixture = _fixture.get_fixture
fixture_property = _fixture.fixture_property
required_fixture = _fixture.required_fixture
get_fixture_name = _fixture.get_fixture_name
get_fixture_class = _fixture.get_fixture_class
get_fixture_dir = _fixture.get_fixture_dir
get_object_name = _fixture.get_object_name
remove_fixture = _fixture.remove_fixture
reset_fixture = _fixture.reset_fixture
setup_fixture = _fixture.setup_fixture
cleanup_fixture = _fixture.cleanup_fixture
use_fixture = _fixture.use_fixture
list_required_fixtures = _fixture.list_required_fixtures
SharedFixture = _fixture.SharedFixture
FixtureManager = _fixture.FixtureManager
RequiredFixture = _fixture.RequiredFixture

parse_ini_file = _ini.parse_ini_file

CaptureLogFixture = _logging.CaptureLogFixture

load_object = _loader.load_object
load_module = _loader.load_module

interworker_synched = _lockutils.interworker_synched

makedirs = _os.makedirs
open_output_file = _os.open_output_file

runs_operation = _operation.runs_operation
before_operation = _operation.before_operation
after_operation = _operation.after_operation
with_operation = _operation.with_operation
RunsOperations = _operation.RunsOperations
Operation = _operation.Operation
get_operation = _operation.get_operation
get_operation_name = _operation.get_operation_name
operation_config = _operation.operation_config

retry = _retry.retry
retry_attempt = _retry.retry_attempt
retry_on_exception = _retry.retry_on_exception
Retry = _retry.Retry
RetryAttempt = _retry.RetryAttempt
RetryCountLimitError = _retry.RetryCountLimitError
RetryLimitError = _retry.RetryLimitError
RetryTimeLimitError = _retry.RetryTimeLimitError

Selection = _select.Selection
select = _select.select
select_uniques = _select.select_uniques
ObjectNotFound = _select.ObjectNotFound
MultipleObjectsFound = _select.MultipleObjectsFound

addme_to_shared_resource = _shelves.addme_to_shared_resource
removeme_from_shared_resource = _shelves.removeme_from_shared_resource
remove_test_from_all_shared_resources = (
    _shelves.remove_test_from_all_shared_resources)
initialize_shelves = _shelves.initialize_shelves

SkipException = _skip.SkipException
skip_if = _skip.skip_if
skip_on_error = _skip.skip_on_error
skip_test = _skip.skip_test
skip_unless = _skip.skip_unless
skip = _skip.skip

min_seconds = _time.min_seconds
max_seconds = _time.max_seconds
Seconds = _time.Seconds
SecondsValueError = _time.SecondsValueError
sleep = _time.sleep
time = _time.time
to_seconds = _time.to_seconds
to_seconds_float = _time.to_seconds_float
true_seconds = _time.true_seconds

get_short_hostname = _utils.get_short_hostname

InvalidVersion = _version.InvalidVersion
VersionMismatch = _version.VersionMismatch
VersionType = _version.VersionType
Version = _version.Version
check_version = _version.check_version
get_version = _version.get_version
match_version = _version.match_version
parse_version = _version.parse_version

dump_yaml = _yaml.dump_yaml
load_yaml = _yaml.load_yaml

from tobiko import config  # noqa
config.init_config()
