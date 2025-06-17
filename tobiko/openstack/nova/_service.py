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

import json
import typing

from keystoneauth1 import exceptions as ks_exceptions
from novaclient import exceptions as nc_exceptions
from oslo_log import log

import tobiko
from tobiko.openstack.nova import _client


LOG = log.getLogger(__name__)


class NovaServiceException(tobiko.TobikoException):
    pass


class NovaServicesNotfound(NovaServiceException):
    message = "Nova services not found ({attributes})"


class NovaServicesFailed(NovaServiceException):
    message = "Nova services are failed:\n{details}"


def services_details(services: typing.List):
    # pylint: disable=protected-access
    return json.dumps([service._info for service in services],
                      indent=4, sort_keys=True)


def wait_for_services_up(retry: typing.Optional[tobiko.Retry] = None,
                         **list_services_params):
    for attempt in tobiko.retry(other_retry=retry,
                                default_timeout=300.,
                                default_interval=3.):
        try:
            services = _client.list_services(**list_services_params)
        except (ks_exceptions.connection.ConnectFailure,
                nc_exceptions.ClientException):
            # Re-raises this exception in case this is the last attempt
            attempt.check_limits()
            continue
        LOG.debug(f"Found {len(services)} Nova services")
        try:
            if not services:
                raise NovaServicesNotfound(
                    attributes=json.dumps(list_services_params))

            heathy_services = services.with_attributes(state='up')
            LOG.debug(f"Found {len(heathy_services)} healthy Nova services")

            failed_services = [service
                               for service in services
                               if service not in heathy_services]
            LOG.debug(f"Found {len(failed_services)} failed Nova services")
            if failed_services:
                details = services_details(failed_services)
                LOG.info(f"Failed Nova services:\n{details}")
                raise NovaServicesFailed(details=details)
            LOG.info('All nova services are up!')
            break  # all Nova services are healthy

        except NovaServiceException:
            # Re-raises this exception in case this is the last attempt
            attempt.check_limits()
            continue
