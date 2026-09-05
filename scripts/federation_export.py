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

Rows carry `synthetic` = the signal's `is_synthetic` flag. Production mode is
fail-closed: it rejects synthetic rows, an empty ledger, missing/invalid capture
timestamps, and a ledger whose newest capture exceeds `--max-age-hours`.

Deterministic IDs: `src_/ent_/rel_/obs_` + sha256(key)[:32].
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prii_export_utils import fid as _fid
from prii_export_utils import norm as _norm
from prii_export_utils import sha256 as _sha256

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCER = "centinelas-pr"
CONTRACT_VERSION = "1.0.0"
PRODUCER_SCRIPT = "scripts/federation_export.py"
DEFAULT_LEDGER = REPO_ROOT / "data/signals/example_signals.jsonl"
DEFAULT_SOURCES = REPO_ROOT / "data/reference/source_registry.csv"
DEFAULT_MAX_AGE_HOURS = 168.0
ACCEPTABLE_CLASSIFICATION_METHODS = {"keyword_fast_path", "llm"}
ACCEPTABLE_SOURCE_STATES = {
    "SUCCESS_WITH_ROWS",
    "SUCCESS_EMPTY",
    "SUCCESS_FILTERED_EMPTY",
}
REQUIRED_RECEIPT_GATES = {
    "nonempty_ledger",
    "no_synthetic_rows",
    "unique_signal_ids",
    "full_polled_item_retention",
    "repository_head_bound",
    "source_config_stable",
    "terminal_sources",
    "source_conservation",
    "unique_source_names",
    "unique_source_urls",
    "source_registry_ids_bound",
    "unique_source_registry_ids",
    "entry_conservation",
    "raw_response_conservation",
    "raw_hashes_bound",
    "no_source_failures",
    "no_classifier_fallback",
    "source_scope_conservation",
    "active_source_scope_matches_receipts",
    "source_scope_registry_ids_unique",
    "excluded_sources_adjudicated",
}
TERMINAL_EXCLUDED_SOURCE_STATES = {
    "NONCANONICAL_ACCESS_BLOCKED",
    "RETIRED_NO_EQUIVALENT_PUBLIC_FEED",
    "RETIRED_NO_PUBLIC_FEED",
    "SUPERSEDED",
}

STREAM_SCHEMA = {
    "sources": "federation_source.schema.json",
    "entities": "federation_entity.schema.json",
    "relationships": "federation_relationship.schema.json",
    "observations": "federation_observation.schema.json",
}


def _lineage(phase: str, source_inputs: list[str] | None = None) -> dict[str, Any]:
    return {
        "producer_script": PRODUCER_SCRIPT,
        "producer_phase": phase,
        "source_inputs": source_inputs
        or ["data/signals/example_signals.jsonl", "data/reference/source_registry.csv"],
        "extraction_method": "deterministic_signal_projection",
    }


def _load_source_registry(path: Path) -> dict[str, dict[str, str]]:
    import csv

    if not path.exists():
        return {}
    with path.open() as fh:
        return {row["source_id"]: row for row in csv.DictReader(fh)}


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _production_input_errors(
    signals: list[dict[str, Any]],
    *,
    now: datetime,
    max_age_hours: float,
) -> list[str]:
    if not signals:
        return ["production export rejects an empty live signal ledger"]
    if max_age_hours <= 0:
        return ["--max-age-hours must be greater than zero in production mode"]

    captures: list[datetime] = []
    for index, signal in enumerate(signals, start=1):
        captured = _parse_utc_timestamp(signal.get("captured_at"))
        if captured is None:
            return [f"production signal row {index} has missing or invalid captured_at"]
        captures.append(captured)

    newest = max(captures)
    age_hours = (now.astimezone(timezone.utc) - newest).total_seconds() / 3600.0
    if age_hours < -1.0:
        return [f"production ledger newest captured_at is {abs(age_hours):.1f}h in the future"]
    if age_hours > max_age_hours:
        return [
            "production live signal ledger is stale: "
            f"newest capture age={age_hours:.1f}h exceeds max={max_age_hours:.1f}h"
        ]
    return []


