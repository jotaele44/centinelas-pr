import copy

import pytest

from centinelas.space_observations import IntakeEngine
from centinelas.space_observations.producer import JsonlLedger
from centinelas.space_observations.retry import retry_failed
from centinelas.space_observations.routing import route_to_embedded_producer


def lead(lead_id="CENT-SPACE-2026-0123456789ABCDEF", dedup="3" * 64):
    return {
        "schema_version": "1.0.0",
        "lead_id": lead_id,
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
        "downstream_route": {
            "primary": "satellite-observations-pr",
            "correlation_target": "thehub-pr",
            "route_status": "new",
        },
        "evidence_tier": "T1",
        "confidence_score": 95,
        "review_status": "qualified",
        "content_fingerprint": "2" * 64,
        "dedup_key": dedup,
        "raw_binary_storage_prohibited": True,
        "confirmation_claim_prohibited": True,
        "analyst_assertion": None,
        "negative_inference": False,
    }


def test_route_bridge_is_immutable_and_rejects_unrelated_routes():
    source = lead()
    before = copy.deepcopy(source)
    routed = route_to_embedded_producer(source)
    assert source == before
    assert routed is not source
    assert routed["downstream_route"]["primary"] == "centinelas-space-observations"

    unrelated = lead()
    unrelated["downstream_route"]["primary"] = "moneysweep-pr"
    with pytest.raises(ValueError, match="unrelated primary route"):
        route_to_embedded_producer(unrelated)


def test_failed_target_only_retry_selects_retryable_rows(tmp_path):
    retryable = route_to_embedded_producer(lead())
    unrelated = route_to_embedded_producer(
        lead("CENT-SPACE-2026-FEDCBA9876543210", "4" * 64)
    )
    engine = IntakeEngine(tmp_path, production=True)
    JsonlLedger(
        tmp_path / "data" / "space_observations" / "ledgers" / "failures.jsonl"
    ).record(
        {
            "run_id": "failed-run",
            "lead_id": retryable["lead_id"],
            "failure_class": "INTAKE_INTERNAL_ERROR",
            "detail": "transient fixture",
            "retryable": True,
        }
    )
    JsonlLedger(
        tmp_path / "data" / "space_observations" / "ledgers" / "failures.jsonl"
    ).record(
        {
            "run_id": "failed-run",
            "lead_id": unrelated["lead_id"],
            "failure_class": "INVALID_SCHEMA",
            "detail": "permanent fixture",
            "retryable": False,
        }
    )

    results = retry_failed(
        engine,
        [retryable, unrelated],
        failed_run_id="failed-run",
        retry_run_id="retry-run",
    )
    assert len(results) == 1
    assert results[0].acknowledgement["lead_id"] == retryable["lead_id"]
    assert results[0].disposition == "accepted"
