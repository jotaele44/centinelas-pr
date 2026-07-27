import copy
import json

import pytest

from centinelas.space_observations import IntakeEngine, export_federation
from centinelas.space_observations.routing import route_to_embedded_producer


def lead():
    return {
        "schema_version": "1.0.0",
        "lead_id": "CENT-SPACE-2026-0123456789ABCDEF",
        "category": "SPACE_AND_REMOTE_SENSING",
        "subcategory": "SATELLITE_DATASET_RELEASE",
        "source_id": "CENT-SRC-SPACE-TEST",
        "source_url": "https://example.test/item",
        "canonical_url": "https://example.test/item",
        "discovered_at": "2026-07-27T00:00:00Z",
        "title": "Dataset release",
        "discovery_provenance": {"content_sha256": "1" * 64},
        "access_status": "public_direct",
        "temporal_coverage": {},
        "geographic_coverage": {},
        "sensor": {"sensor_type": "unknown", "capability_known": False},
        "potential_case_links": [],
        "downstream_route": {"primary": "satellite-observations-pr", "correlation_target": "thehub-pr", "route_status": "new"},
        "evidence_tier": "T1",
        "confidence_score": 95,
        "review_status": "qualified",
        "content_fingerprint": "2" * 64,
        "dedup_key": "3" * 64,
        "raw_binary_storage_prohibited": True,
        "confirmation_claim_prohibited": True,
        "analyst_assertion": None,
        "negative_inference": False,
    }


def test_route_bridge_and_two_clean_replays(tmp_path):
    routed = route_to_embedded_producer(lead())
    first = IntakeEngine(tmp_path, production=True).process(routed, run_id="run-1")
    second = IntakeEngine(tmp_path, production=True).process(routed, run_id="run-2")
    assert first.disposition == "accepted"
    assert second.disposition == "duplicate"
    assert first.acknowledgement["receiver"] == "centinelas-space-observations"
    assert first.acquisition["network_acquisition_performed"] is False
    assert first.acquisition["analytic_boundaries"]["correlation_owner"] == "thehub-pr"


def test_persistence_accounting_and_export(tmp_path):
    routed = route_to_embedded_producer(lead())
    bad = copy.deepcopy(routed)
    bad["review_status"] = "new"
    results = IntakeEngine(tmp_path, production=True).process_many([routed, bad], run_id="run")
    assert [result.disposition for result in results] == ["accepted", "rejected"]
    run = json.loads((tmp_path / "data/space_observations/ledgers/runs.jsonl").read_text())
    assert run["input_count"] == run["accepted"] + run["duplicate"] + run["rejected"] + run["failed"]
    manifest = export_federation(tmp_path, tmp_path / "export")
    assert manifest["producer"] == "centinelas-space-observations"
    assert manifest["network_acquisition_performed"] is False


def test_case_authority_dsp_negative_and_synthetic_guards(tmp_path):
    linked = route_to_embedded_producer(lead())
    linked["potential_case_links"] = [{"producer": "ovnis-pr", "case_id": "OVNIS-TEST", "not_a_confirmation": True}]
    assert IntakeEngine(tmp_path).process(linked, run_id="case").disposition == "accepted"

    dsp = route_to_embedded_producer(lead())
    dsp["dedup_key"] = "4" * 64
    dsp["sensor"] = {"sensor_type": "infrared_warning", "capability_known": True, "capability_source_ref": None}
    assert IntakeEngine(tmp_path).process(dsp, run_id="dsp").disposition == "rejected"

    negative = route_to_embedded_producer(lead())
    negative["dedup_key"] = "5" * 64
    negative["negative_inference"] = "absence proves no event"
    assert IntakeEngine(tmp_path).process(negative, run_id="negative").disposition == "rejected"

    synthetic = route_to_embedded_producer(lead())
    synthetic["dedup_key"] = "6" * 64
    synthetic["synthetic"] = True
    assert IntakeEngine(tmp_path, production=True).process(synthetic, run_id="synthetic").disposition == "rejected"


def test_route_mismatch_isolated_failure(tmp_path):
    mismatch = lead()
    result = IntakeEngine(tmp_path).process(mismatch, run_id="mismatch")
    assert result.disposition == "rejected"
    assert result.acknowledgement["reason_code"] == "ROUTE_MISMATCH"
