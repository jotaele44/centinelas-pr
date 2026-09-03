import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from centinelas.releases.pilot import (
    PilotPolicyError,
    load_manifest,
    readiness_certificate,
    source_readiness,
)

MANIFEST = Path("config/federal_records_source_enablement.json")
NOW = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)


def _approved_manifest():
    payload = json.loads(MANIFEST.read_text())
    payload["emergency_kill_switch"]["engaged"] = False
    for source_id in ("nara_ndc", "dia_reading_room", "air_force_blue_book"):
        source = payload["sources"][source_id]
        source.update(
            {
                "enabled": True,
                "approval_status": "approved",
                "approved_by": "owner-reviewer",
                "approved_at": "2026-07-28T15:00:00Z",
                "approval_expires_at": "2026-07-29T15:00:00Z",
                "policy_review_status": "approved",
            }
        )
    return payload


def test_committed_manifest_is_fail_closed():
    manifest = load_manifest(MANIFEST)
    certificate = readiness_certificate(manifest, now=NOW)
    assert certificate["pilot_ready"] is False
    assert manifest["pilot_enabled"] is False
    assert manifest["emergency_kill_switch"]["engaged"] is True
    assert manifest["linked_binary_fetch"] is False
    assert manifest["baseline_mutation_allowed"] is False


def test_approved_bounded_manifest_can_pass_readiness():
    manifest = _approved_manifest()
    certificate = readiness_certificate(manifest, now=NOW)
    assert certificate["pilot_ready"] is True
    assert all(row["ready"] for row in certificate["sources"].values())


def test_expired_approval_and_engaged_kill_switch_fail():
    manifest = _approved_manifest()
    manifest["sources"]["nara_ndc"]["approval_expires_at"] = "2026-07-28T15:30:00Z"
    manifest["emergency_kill_switch"]["engaged"] = True
    ready, reasons = source_readiness(manifest, "nara_ndc", now=NOW)
    assert ready is False
    assert "APPROVAL_EXPIRED" in reasons
    assert "EMERGENCY_KILL_SWITCH_ENGAGED" in reasons


def test_budget_caps_fail_closed():
    manifest = _approved_manifest()
    source = manifest["sources"]["dia_reading_room"]
    source["max_pages_per_run"] = 3
    source["max_records_per_run"] = 251
    source["daily_request_budget"] = 7
    ready, reasons = source_readiness(manifest, "dia_reading_room", now=NOW)
    assert ready is False
    assert "MAX_PAGES_EXCEEDS_PILOT_CAP" in reasons
    assert "MAX_RECORDS_EXCEEDS_PILOT_CAP" in reasons
    assert "DAILY_REQUEST_BUDGET_EXCEEDS_PILOT_CAP" in reasons


def test_robots_denied_sources_cannot_enter_pilot():
    manifest = _approved_manifest()
    manifest["sources"]["nara_catalog"] = copy.deepcopy(manifest["sources"]["nara_ndc"])
    ready, reasons = source_readiness(manifest, "nara_catalog", now=NOW)
    assert ready is False
    assert "SOURCE_NOT_IN_PILOT_ALLOWLIST" in reasons


def test_binary_or_baseline_enablement_is_rejected(tmp_path):
    payload = _approved_manifest()
    payload["linked_binary_fetch"] = True
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(PilotPolicyError, match="binary"):
        load_manifest(path)

    payload["linked_binary_fetch"] = False
    payload["baseline_mutation_allowed"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(PilotPolicyError, match="baseline"):
        load_manifest(path)