def _production_receipt_errors(
    receipt: dict[str, Any] | None,
    *,
    ledger_path: Path,
    signals: list[dict[str, Any]],
) -> list[str]:
    if receipt is None:
        return ["production export requires --receipt from build_signal_ledger.py"]

    errors: list[str] = []
    if receipt.get("schema_version") != "1.0.0":
        errors.append("production snapshot receipt has an unsupported schema version")
    if receipt.get("repository") != "jotaele44/centinelas-pr":
        errors.append("production snapshot receipt names the wrong repository")
    if receipt.get("classification") != "PASS":
        errors.append(
            "production snapshot receipt is not PASS: "
            f"classification={receipt.get('classification')!r}"
        )

    gates = receipt.get("gates")
    if not isinstance(gates, dict):
        failed = ["invalid_or_missing_gates"]
    else:
        missing = REQUIRED_RECEIPT_GATES - gates.keys()
        failed = sorted(
            {
                *missing,
                *(key for key in REQUIRED_RECEIPT_GATES if gates.get(key) is not True),
            }
        )
    if failed:
        errors.append(f"production snapshot receipt has failed gates: {failed}")

    ledger = receipt.get("ledger")
    if not isinstance(ledger, dict):
        return [*errors, "production snapshot receipt is missing ledger metadata"]
    actual_sha256 = _sha256(ledger_path)
    if ledger.get("sha256") != actual_sha256:
        errors.append("production ledger SHA256 does not match snapshot receipt")
    if ledger.get("rows") != len(signals):
        errors.append(
            "production ledger row count does not match snapshot receipt: "
            f"receipt={ledger.get('rows')!r}, actual={len(signals)}"
        )
    if ledger.get("polled_items_before_limit") != len(signals):
        errors.append("production receipt does not retain every polled item")
    actual_synthetic_rows = sum(bool(row.get("is_synthetic")) for row in signals)
    if ledger.get("synthetic_rows") != actual_synthetic_rows:
        errors.append("production receipt synthetic-row count does not match ledger")
    actual_duplicate_ids = len(signals) - len(
        {row.get("signal_id") for row in signals}
    )
    if ledger.get("duplicate_signal_ids") != actual_duplicate_ids:
        errors.append("production receipt duplicate-ID count does not match ledger")
    method_counts = dict(
        sorted(Counter(str(row.get("classification_method")) for row in signals).items())
    )
    if ledger.get("classification_method_counts") != method_counts:
        errors.append("production receipt classification-method counts do not match ledger")
    invalid_methods = sorted(
        {
            str(row.get("classification_method"))
            for row in signals
            if row.get("classification_method") not in ACCEPTABLE_CLASSIFICATION_METHODS
        }
    )
    if invalid_methods:
        errors.append(f"production ledger has non-accepted classification methods: {invalid_methods}")
    if any(not str(row.get("classifier_reasoning") or "").strip() for row in signals):
        errors.append("production ledger has rows without classifier reasoning")

    sources = receipt.get("sources")
    if not isinstance(sources, dict) or not isinstance(sources.get("rows"), list):
        errors.append("production snapshot receipt is missing source rows")
    else:
        source_rows = sources["rows"]
        if not all(isinstance(row, dict) for row in source_rows):
            errors.append("production snapshot receipt contains invalid source rows")
            source_rows = [row for row in source_rows if isinstance(row, dict)]
        if not (
            sources.get("configured")
            == sources.get("receipts")
            == len(source_rows)
        ):
            errors.append("production source receipt arithmetic does not close")
        status_counts = dict(
            sorted(Counter(str(row.get("status")) for row in source_rows).items())
        )
        if sources.get("status_counts") != status_counts:
            errors.append("production source status counts do not match source rows")
        if any(row.get("status") not in ACCEPTABLE_SOURCE_STATES for row in source_rows):
            errors.append("production source receipt contains a non-success status")
        if sources.get("source_failure_count") != 0:
            errors.append("production source receipt has a nonzero failure count")
        count_fields = (
            "entries_seen",
            "entries_filtered",
            "entries_without_link",
            "accepted_entries",
            "duplicates_suppressed",
            "emitted_items",
        )
        count_fields_valid = all(
            isinstance(row.get(field), int)
            and not isinstance(row.get(field), bool)
            and row[field] >= 0
            for row in source_rows
            for field in count_fields
        )
        if not count_fields_valid:
            errors.append("production source receipt contains invalid entry counts")
        else:
            if any(
                row["entries_seen"]
                != row["entries_filtered"]
                + row["entries_without_link"]
                + row["accepted_entries"]
                or row["accepted_entries"]
                != row["duplicates_suppressed"] + row["emitted_items"]
                for row in source_rows
            ):
                errors.append("production source entry arithmetic does not close")
            if sum(row["emitted_items"] for row in source_rows) != len(signals):
                errors.append("production source emitted-item total does not match ledger rows")
        names = [row.get("name") for row in source_rows]
        urls = [row.get("url") for row in source_rows]
        registry_ids = [row.get("source_registry_id") for row in source_rows]
        identities = names + urls + registry_ids
        if any(not isinstance(value, str) or not value for value in identities):
            errors.append("production source receipt has missing source identity fields")
        elif any(len(values) != len(set(values)) for values in (names, urls, registry_ids)):
            errors.append("production source receipt has source identity collisions")

        raw_directory = sources.get("raw_directory")
        raw_dir = Path(raw_directory) if isinstance(raw_directory, str) else None
        referenced_raw_files: set[str] = set()
        if raw_dir is None or not raw_dir.is_dir():
            errors.append("production source raw directory is unavailable")
        else:
            for row in source_rows:
                relative = row.get("raw_content_path")
                expected_hash = row.get("response_content_sha256")
                expected_bytes = row.get("response_content_bytes")
                if (
                    not isinstance(relative, str)
                    or Path(relative).name != relative
                    or not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash or ""))
                ):
                    errors.append(
                        f"production source raw binding is invalid for {row.get('name')!r}"
                    )
                    continue
                referenced_raw_files.add(relative)
                raw_path = raw_dir / relative
                if not raw_path.is_file():
                    errors.append(f"production source raw file is missing: {relative}")
                    continue
                if raw_path.stat().st_size != expected_bytes or _sha256(raw_path) != expected_hash:
                    errors.append(f"production source raw file does not match receipt: {relative}")
            actual_raw_files = {path.name for path in raw_dir.iterdir() if path.is_file()}
            if actual_raw_files != referenced_raw_files:
                errors.append("production raw directory contains unbound or missing files")

    source_config = receipt.get("source_config")
    if (
        not isinstance(source_config, dict)
        or source_config.get("stable") is not True
        or not isinstance(source_config.get("before"), list)
        or not source_config.get("before")
        or source_config.get("before") != source_config.get("after")
    ):
        errors.append("production source configuration binding is incomplete or unstable")

    source_scope = receipt.get("source_scope")
    if not isinstance(source_scope, dict) or not isinstance(
        source_scope.get("rows"), list
    ):
        errors.append("production snapshot receipt is missing source scope rows")
    else:
        scope_rows = source_scope["rows"]
        if not all(isinstance(row, dict) for row in scope_rows):
            errors.append("production snapshot receipt contains invalid source scope rows")
            scope_rows = [row for row in scope_rows if isinstance(row, dict)]
        active_scope = [row for row in scope_rows if row.get("active") is True]
        excluded_scope = [row for row in scope_rows if row.get("active") is False]
        inventory_count = source_scope.get("inventory")
        active_count = source_scope.get("active")
        excluded_count = source_scope.get("excluded")
        scope_counts_valid = all(
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
            for value in (inventory_count, active_count, excluded_count)
        )
        if (
            not scope_counts_valid
            or not isinstance(inventory_count, int)
            or not isinstance(active_count, int)
            or not isinstance(excluded_count, int)
            or not (
                inventory_count == len(scope_rows)
                and inventory_count == active_count + excluded_count
                and active_count == len(active_scope)
                and excluded_count == len(excluded_scope)
            )
        ):
            errors.append("production source scope arithmetic does not close")
        scope_ids = [row.get("source_registry_id") for row in scope_rows]
        if any(not isinstance(value, str) or not value for value in scope_ids):
            errors.append("production source scope has missing registry IDs")
        elif len(scope_ids) != len(set(scope_ids)):
            errors.append("production source scope has registry ID collisions")
        if isinstance(sources, dict) and isinstance(sources.get("rows"), list):
            receipt_ids = {
                row.get("source_registry_id")
                for row in sources["rows"]
                if isinstance(row, dict)
            }
            active_scope_ids = {
                row.get("source_registry_id") for row in active_scope
            }
            if receipt_ids != active_scope_ids:
                errors.append("production active source scope does not match source receipts")
        if any(
            row.get("lifecycle_state") not in TERMINAL_EXCLUDED_SOURCE_STATES
            or not str(row.get("retired_at") or "").strip()
            or not str(row.get("retirement_reason") or "").strip()
            or not str(row.get("adjudication_ref") or "").strip()
            for row in excluded_scope
        ):
            errors.append("production excluded source scope is not fully adjudicated")

    repository_head = receipt.get("repository_head")
    if not isinstance(repository_head, str) or not re.fullmatch(
        r"[0-9a-f]{40}", repository_head
    ):
        errors.append("production snapshot receipt lacks a full repository head SHA")
    return errors


