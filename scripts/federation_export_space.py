#!/usr/bin/env python3
"""Export validated space-data leads as Hub-compatible canonical streams."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import federation_export as canonical_export  # noqa: E402

from centinelas.space_discovery import (  # noqa: E402
    enrich_federation_attributes,
    sha256_bytes,
    validate_lead,
)

PRODUCER_SCRIPT = "scripts/federation_export_space.py"
PRODUCER_PHASE = "SPACE_DATA_DISCOVERY"


def _stable_id(prefix: str, *parts: str) -> str:
    material = "|".join(parts)
    return f"{prefix}_{sha256_bytes(material.encode())[:32]}"


def _lineage(ledger_ref: str) -> dict[str, Any]:
    return {
        "producer_script": PRODUCER_SCRIPT,
        "producer_phase": PRODUCER_PHASE,
        "source_inputs": [ledger_ref],
        "extraction_method": "validated_space_lead_projection",
    }


def _jurisdiction(lead: dict[str, Any]) -> str:
    coverage = lead["geographic_coverage"]
    if coverage.get("global") is True:
        return "GLOBAL"
    jurisdictions = sorted({str(value) for value in coverage.get("jurisdictions", []) if value})
    return "|".join(jurisdictions) or "UNRESOLVED"


def build_streams(
    leads: list[dict[str, Any]],
    *,
    ledger_ref: str,
    mode: str,
) -> dict[str, list[dict[str, Any]]]:
    if not leads:
        raise ValueError("space-data export rejects an empty lead ledger")
    if mode not in {"test", "production"}:
        raise ValueError(f"unsupported export mode: {mode}")

    sources: dict[str, dict[str, Any]] = {}
    source_selection: dict[str, tuple[str, str, str]] = {}
    entities: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}

    for lead in leads:
        validate_lead(lead)
        synthetic = lead["synthetic"]
        if mode == "production" and synthetic:
            raise ValueError("production export rejects synthetic space-data leads")

        confidence = lead["confidence_score"] / 100.0
        source_id = _stable_id("src", lead["source_id"])
        entity_id = _stable_id("ent", lead["lead_id"])
        observation_id = _stable_id("obs", lead["lead_id"])
        lineage = _lineage(ledger_ref)

        source_row = {
            "source_id": source_id,
            "source_type": "space_data_discovery",
            "source_name": lead["source_id"],
            "source_url": lead["source_url"],
            "source_ref": lead["source_id"],
            "confidence": confidence,
            "lineage": lineage,
            "synthetic": synthetic,
            "created_at": lead["discovered_at"],
            "extracted_at": lead["last_verified_at"],
        }
        existing_source = sources.get(source_id)
        stable_fields = ("source_type", "source_name", "source_url", "source_ref", "synthetic")
        if existing_source is not None and any(
            existing_source[field] != source_row[field] for field in stable_fields
        ):
            raise ValueError(f"conflicting source manifestations for {lead['source_id']}")
        selection_key = (lead["last_verified_at"], lead["discovered_at"], lead["lead_id"])
        if existing_source is None or selection_key > source_selection[source_id]:
            sources[source_id] = source_row
            source_selection[source_id] = selection_key

        entity_row = {
            "entity_id": entity_id,
            "source_id": source_id,
            "name": lead["title"],
            "normalized_name": " ".join(lead["title"].casefold().split()),
            "entity_type": "space_data_lead",
            "jurisdiction": _jurisdiction(lead),
            "confidence": confidence,
            "lineage": lineage,
            "synthetic": synthetic,
            "created_at": lead["discovered_at"],
            "extracted_at": lead["last_verified_at"],
        }
        if entity_id in entities:
            raise ValueError(f"duplicate lead identity in export: {lead['lead_id']}")
        entities[entity_id] = entity_row

        observations[observation_id] = {
            "observation_id": observation_id,
            "entity_id": entity_id,
            "source_id": source_id,
            "observation_type": "space_data_discovery",
            "observed_at": lead["published_at"] or lead["discovered_at"],
            "attributes": {
                "signal_id": lead["lead_id"],
                "title": lead["title"],
                "source_url": lead["source_url"],
                **enrich_federation_attributes(lead),
            },
            "confidence": confidence,
            "lineage": lineage,
            "synthetic": synthetic,
            "created_at": lead["discovered_at"],
            "extracted_at": lead["last_verified_at"],
        }

    return {
        "sources": list(sources.values()),
        "entities": list(entities.values()),
        "relationships": [],
        "observations": list(observations.values()),
    }


def write_space_package(
    leads: list[dict[str, Any]],
    *,
    out: Path,
    ledger_ref: str,
    mode: str,
    created_at: str | None = None,
) -> Path:
    timestamp = created_at or (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    streams = build_streams(leads, ledger_ref=ledger_ref, mode=mode)
    return canonical_export.write_package(streams, out, mode, timestamp)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=("test", "production"), default="test")
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    leads = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest_path = write_space_package(
        leads,
        out=Path(args.out),
        ledger_ref=str(ledger_path),
        mode=args.mode,
    )
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
