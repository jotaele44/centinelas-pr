#!/usr/bin/env python3
"""Project Centinelas pre-officialization signals into PRII federation streams.

Maps the Centinelas signal/matter model onto the Hub's canonical contract:
  * each source family (referenced by a signal) -> one `sources` row
  * each distinct matter                        -> one `entities` row (entity_type=public_matter)
  * each distinct agency                        -> one `entities` row (entity_type=agency)
  * each distinct municipality                  -> one `entities` row (entity_type=municipality)
  * each signal                                 -> one `observations` row (observation_type=<signal_type>)
  * matter -> agency                            -> one `relationships` row (involves_agency)
  * matter -> municipality                      -> one `relationships` row (located_in)

Writes `exports/federation/{sources,entities,relationships,observations}.jsonl`
+ a Hub-conformant `manifest.json` (federation_export_manifest). Stdlib only,
consistent with the sibling OVNIS producer.

Rows carry `synthetic` = the signal's `is_synthetic` flag. The seed ledger
(`data/signals/example_signals.jsonl`) is entirely synthetic, so `--mode
production` rejects it: Centinelas has no real signal intake yet
(`ready_for_hub_live_execution=false`).

Deterministic IDs: `src_/ent_/rel_/obs_` + sha256(key)[:32].
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from prii_export_utils import fid as _fid, norm as _norm, sha256 as _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCER = "centinelas-pr"
CONTRACT_VERSION = "1.0.0"
PRODUCER_SCRIPT = "scripts/federation_export.py"
DEFAULT_LEDGER = REPO_ROOT / "data/signals/example_signals.jsonl"
DEFAULT_SOURCES = REPO_ROOT / "data/reference/source_registry.csv"

STREAM_SCHEMA = {
    "sources": "federation_source.schema.json",
    "entities": "federation_entity.schema.json",
    "relationships": "federation_relationship.schema.json",
    "observations": "federation_observation.schema.json",
}


def _lineage(phase: str) -> Dict[str, Any]:
    return {
        "producer_script": PRODUCER_SCRIPT,
        "producer_phase": phase,
        "source_inputs": ["data/signals/example_signals.jsonl", "data/reference/source_registry.csv"],
        "extraction_method": "deterministic_signal_projection",
    }


def _load_source_registry(path: Path) -> Dict[str, Dict[str, str]]:
    import csv

    if not path.exists():
        return {}
    with path.open() as fh:
        return {row["source_id"]: row for row in csv.DictReader(fh)}


def build_streams(
    signals: List[Dict[str, Any]],
    registry: Dict[str, Dict[str, str]],
    now: str,
) -> Dict[str, List[Dict[str, Any]]]:
    sources: Dict[str, Dict[str, Any]] = {}
    entities: Dict[str, Dict[str, Any]] = {}
    relationships: Dict[str, Dict[str, Any]] = {}
    observations: Dict[str, Dict[str, Any]] = {}

    for sig in signals:
        synthetic = bool(sig.get("is_synthetic"))
        created = sig.get("captured_at") or now
        confidence = round(float(sig.get("confidence_score", 0)) / 100.0, 3)
        reg_id = sig.get("source_id")
        reg = registry.get(reg_id, {})

        # --- source (source family) ---
        source_id = _fid("src", reg_id or "unknown")
        if source_id not in sources:
            sources[source_id] = {
                "source_id": source_id,
                "source_type": reg.get("source_family") or "unknown",
                "source_name": reg.get("name") or reg_id or "unknown",
                "source_ref": reg_id or "unknown",
                "confidence": confidence,
                "lineage": _lineage("SOURCE_REGISTRY"),
                "synthetic": synthetic,
                "created_at": created,
                "extracted_at": now,
            }

        # --- matter entity ---
        matter_id = sig.get("matter_id") or sig.get("signal_id")
        matter_ent = _fid("ent", "matter", matter_id)
        entities.setdefault(matter_ent, {
            "entity_id": matter_ent,
            "source_id": source_id,
            "name": sig.get("title") or matter_id,
            "normalized_name": _norm(sig.get("title") or matter_id),
            "entity_type": "public_matter",
            "jurisdiction": "PR",
            "confidence": confidence,
            "lineage": _lineage("MATTER_ENTITY"),
            "synthetic": synthetic,
            "created_at": created,
            "extracted_at": now,
        })

        # --- agency entities + involves_agency ---
        for agency in sig.get("agencies", []) or []:
            agency_ent = _fid("ent", "agency", _norm(agency))
            entities.setdefault(agency_ent, {
                "entity_id": agency_ent,
                "source_id": source_id,
                "name": agency,
                "normalized_name": _norm(agency),
                "entity_type": "agency",
                "jurisdiction": "PR",
                "confidence": confidence,
                "lineage": _lineage("AGENCY_ENTITY"),
                "synthetic": synthetic,
                "created_at": created,
                "extracted_at": now,
            })
            rel_id = _fid("rel", matter_ent, "involves_agency", agency_ent)
            relationships.setdefault(rel_id, _relationship(
                rel_id, source_id, matter_ent, agency_ent, "involves_agency",
                confidence, synthetic, created, now))

        # --- municipality entities + located_in ---
        for muni in sig.get("municipalities", []) or []:
            muni_ent = _fid("ent", "municipality", _norm(muni))
            entities.setdefault(muni_ent, {
                "entity_id": muni_ent,
                "source_id": source_id,
                "name": muni,
                "normalized_name": _norm(muni),
                "entity_type": "municipality",
                "jurisdiction": "PR",
                "confidence": 0.95,
                "lineage": _lineage("MUNICIPALITY_ENTITY"),
                "synthetic": synthetic,
                "created_at": created,
                "extracted_at": now,
            })
            rel_id = _fid("rel", matter_ent, "located_in", muni_ent)
            relationships.setdefault(rel_id, _relationship(
                rel_id, source_id, matter_ent, muni_ent, "located_in",
                confidence, synthetic, created, now))

        # --- observation (the signal itself) ---
        obs_id = _fid("obs", "signal", sig.get("signal_id"))
        observations[obs_id] = {
            "observation_id": obs_id,
            "entity_id": matter_ent,
            "source_id": source_id,
            "observation_type": sig.get("signal_type") or "public_signal",
            "observed_at": sig.get("captured_at") or now,
            "attributes": {
                "signal_id": sig.get("signal_id"),
                "matter_id": matter_id,
                "title": sig.get("title"),
                "summary": sig.get("summary"),
                "signal_stage": sig.get("signal_stage"),
                "beat": sig.get("beat"),
                "evidence_tier": sig.get("evidence_tier"),
                "handoff_status": sig.get("handoff_status"),
                "deadline_date": sig.get("deadline_date"),
                "source_url": sig.get("source_url"),
            },
            "confidence": confidence,
            "lineage": _lineage("OBSERVATION"),
            "synthetic": synthetic,
            "created_at": created,
            "extracted_at": now,
        }

    return {
        "sources": list(sources.values()),
        "entities": list(entities.values()),
        "relationships": list(relationships.values()),
        "observations": list(observations.values()),
    }


def _relationship(rel_id, source_id, src_ent, tgt_ent, rtype, confidence, synthetic, created, now):
    return {
        "relationship_id": rel_id,
        "source_id": source_id,
        "source_entity_id": src_ent,
        "target_entity_id": tgt_ent,
        "relationship_type": rtype,
        "evidence_source_id": source_id,
        "confidence": confidence,
        "lineage": _lineage("RELATIONSHIP"),
        "synthetic": synthetic,
        "created_at": created,
        "extracted_at": now,
    }


def write_package(streams: Dict[str, List[Dict[str, Any]]], out_dir: Path, mode: str, now: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for stream in ("sources", "entities", "relationships", "observations"):
        rows = streams[stream]
        if not rows:
            continue
        fpath = out_dir / f"{stream}.jsonl"
        fpath.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        files.append({
            "filename": f"{stream}.jsonl",
            "stream": stream,
            "record_count": len(rows),
            "sha256": _sha256(fpath),
            "schema_id": STREAM_SCHEMA[stream],
        })
    digest = hashlib.sha256(
        ("|".join(f"{f['filename']}:{f['sha256']}" for f in files) + f"|{mode}").encode()
    ).hexdigest()[:32]
    manifest = {
        "package_id": f"pkg_{digest}",
        "producer": PRODUCER,
        "export_contract_version": CONTRACT_VERSION,
        "mode": mode,
        "created_at": now,
        "extracted_at": now,
        "federation": {"producer_repo": PRODUCER, "hub_parent": "thehub-pr"},
        "files": files,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return out_dir / "manifest.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Centinelas signals as PRII canonical streams.")
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--out", default=str(REPO_ROOT / "exports/federation"))
    ap.add_argument("--mode", default="test", choices=["test", "production"])
    args = ap.parse_args()

    signals = [json.loads(line) for line in Path(args.ledger).read_text().splitlines() if line.strip()]
    registry = _load_source_registry(Path(args.sources))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    streams = build_streams(signals, registry, now)

    if args.mode == "production":
        synthetic = [r for s in streams.values() for r in s if r.get("synthetic")]
        if synthetic:
            print(
                f"FAIL — {len(synthetic)} synthetic rows are not allowed in production mode; "
                "Centinelas has no real (non-synthetic) signal intake yet"
            )
            return 1

    manifest_path = write_package(streams, Path(args.out), args.mode, now)
    counts = {k: len(v) for k, v in streams.items()}
    print(f"wrote {manifest_path} — {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
