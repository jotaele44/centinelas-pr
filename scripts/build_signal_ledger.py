#!/usr/bin/env python3
"""Bridge the live intake engine into the federation signal ledger.

The engine (src/centinelas) ingests real RSS feeds and classifies items, but
its output (`ClassifiedItem`) never reached `data/signals/` — the federation
export could only read the synthetic seed ledger, so `--mode production` was
permanently refused. This bridge closes that gap:

    poll_all() -> classify() -> signal rows -> data/signals/live_signals.jsonl

Every emitted row is a REAL public signal (`is_synthetic: false`) captured
from the configured feeds at run time. These are global topical early signals
(stage `raw_observation`, one matter per item); the Puerto Rico
pre-officialization source families in the registry (legislative calendars,
municipal agendas, procurement notices, ...) remain the named future intake —
this bridge does not claim them.

Mapping (ClassifiedItem -> signal.schema.json):
  signal_id        CENT-SIG-<item_id>
  matter_id        CENT-MAT-<item_id>          (1:1 item->matter at this stage)
  signal_type      <primary label, lowercased>_signal
  beat             <primary label, lowercased>
  signal_stage     raw_observation
  source_id        CENT-SRC-RSS-<feed slug>    (rows added to the source registry)
  confidence_score confidence * 100
  evidence_tier    verbatim (same T1-T4 enum)
  is_synthetic     false

Usage:
    python scripts/build_signal_ledger.py                 # live poll + classify
    python scripts/build_signal_ledger.py --out <path> --limit 100
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from centinelas.classify.classifier import classify_with_provenance  # noqa: E402
from centinelas.ingest import rss  # noqa: E402
from centinelas.models import ClassifiedItem  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "data" / "signals" / "live_signals.jsonl"
SOURCE_CONFIG_PATHS = (
    REPO_ROOT / "src" / "centinelas" / "ingest" / "sources.yaml",
    REPO_ROOT / "src" / "centinelas" / "ingest" / "just_security_sources.yaml",
    REPO_ROOT / "data" / "reference" / "source_registry.csv",
    REPO_ROOT / "docs" / "source_adjudication_20260905.json",
)
TERMINAL_EXCLUDED_SOURCE_STATES = {
    "NONCANONICAL_ACCESS_BLOCKED",
    "RETIRED_NO_EQUIVALENT_PUBLIC_FEED",
    "RETIRED_NO_PUBLIC_FEED",
    "SUPERSEDED",
}


def feed_source_id(feed_name: str) -> str:
    """Deterministic registry id for a feed — mirrored in source_registry.csv."""
    slug = re.sub(r"[^A-Z0-9]+", "-", feed_name.upper()).strip("-")
    return f"CENT-SRC-RSS-{slug}"


def source_name_to_id(sources: list[dict] | None = None) -> dict[str, str]:
    configured_sources = rss._load_sources() if sources is None else sources
    return {
        src["name"]: src.get("source_id") or feed_source_id(src["name"])
        for src in configured_sources
    }


def build_source_scope(source_inventory: list[dict]) -> list[dict]:
    source_ids = source_name_to_id(source_inventory)
    return [
        {
            "source_registry_id": source_ids.get(source["name"]),
            "name": source["name"],
            "url": source.get("url"),
            "active": bool(source.get("enabled", True)),
            "lifecycle_state": (
                "ACTIVE"
                if source.get("enabled", True)
                else source.get("lifecycle_state", "UNRESOLVED")
            ),
            "retired_at": source.get("retired_at"),
            "retirement_reason": source.get("retirement_reason"),
            "adjudication_ref": source.get("adjudication_ref"),
            "candidate_url": source.get("candidate_url"),
        }
        for source in source_inventory
    ]


def item_to_signal(
    item: ClassifiedItem,
    source_ids: dict[str, str],
    *,
    classification_method: str = "unresolved",
) -> dict:
    primary = item.labels[0].value.lower() if item.labels else "unclassified"
    return {
        "signal_id": f"CENT-SIG-{item.item_id}",
        "matter_id": f"CENT-MAT-{item.item_id}",
        "signal_type": f"{primary}_signal",
        "title": item.title,
        "summary": (item.body_text or "")[:500],
        "source_id": source_ids.get(item.source_name, feed_source_id(item.source_name)),
        "source_url": item.source_url,
        "captured_at": item.captured_at.isoformat(),
        "published_at": item.published_at.isoformat(),
        "signal_stage": "raw_observation",
        "beat": primary,
        "municipalities": [],
        "agencies": [],
        "entities": [],
        "estimated_value": None,
        "deadline_date": None,
        "urgency_score": None,
        "confidence_score": round(item.confidence * 100, 1),
        "evidence_tier": item.evidence_tier,
        "handoff_status": "raw",
        "is_synthetic": False,
        "labels": [label.value for label in item.labels],
        "classification_method": classification_method,
        "classifier_reasoning": item.classifier_reasoning,
    }


def build_ledger_with_receipts(
    limit: int | None = None,
    *,
    raw_dir: Path | None = None,
    timeout_seconds: float = 20.0,
    sources: list[dict] | None = None,
) -> tuple[list[dict], list[dict], int]:
    configured_sources = rss._load_sources() if sources is None else sources
    raw_items, source_receipts = rss.poll_all_with_receipts(
        raw_dir=raw_dir,
        timeout_seconds=timeout_seconds,
        sources=configured_sources,
    )
    if not raw_items:
        raise SystemExit("FAIL — no feeds returned items; refusing to write an empty live ledger")
    polled_item_count = len(raw_items)
    if limit:
        raw_items = raw_items[:limit]
    source_ids = source_name_to_id(configured_sources)
    for receipt in source_receipts:
        receipt["source_registry_id"] = source_ids.get(receipt["name"])
    signals = []
    for raw in raw_items:
        labels, confidence, reasoning, method = classify_with_provenance(raw)
        classified = ClassifiedItem(
            **raw.model_dump(), labels=labels, confidence=confidence,
            classifier_reasoning=reasoning,
        )
        signals.append(
            item_to_signal(
                classified,
                source_ids,
                classification_method=method,
            )
        )
    return signals, source_receipts, polled_item_count


def build_ledger(limit: int | None = None) -> list[dict]:
    signals, _, _ = build_ledger_with_receipts(limit)
    return signals


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def git_head() -> str | None:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def source_config_state() -> list[dict]:
    return [
        {
            "path": str(path.relative_to(REPO_ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        }
        for path in SOURCE_CONFIG_PATHS
    ]


def build_receipt(
    *,
    out: Path,
    raw_dir: Path,
    signals: list[dict],
    source_receipts: list[dict],
    polled_item_count: int,
    started_at: str,
    completed_at: str,
    limit: int | None,
    configured_source_count: int,
    repository_head: str | None,
    source_config_before: list[dict],
    source_config_after: list[dict],
    source_scope_rows: list[dict] | None = None,
) -> dict:
    source_status_counts = Counter(row["status"] for row in source_receipts)
    method_counts = Counter(row["classification_method"] for row in signals)
    terminal_sources = all(row["status"] != "UNRESOLVED" for row in source_receipts)
    source_conservation = len(source_receipts) == configured_source_count
    entry_conservation = all(
        row["entries_seen"]
        == row["entries_filtered"]
        + row["entries_without_link"]
        + row["accepted_entries"]
        and row["accepted_entries"]
        == row["duplicates_suppressed"] + row["emitted_items"]
        for row in source_receipts
        if row["http_status"] is not None and 200 <= row["http_status"] < 300
    )
    raw_hashes_bound = all(
        row["raw_content_path"] is not None
        and (raw_dir / row["raw_content_path"]).is_file()
        and sha256_path(raw_dir / row["raw_content_path"])
        == row["response_content_sha256"]
        for row in source_receipts
        if row["response_content_sha256"] is not None
    )
    raw_response_conservation = all(
        (row["http_status"] is None) == (row["response_content_sha256"] is None)
        for row in source_receipts
    )
    acceptable_source_states = {
        "SUCCESS_WITH_ROWS",
        "SUCCESS_EMPTY",
        "SUCCESS_FILTERED_EMPTY",
    }
    source_failures = [
        row for row in source_receipts if row["status"] not in acceptable_source_states
    ]
    classifier_fallback_rows = sum(
        count
        for method, count in method_counts.items()
        if method in {"keyword_fallback", "unclassified_fallback", "unresolved"}
    )
    if source_scope_rows is None:
        source_scope_rows = [
            {
                "source_registry_id": row.get("source_registry_id"),
                "name": row.get("name"),
                "url": row.get("url"),
                "active": True,
                "lifecycle_state": "ACTIVE",
                "retired_at": None,
                "retirement_reason": None,
                "adjudication_ref": None,
                "candidate_url": None,
            }
            for row in source_receipts
        ]
    active_scope_rows = [row for row in source_scope_rows if row.get("active") is True]
    excluded_scope_rows = [row for row in source_scope_rows if row.get("active") is False]
    source_scope_conservation = (
        len(source_scope_rows) == len(active_scope_rows) + len(excluded_scope_rows)
        and len(active_scope_rows) == configured_source_count
    )
    active_scope_matches_receipts = {
        row.get("source_registry_id") for row in active_scope_rows
    } == {row.get("source_registry_id") for row in source_receipts}
    excluded_sources_adjudicated = all(
        row.get("lifecycle_state") in TERMINAL_EXCLUDED_SOURCE_STATES
        and bool(row.get("retired_at"))
        and bool(row.get("retirement_reason"))
        and bool(row.get("adjudication_ref"))
        for row in excluded_scope_rows
    )
    gates = {
        "nonempty_ledger": bool(signals),
        "no_synthetic_rows": not any(row.get("is_synthetic") for row in signals),
        "unique_signal_ids": len(signals)
        == len({row["signal_id"] for row in signals}),
        "full_polled_item_retention": len(signals) == polled_item_count,
        "repository_head_bound": bool(repository_head),
        "source_config_stable": source_config_before == source_config_after,
        "terminal_sources": terminal_sources,
        "source_conservation": source_conservation,
        "unique_source_names": len(source_receipts)
        == len({row["name"] for row in source_receipts}),
        "unique_source_urls": len(source_receipts)
        == len({row["url"] for row in source_receipts}),
        "source_registry_ids_bound": all(
            bool(row.get("source_registry_id")) for row in source_receipts
        ),
        "unique_source_registry_ids": len(source_receipts)
        == len({row.get("source_registry_id") for row in source_receipts}),
        "entry_conservation": entry_conservation,
        "raw_response_conservation": raw_response_conservation,
        "raw_hashes_bound": raw_hashes_bound,
        "no_source_failures": not source_failures,
        "no_classifier_fallback": classifier_fallback_rows == 0,
        "source_scope_conservation": source_scope_conservation,
        "active_source_scope_matches_receipts": active_scope_matches_receipts,
        "source_scope_registry_ids_unique": all(
            bool(row.get("source_registry_id")) for row in source_scope_rows
        )
        and len(source_scope_rows)
        == len({row.get("source_registry_id") for row in source_scope_rows}),
        "excluded_sources_adjudicated": excluded_sources_adjudicated,
    }
    classification = "PASS" if all(gates.values()) else "PROVISIONAL"
    return {
        "schema_version": "1.0.0",
        "classification": classification,
        "repository": "jotaele44/centinelas-pr",
        "repository_head": repository_head,
        "capture_started_at": started_at,
        "capture_completed_at": completed_at,
        "ledger": {
            "path": str(out),
            "sha256": sha256_path(out),
            "rows": len(signals),
            "polled_items_before_limit": polled_item_count,
            "limit": limit,
            "synthetic_rows": sum(bool(row.get("is_synthetic")) for row in signals),
            "duplicate_signal_ids": len(signals)
            - len({row["signal_id"] for row in signals}),
            "classification_method_counts": dict(sorted(method_counts.items())),
        },
        "sources": {
            "configured": configured_source_count,
            "receipts": len(source_receipts),
            "status_counts": dict(sorted(source_status_counts.items())),
            "terminal": terminal_sources,
            "source_conservation": source_conservation,
            "entry_conservation": entry_conservation,
            "source_failure_count": len(source_failures),
            "raw_directory": str(raw_dir),
            "raw_hashes_bound": raw_hashes_bound,
            "raw_response_conservation": raw_response_conservation,
            "response_content_byte_scope": "decoded_http_entity_body",
            "rows": source_receipts,
        },
        "source_config": {
            "before": source_config_before,
            "after": source_config_after,
            "stable": source_config_before == source_config_after,
        },
        "source_scope": {
            "inventory": len(source_scope_rows),
            "active": len(active_scope_rows),
            "excluded": len(excluded_scope_rows),
            "conservation": source_scope_conservation,
            "active_matches_receipts": active_scope_matches_receipts,
            "excluded_adjudicated": excluded_sources_adjudicated,
            "rows": source_scope_rows,
        },
        "gates": gates,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Materialize real signals into the federation ledger.")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--receipt")
    ap.add_argument("--raw-dir")
    ap.add_argument("--timeout-seconds", type=float, default=20.0)
    ap.add_argument("--require-complete-sources", action="store_true")
    args = ap.parse_args(argv)

    if bool(args.receipt) != bool(args.raw_dir):
        ap.error("--receipt and --raw-dir must be provided together")
    if args.timeout_seconds <= 0:
        ap.error("--timeout-seconds must be greater than zero")

    out = Path(args.out)
    receipt_path = Path(args.receipt) if args.receipt else None
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    if receipt_path is not None and (
        out.exists()
        or receipt_path.exists()
        or (raw_dir is not None and raw_dir.exists() and any(raw_dir.iterdir()))
    ):
        print("FAIL — snapshot paths already exist; refusing to overwrite mutable evidence")
        return 2

    repository_head = git_head()
    source_config_before = source_config_state()
    source_inventory = rss._load_source_inventory()
    configured_sources = [
        source for source in source_inventory if source.get("enabled", True)
    ]
    started_at = datetime.now(timezone.utc).isoformat()
    signals, source_receipts, polled_item_count = build_ledger_with_receipts(
        limit=args.limit,
        raw_dir=raw_dir,
        timeout_seconds=args.timeout_seconds,
        sources=configured_sources,
    )
    synthetic = [s for s in signals if s.get("is_synthetic")]
    if synthetic:
        raise SystemExit(f"bridge bug: {len(synthetic)} rows flagged synthetic")

    write_text_atomic(
        out,
        "".join(json.dumps(sig, ensure_ascii=False, sort_keys=True) + "\n" for sig in signals),
    )
    beats: dict[str, int] = {}
    for sig in signals:
        beats[sig["beat"]] = beats.get(sig["beat"], 0) + 1
    if receipt_path is None or raw_dir is None:
        print(
            f"wrote {out} — {len(signals)} real signals, "
            f"beats={dict(sorted(beats.items()))}; NONCERTIFYING: no source receipt"
        )
        return 0

    completed_at = datetime.now(timezone.utc).isoformat()
    source_config_after = source_config_state()
    receipt = build_receipt(
        out=out,
        raw_dir=raw_dir,
        signals=signals,
        source_receipts=source_receipts,
        polled_item_count=polled_item_count,
        started_at=started_at,
        completed_at=completed_at,
        limit=args.limit,
        configured_source_count=len(configured_sources),
        repository_head=repository_head,
        source_config_before=source_config_before,
        source_config_after=source_config_after,
        source_scope_rows=build_source_scope(source_inventory),
    )
    write_text_atomic(
        receipt_path,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(
        f"wrote {out} and {receipt_path} — {len(signals)} real signals, "
        f"classification={receipt['classification']}, "
        f"source_statuses={receipt['sources']['status_counts']}, "
        f"beats={dict(sorted(beats.items()))}"
    )
    if args.require_complete_sources and receipt["classification"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