def build_streams(
    signals: list[dict[str, Any]],
    registry: dict[str, dict[str, str]],
    now: str,
    source_inputs: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    sources: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    relationships: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}

    for sig in signals:
        synthetic = bool(sig.get("is_synthetic"))
        created = sig.get("captured_at") or now
        confidence = round(float(sig.get("confidence_score", 0)) / 100.0, 3)
        reg_id = sig.get("source_id")
        reg = registry.get(reg_id, {}) if isinstance(reg_id, str) else {}

        # --- source (source family) ---
        source_id = _fid("src", reg_id or "unknown")
        if source_id not in sources:
            sources[source_id] = {
                "source_id": source_id,
                "source_type": reg.get("source_family") or "unknown",
                "source_name": reg.get("name") or reg_id or "unknown",
                "source_ref": reg_id or "unknown",
                "confidence": confidence,
                "lineage": _lineage("SOURCE_REGISTRY", source_inputs),
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
            "lineage": _lineage("MATTER_ENTITY", source_inputs),
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
                "lineage": _lineage("AGENCY_ENTITY", source_inputs),
                "synthetic": synthetic,
                "created_at": created,
                "extracted_at": now,
            })
            rel_id = _fid("rel", matter_ent, "involves_agency", agency_ent)
            relationships.setdefault(rel_id, _relationship(
                rel_id, source_id, matter_ent, agency_ent, "involves_agency",
                confidence, synthetic, created, now, source_inputs))

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
                "lineage": _lineage("MUNICIPALITY_ENTITY", source_inputs),
                "synthetic": synthetic,
                "created_at": created,
                "extracted_at": now,
            })
            rel_id = _fid("rel", matter_ent, "located_in", muni_ent)
            relationships.setdefault(rel_id, _relationship(
                rel_id, source_id, matter_ent, muni_ent, "located_in",
                confidence, synthetic, created, now, source_inputs))

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
                "classification_method": sig.get("classification_method"),
                "classifier_reasoning": sig.get("classifier_reasoning"),
            },
            "confidence": confidence,
            "lineage": _lineage("OBSERVATION", source_inputs),
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


