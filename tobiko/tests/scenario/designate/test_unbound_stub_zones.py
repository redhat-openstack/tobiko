# Copyright (c) 2026 Red Hat
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
"""Configure Designate unbound stubZones on OpenStackControlPlane.

Patches ``spec.designate.template.designateUnbound.stubZones`` and waits for
the operator to render ``/etc/unbound/conf.d/10-stubzones.conf`` inside
designate-unbound pods. Podified-only; does not use the Designate Keystone API.
"""
import copy
import shlex
import typing

import openshift_client as oc
import testtools
from oslo_log import log

import tobiko
from tobiko import podified

LOG = log.getLogger(__name__)

# Stub zone FQDNs used by these tests (trailing '.' = absolute DNS name).
ORIGINAL_STUB_ZONE_NAME = 'tobiko-stub-original.example.com.'
UPDATED_STUB_ZONE_NAME = 'tobiko-stub-updated.example.com.'
# Operator-written unbound stub-zones file inside designate-unbound pods.
# Filename comes from designate-operator's template (mounted under conf.d):
# https://github.com/openstack-k8s-operators/designate-operator/blob/main/templates/designateunbound/config/10-stubzones.conf  # noqa: E501
UNBOUND_POD_CONF_FILE_PATH = '/etc/unbound/conf.d/10-stubzones.conf'

StubZoneEntry = typing.Dict[str, typing.Any]
DesignateUnbound = typing.Dict[str, typing.Any]


def _normalize_zone_name(zone: str) -> str:
    """Return zone name lower-cased, with a trailing '.'.

    :param zone: Zone name string (with or without trailing '.').
    :return: Lower-cased name with a trailing '.' added.
    """
    return zone.strip().rstrip('.').lower() + '.'


def _get_designate_unbound() -> DesignateUnbound:
    """Return a deep copy of designateUnbound from OpenStackControlPlane.

    Reads ``spec.designate.template.designateUnbound``.

    :return: designateUnbound dict, or ``{}`` if the section is missing.
    """
    designate = (
        podified.get_openstack_controlplane_spec().get('designate') or {})
    unbound = (designate.get('template') or {}).get('designateUnbound')
    return copy.deepcopy(unbound or {})


@tobiko.interworker_synched('designate_unbound_stub_zones')
def _patch_designate_unbound(
        designate_unbound: typing.Optional[DesignateUnbound]) -> None:
    """Set the designateUnbound section on the OpenStackControlPlane.

    :param designate_unbound: designateUnbound dict to apply, or None to clear.
    :return: None.
    """
    podified.patch_openstack_controlplane({
        'spec': {'designate': {'template': {
            'designateUnbound': designate_unbound}}}})


def _set_stub_zones(
        zones: typing.Optional[typing.List[StubZoneEntry]]) -> None:
    """Set designateUnbound.stubZones on the OpenStackControlPlane.

    :param zones: New stubZones list, or empty/None to clear.
    :return: None.
    """
    unbound = _get_designate_unbound()
    unbound['stubZones'] = list(zones) if zones else None
    _patch_designate_unbound(unbound)


def _unbound_stubzones_conf_exists(pods: typing.List[str]) -> bool:
    """Return whether unbound stub-zones conf exists on every unbound pod.

    Checks ``UNBOUND_POD_CONF_FILE_PATH`` on each pod.

    :param pods: Unbound pod names.
    :return: True if the conf file exists on all pods, else False.
    """
    for pod in pods:
        try:
            result = podified.execute_in_pod(
                pod,
                'test -f {} && echo yes'.format(
                    shlex.quote(UNBOUND_POD_CONF_FILE_PATH)))
        except oc.OpenShiftPythonException:
            return False
        if (result.out() or '').strip() != 'yes':
            return False
    return bool(pods)


def _zone_in_unbound_pods(
        zone: str, pods: typing.List[str], present: bool = True) -> bool:
    """Return whether *zone* matches *present* on every unbound pod.

    Searches ``UNBOUND_POD_CONF_FILE_PATH`` on all unbound replicas.

    :param zone: Zone name to search for.
    :param pods: Unbound pod names.
    :param present: If True, zone must be on every pod; if False, on none.
    :return: True if all pods match, else False. False if *pods* is empty.
    """
    if not pods:
        return False
    key = _normalize_zone_name(zone)
    for pod in pods:
        try:
            result = podified.execute_in_pod(
                pod, 'cat {}'.format(shlex.quote(UNBOUND_POD_CONF_FILE_PATH)))
            text = (result.out() or '').strip().lower()
        except oc.OpenShiftPythonException:
            text = ''
        found = key in text or key.rstrip('.') in text
        if found != present:
            return False
    return True


def _stub_zone_in_controlplane(zone: str) -> bool:
    """Return whether *zone* is in controlplane designateUnbound.stubZones.

    :param zone: Stub zone name to look up.
    :return: True if listed in stubZones, else False.
    """
    target_zone = _normalize_zone_name(zone)
    present = set()
    for entry in _get_designate_unbound().get('stubZones') or []:
        if isinstance(entry, dict) and entry.get('name'):
            present.add(_normalize_zone_name(entry['name']))
    return target_zone in present


