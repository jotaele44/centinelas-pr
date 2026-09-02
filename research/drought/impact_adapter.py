"""Internal drought-impact adapter for Centinelas federation events.

The adapter emits impact references only. Canonical hydrologic values remain in
AguaYLuz, and producer record IDs remain provisional until that contract ships.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, get_args

ImpactType = Literal[
    "wildfire_activity",
    "agricultural_water_shortage",
    "crop_stress",
    "infrastructure_fire_damage",
    "stream_dry_report",
    "water_hauling",
    "forage_shortage",
    "municipal_rationing",
]

IMPACT_TYPES = frozenset(get_args(ImpactType))
EVIDENCE_TIERS = frozenset({"T1", "T2", "T3", "T4"})
AGUAYLUZ_RECORD_ID = re.compile(
    r"^AYL_DROUGHT_(?:CLASSIFICATION_OBSERVATION|HYDROLOGIC_INDICATOR|"
    r"IMPACT_EVENT|WATER_RESTRICTION|OUTLOOK|SOURCE_DOCUMENT)_[0-9a-f]{20}$"
)
MUNICIPALITY_GEOID = re.compile(r"^72[0-9]{3}$")
FORBIDDEN_HYDROLOGY_FIELDS = frozenset(
    {
        "streamflow_value",
        "groundwater_level",
        "reservoir_level",
        "soil_moisture_value",
        "drought_geometry",
        "forecast_probability",
    }
)
AGUAYLUZ_CONTRACT_SNAPSHOT = {
    "schema_version": "aguayluz.drought-record/v0.1",
    "producer_repo": "aguayluz-pr",
    "producer_pr": 148,
    "producer_head": "f8fda661accf672bef1b40464601d7372dd00140",
    "certification_state": "PROVISIONAL",
    "identity_state": "CANDIDATE_NOT_IDENTITY",
}


def _sha(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sorted_references(name: str, values: list[str] | None, *, optional: bool = False) -> list[str]:
    if values is None:
        if optional:
            return []
        raise ValueError(f"{name} must be a list")
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError(f"{name} must contain non-empty strings")
    return sorted(set(values))


def _validate_observed_at(observed_at: str | None) -> None:
    if observed_at is None:
        return
    if not isinstance(observed_at, str) or not observed_at:
        raise ValueError("observed_at must be an ISO 8601 date-time with timezone")
    try:
        parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO 8601 date-time with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must be an ISO 8601 date-time with timezone")


def reject_embedded_hydrology(payload: Mapping[str, Any]) -> None:
    """Fail closed when nested content duplicates canonical AguaYLuz observations."""

    active_containers: set[int] = set()

    def visit(value: Any, depth: int) -> None:
        if depth > 64:
            raise ValueError("payload nesting exceeds the supported depth")
        if isinstance(value, Mapping):
            container_id = id(value)
            if container_id in active_containers:
                raise ValueError("payload contains a reference cycle")
            active_containers.add(container_id)
            try:
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise ValueError("payload object keys must be strings")
                    if key in FORBIDDEN_HYDROLOGY_FIELDS:
                        raise ValueError(f"canonical hydrology belongs to AguaYLuz: {key}")
                    visit(child, depth + 1)
            finally:
                active_containers.remove(container_id)
        elif isinstance(value, (list, tuple)):
            container_id = id(value)
            if container_id in active_containers:
                raise ValueError("payload contains a reference cycle")
            active_containers.add(container_id)
            try:
                for child in value:
                    visit(child, depth + 1)
            finally:
                active_containers.remove(container_id)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("payload numbers must be finite")

    visit(payload, 0)


def _json_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    source = {} if value is None else value
    if not isinstance(source, Mapping):
        raise ValueError("uncertainty must be an object")
    reject_embedded_hydrology(source)
    try:
        normalized = json.loads(
            json.dumps(source, allow_nan=False, ensure_ascii=True, sort_keys=True)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("uncertainty must contain JSON-compatible values") from exc
    if not isinstance(normalized, dict):
        raise ValueError("uncertainty must be an object")
    reject_embedded_hydrology(normalized)
    return normalized


def build_impact_event(
    *,
    source_claim_id: str,
    impact_type: ImpactType,
    observed_at: str | None,
    municipality_geoids: list[str],
    linked_aguayluz_record_ids: list[str],
    linked_asset_ids: list[str] | None = None,
    watershed_ids: list[str] | None = None,
    irrigation_district_ids: list[str] | None = None,
    evidence_tier: str = "T2",
    uncertainty: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic impact event with reference-only hydrologic linkage."""

    if not isinstance(source_claim_id, str) or not source_claim_id.strip():
        raise ValueError("source_claim_id is required")
    if impact_type not in IMPACT_TYPES:
        raise ValueError("unsupported impact type")
    if evidence_tier not in EVIDENCE_TIERS:
        raise ValueError("unsupported evidence tier")
    _validate_observed_at(observed_at)

    geoids = _sorted_references("municipality_geoids", municipality_geoids)
    if any(MUNICIPALITY_GEOID.fullmatch(value) is None for value in geoids):
        raise ValueError("municipality_geoids must be five-digit Puerto Rico GEOIDs")

    aguayluz_ids = _sorted_references("linked_aguayluz_record_ids", linked_aguayluz_record_ids)
    if any(AGUAYLUZ_RECORD_ID.fullmatch(value) is None for value in aguayluz_ids):
        raise ValueError("AguaYLuz links must use provisional AYL_DROUGHT_ record IDs")

    identity = {
        "source_claim_id": source_claim_id,
        "impact_type": impact_type,
        "municipality_geoids": geoids,
    }
    event_id = f"CEN_DROUGHT_{_sha(identity)[:20]}"
    event = {
        "schema_version": "centinelas.drought-impact/v0.1",
        "event_id": event_id,
        "event_type": "drought_impact",
        "impact_type": impact_type,
        "observed_at": observed_at,
        "source_claim_id": source_claim_id,
        "evidence_tier": evidence_tier,
        "municipality_geoids": geoids,
        "linked_aguayluz_record_ids": aguayluz_ids,
        "linked_asset_ids": _sorted_references("linked_asset_ids", linked_asset_ids, optional=True),
        "watershed_ids": _sorted_references("watershed_ids", watershed_ids, optional=True),
        "irrigation_district_ids": _sorted_references(
            "irrigation_district_ids", irrigation_district_ids, optional=True
        ),
        "uncertainty": _json_mapping(uncertainty),
        "canonical_hydrology_embedded": False,
        "aguayluz_link_contract": dict(AGUAYLUZ_CONTRACT_SNAPSHOT),
    }
    reject_embedded_hydrology(event)
    event["content_sha256"] = _sha(event)
    return event
