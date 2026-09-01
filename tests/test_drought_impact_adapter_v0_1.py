from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

jsonschema = pytest.importorskip("jsonschema")

from research.drought.impact_adapter import (  # noqa: E402
    AGUAYLUZ_CONTRACT_SNAPSHOT,
    IMPACT_TYPES,
    build_impact_event,
    reject_embedded_hydrology,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/drought-impact-v0.1.schema.json").read_text())


def _event(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source_claim_id": "NIDIS_PR_20260723_008",
        "impact_type": "wildfire_activity",
        "observed_at": "2026-07-21T17:00:00-04:00",
        "municipality_geoids": ["72113", "72079", "72113"],
        "linked_aguayluz_record_ids": ["AYL_DROUGHT_IMPACT_EVENT_0123456789abcdef0123"],
        "uncertainty": {"count_qualifier": "approximate"},
    }
    kwargs.update(overrides)
    return build_impact_event(**kwargs)


def test_schema_is_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_runtime_and_schema_impact_types_match() -> None:
    assert set(SCHEMA["properties"]["impact_type"]["enum"]) == IMPACT_TYPES


def test_event_is_reference_only_deterministic_and_schema_valid() -> None:
    first = _event()
    second = _event()

    assert first == second
    assert first["canonical_hydrology_embedded"] is False
    assert first["municipality_geoids"] == ["72079", "72113"]
    assert first["aguayluz_link_contract"] == AGUAYLUZ_CONTRACT_SNAPSHOT
    assert first["aguayluz_link_contract"]["certification_state"] == "PROVISIONAL"
    assert first["aguayluz_link_contract"]["identity_state"] == "CANDIDATE_NOT_IDENTITY"

    content_sha256 = first.pop("content_sha256")
    canonical = json.dumps(first, sort_keys=True, separators=(",", ":")).encode()
    assert content_sha256 == hashlib.sha256(canonical).hexdigest()
    first["content_sha256"] = content_sha256
    jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker()).validate(
        first
    )


@pytest.mark.parametrize("impact_type", ["flood", "", None])
def test_invalid_impact_type_fails_closed(impact_type: Any) -> None:
    with pytest.raises(ValueError, match="impact type"):
        _event(impact_type=impact_type)


@pytest.mark.parametrize(
    "record_id",
    [
        "copied-narrative-value",
        "AYL_DROUGHT_UNKNOWN_0123456789abcdef0123",
        "AYL_DROUGHT_IMPACT_EVENT_short",
        "AYL_DROUGHT_IMPACT_EVENT_0123456789ABCDEF0123",
    ],
)
def test_noncanonical_link_fails_closed(record_id: str) -> None:
    with pytest.raises(ValueError, match="AYL_DROUGHT"):
        _event(linked_aguayluz_record_ids=[record_id])


def test_nested_embedded_hydrology_is_rejected_by_runtime_and_schema() -> None:
    uncertainty = {"reported": [{"details": {"streamflow_value": 25}}]}
    with pytest.raises(ValueError, match="belongs to AguaYLuz"):
        _event(uncertainty=uncertainty)

    direct = _event()
    direct["uncertainty"] = uncertainty
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(SCHEMA).validate(direct)


def test_reference_cycles_fail_closed() -> None:
    uncertainty: dict[str, Any] = {}
    uncertainty["self"] = uncertainty
    with pytest.raises(ValueError, match="reference cycle"):
        _event(uncertainty=uncertainty)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"uncertainty": {"bad": {"not-json"}}}, "JSON-compatible"),
        ({"uncertainty": {1: "non-string key"}}, "keys must be strings"),
        ({"uncertainty": {"confidence": float("nan")}}, "finite"),
        ({"uncertainty": []}, "uncertainty must be an object"),
        ({"observed_at": "2026-07-21T17:00:00"}, "timezone"),
        ({"observed_at": "not-a-date"}, "timezone"),
        ({"municipality_geoids": None}, "municipality_geoids must be a list"),
        ({"municipality_geoids": ()}, "non-empty strings"),
        ({"municipality_geoids": ["7201"]}, "Puerto Rico GEOIDs"),
        ({"linked_aguayluz_record_ids": None}, "record_ids must be a list"),
        ({"linked_asset_ids": [""]}, "non-empty strings"),
        ({"evidence_tier": "T5"}, "evidence tier"),
    ],
)
def test_invalid_payloads_fail_closed(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _event(**overrides)


def test_hydrology_guard_accepts_reference_only_impact_content() -> None:
    reject_embedded_hydrology({"impact_summary": "reported stream drying"})


def test_schema_rejects_non_object_uncertainty() -> None:
    event = _event()
    event["uncertainty"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(SCHEMA).validate(event)