def _wait_zone_presence_in_unbound_pods(
        zone: str, pods: typing.List[str], present: bool = True) -> bool:
    """Wait until *zone* is present or absent on every unbound pod.

    Polls all designate-unbound replicas until the operator has rendered the
    expected result into ``10-stubzones.conf`` on each pod, or times out.
    Used after add/update (``present=True``) and after delete/rename of the
    old name (``present=False``). Callers decide how to fail on timeout.

    :param zone: Zone name to wait for.
    :param pods: Unbound pod names.
    :param present: If True, wait until the zone appears on every pod; if
        False, wait until it is removed from every pod.
    :return: True if the condition was met; False on timeout.
    """
    target_zone = _normalize_zone_name(zone)
    expect = 'present' if present else 'absent'
    try:
        for attempt in tobiko.retry(interval=10., default_timeout=300.):
            if _zone_in_unbound_pods(target_zone, pods, present=present):
                LOG.info(
                    'Stub zone {!r} is {} in unbound conf on all pods'.format(
                        target_zone, expect))
                return True
            LOG.debug(
                'conf poll #{}: waiting for {!r} to be {} on all pods'.format(
                    attempt.number, target_zone, expect))
    except tobiko.RetryTimeLimitError:
        pass
    return False


def _fail_zone_not_in_unbound_pods(
        zone: str, pods: typing.List[str], present: bool = True) -> None:
    """Fail the test when a wait for zone presence/absence timed out.

    :param zone: Zone name that was waited for.
    :param pods: Unbound pod names.
    :param present: Expected presence used in the wait.
    :return: Never returns; always fails the test.
    """
    expect = 'present' if present else 'absent'
    tobiko.fail(
        'Stub zone {!r} still not {} in {!r} on all pods {!r} '
        'within 300s'.format(
            _normalize_zone_name(zone), expect, UNBOUND_POD_CONF_FILE_PATH,
            pods))


def _stub_zone_names_from_unbound(
        unbound: typing.Optional[DesignateUnbound]) -> typing.Set[str]:
    """Return normalized stub zone names from a designateUnbound dict.

    :param unbound: designateUnbound dict, or None.
    :return: Set of normalized zone names (may be empty).
    """
    names: typing.Set[str] = set()
    if not unbound:
        return names
    for entry in unbound.get('stubZones') or []:
        if isinstance(entry, dict) and entry.get('name'):
            names.add(_normalize_zone_name(entry['name']))
    return names


def _restore_designate_unbound_original_conf(
        snapshot: typing.Optional[DesignateUnbound],
        pods: typing.List[str]) -> None:
    """Restore pre-test designateUnbound conf and wait for Tobiko cleanup.

    Restores designateUnbound from *snapshot*, preserving any pre-existing
    ``stubZones``. ``stubZones`` is always set explicitly in the patch (to the
    snapshot value, or ``None`` if the snapshot had none) so a merge-patch
    removes Tobiko-only zones. Then waits until Tobiko's test zones are gone
    from unbound pods, unless those names were already in the snapshot.

    :param snapshot: Pre-test designateUnbound dict, or None.
    :param pods: Unbound pod names.
    :return: None. Fails the test if Tobiko zones remain after timeout.
    """
    if snapshot is None:
        restored = None
        preexisting: typing.Set[str] = set()
    else:
        restored = copy.deepcopy(snapshot)
        # Merge-patch omits missing keys; set stubZones explicitly so Tobiko
        # additions are cleared when the snapshot had none.
        restored['stubZones'] = snapshot.get('stubZones')
        preexisting = _stub_zone_names_from_unbound(restored)
    _patch_designate_unbound(restored)
    for zone in (ORIGINAL_STUB_ZONE_NAME, UPDATED_STUB_ZONE_NAME):
        if _normalize_zone_name(zone) in preexisting:
            continue
        if not _wait_zone_presence_in_unbound_pods(
                zone, pods, present=False):
            _fail_zone_not_in_unbound_pods(zone, pods, present=False)


def _add_stub_zone_to_controlplane(zone: str) -> None:
    """Append *zone* to designateUnbound.stubZones on the controlplane.

    :param zone: Zone name to add.
    :return: None (no-op if already present).
    """
    target_zone = _normalize_zone_name(zone)
    if _stub_zone_in_controlplane(target_zone):
        return
    zones = list(_get_designate_unbound().get('stubZones') or [])
    _set_stub_zones(zones + [{'name': target_zone}])