def _relationship(
    rel_id,
    source_id,
    src_ent,
    tgt_ent,
    rtype,
    confidence,
    synthetic,
    created,
    now,
    source_inputs,
):
    return {
        "relationship_id": rel_id,
        "source_id": source_id,
        "source_entity_id": src_ent,
        "target_entity_id": tgt_ent,
        "relationship_type": rtype,
        "evidence_source_id": source_id,
        "confidence": confidence,
        "lineage": _lineage("RELATIONSHIP", source_inputs),
        "synthetic": synthetic,
        "created_at": created,
        "extracted_at": now,
    }


def write_package(
    streams: dict[str, list[dict[str, Any]]],
    out_dir: Path,
    mode: str,
    now: str,
    input_provenance: dict[str, Any] | None = None,
) -> Path:
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
    if input_provenance is not None:
        manifest["input_provenance"] = input_provenance
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return out_dir / "manifest.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Centinelas signals as PRII canonical streams.")
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    ap.add_argument("--receipt")
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--out", default=str(REPO_ROOT / "exports/federation"))
    ap.add_argument("--mode", default="test", choices=["test", "production"])
    ap.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help="maximum age of newest captured_at accepted in production mode (default: 168h)",
    )
    args = ap.parse_args()

    ledger_path = Path(args.ledger)
    signals = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
    registry = _load_source_registry(Path(args.sources))
    receipt_path = Path(args.receipt) if args.receipt else None
    receipt: dict[str, Any] | None = None
    receipt_parse_error: str | None = None
    if receipt_path is not None:
        try:
            loaded_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if isinstance(loaded_receipt, dict):
                receipt = loaded_receipt
            else:
                receipt_parse_error = "snapshot receipt must contain a JSON object"
        except (OSError, json.JSONDecodeError) as exc:
            receipt_parse_error = f"could not read snapshot receipt: {exc}"
    now_dt = datetime.now(timezone.utc)
    now = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if args.mode == "production":
        input_errors = _production_input_errors(
            signals,
            now=now_dt,
            max_age_hours=args.max_age_hours,
        )
        if receipt_parse_error:
            input_errors.append(receipt_parse_error)
        else:
            input_errors.extend(
                _production_receipt_errors(
                    receipt,
                    ledger_path=ledger_path,
                    signals=signals,
                )
            )
        if input_errors:
            print("FAIL — " + "; ".join(input_errors))
            return 1

    source_inputs = [str(ledger_path), str(Path(args.sources))]
    if receipt_path is not None:
        source_inputs.append(str(receipt_path))
    streams = build_streams(signals, registry, now, source_inputs)

    if args.mode == "production":
        synthetic = [r for s in streams.values() for r in s if r.get("synthetic")]
        if synthetic:
            print(
                f"FAIL — {len(synthetic)} synthetic rows are not allowed in production mode"
            )
            return 1

    input_provenance = None
    if receipt is not None and receipt_path is not None:
        input_provenance = {
            "ledger_path": str(ledger_path),
            "ledger_sha256": _sha256(ledger_path),
            "ledger_rows": len(signals),
            "receipt_path": str(receipt_path),
            "receipt_sha256": _sha256(receipt_path),
            "receipt_classification": receipt.get("classification"),
            "repository_head": receipt.get("repository_head"),
        }
    manifest_path = write_package(
        streams,
        Path(args.out),
        args.mode,
        now,
        input_provenance,
    )
    counts = {k: len(v) for k, v in streams.items()}
    print(f"wrote {manifest_path} — {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