def _update_stub_zone_on_controlplane(old: str, new: str) -> None:
    """Rename stub zone *old* to *new* on the OpenStackControlPlane.

    :param old: Existing zone name.
    :param new: New zone name.
    :return: None. Fails the test if *old* is not found.
    """
    old = _normalize_zone_name(old)
    new = _normalize_zone_name(new)
    rebuilt = []
    renamed = False
    for entry in _get_designate_unbound().get('stubZones') or []:
        if not isinstance(entry, dict) or not entry.get('name'):
            rebuilt.append(entry)
            continue
        key = _normalize_zone_name(entry['name'])
        if key == old:
            if not renamed:
                rebuilt.append({'name': new})
                renamed = True
        elif key != new:
            rebuilt.append(entry)
    if not renamed:
        tobiko.fail(
            'Update: stub zone {!r} not found in stubZones'.format(old))
    _set_stub_zones(rebuilt)


def _delete_stub_zones_from_controlplane() -> None:
    """Clear designateUnbound.stubZones on the OpenStackControlPlane.

    :return: None.
    """
    _set_stub_zones(None)


@podified.skip_if_not_podified
class DesignateUnboundStubZoneConfigTest(testtools.TestCase):
    """Configure stubZones on the CR; assert unbound pod conf updates."""

    def setUp(self):
        """Skip unless this test's prerequisites match.

        Prerequisites (checked here, before any configuration):
        * podified deployment (class decorator)
        * OpenStackControlPlane has Designate enabled (or enabled unset)
        * at least one designate-unbound pod exists
        * ``UNBOUND_POD_CONF_FILE_PATH`` exists on those pods

        After those checks, snapshots the designateUnbound section of the
        controlplane prior to the test for cleanup after the test.
        """
        super(DesignateUnboundStubZoneConfigTest, self).setUp()
        designate = (
            podified.get_openstack_controlplane_spec().get('designate') or {})
        if not designate:
            self.skipTest(
                'Designate is not configured on OpenStackControlPlane')
        if 'enabled' in designate and not designate.get('enabled'):
            self.skipTest('Designate is disabled on OpenStackControlPlane')
        self.pods = sorted(
            pod.name() for pod in podified.get_pods()
            if 'unbound' in pod.name().lower())
        if not self.pods:
            self.skipTest('No designate-unbound pod found')
        if not _unbound_stubzones_conf_exists(self.pods):
            self.skipTest(
                'Unbound stub-zones conf not found at {!r} '
                'on pods {!r}'.format(
                    UNBOUND_POD_CONF_FILE_PATH, self.pods))
        unbound = (designate.get('template') or {}).get('designateUnbound')
        snap = None if unbound is None else copy.deepcopy(unbound)
        self.addCleanup(
            _restore_designate_unbound_original_conf, snap, self.pods)

    def test_add_stub_zone_to_controlplane(self):
        """Patch stubZones with a new zone and wait for unbound conf.

        Asserts the zone is listed on OpenStackControlPlane and appears in
        ``UNBOUND_POD_CONF_FILE_PATH`` on designate-unbound pods.
        """
        _add_stub_zone_to_controlplane(ORIGINAL_STUB_ZONE_NAME)
        self.assertTrue(_stub_zone_in_controlplane(ORIGINAL_STUB_ZONE_NAME))
        if not _wait_zone_presence_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=True):
            _fail_zone_not_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=True)

    def test_update_stub_zone_on_controlplane(self):
        """Rename a stubZones entry on the CR and wait for unbound conf.

        Asserts the new name is on the CR and in pod conf, and the old name is
        gone from both.
        """
        _add_stub_zone_to_controlplane(ORIGINAL_STUB_ZONE_NAME)
        if not _wait_zone_presence_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=True):
            _fail_zone_not_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=True)
        _update_stub_zone_on_controlplane(
            ORIGINAL_STUB_ZONE_NAME, UPDATED_STUB_ZONE_NAME)
        self.assertFalse(_stub_zone_in_controlplane(ORIGINAL_STUB_ZONE_NAME))
        self.assertTrue(_stub_zone_in_controlplane(UPDATED_STUB_ZONE_NAME))
        if not _wait_zone_presence_in_unbound_pods(
                UPDATED_STUB_ZONE_NAME, self.pods, present=True):
            _fail_zone_not_in_unbound_pods(
                UPDATED_STUB_ZONE_NAME, self.pods, present=True)
        if not _wait_zone_presence_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=False):
            _fail_zone_not_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=False)

    def test_delete_stub_zones_from_controlplane(self):
        """Clear stubZones on the CR and wait for unbound conf cleanup.

        Asserts the zone is removed from OpenStackControlPlane and from
        ``UNBOUND_POD_CONF_FILE_PATH`` on designate-unbound pods.
        """
        _add_stub_zone_to_controlplane(ORIGINAL_STUB_ZONE_NAME)
        if not _wait_zone_presence_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=True):
            _fail_zone_not_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=True)
        _delete_stub_zones_from_controlplane()
        self.assertFalse(_stub_zone_in_controlplane(ORIGINAL_STUB_ZONE_NAME))
        if not _wait_zone_presence_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=False):
            _fail_zone_not_in_unbound_pods(
                ORIGINAL_STUB_ZONE_NAME, self.pods, present=False)
