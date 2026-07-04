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
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from centinelas.classify.classifier import classify  # noqa: E402
from centinelas.ingest import rss  # noqa: E402
from centinelas.models import ClassifiedItem  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "data" / "signals" / "live_signals.jsonl"


def feed_source_id(feed_name: str) -> str:
    """Deterministic registry id for a feed — mirrored in source_registry.csv."""
    slug = re.sub(r"[^A-Z0-9]+", "-", feed_name.upper()).strip("-")
    return f"CENT-SRC-RSS-{slug}"


def source_name_to_id() -> dict[str, str]:
    return {src["name"]: feed_source_id(src["name"]) for src in rss._load_sources()}


def item_to_signal(item: ClassifiedItem, source_ids: dict[str, str]) -> dict:
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
    }


def build_ledger(limit: int | None = None) -> list[dict]:
    raw_items = rss.poll_all()
    if not raw_items:
        raise SystemExit("FAIL — no feeds returned items; refusing to write an empty live ledger")
    if limit:
        raw_items = raw_items[:limit]
    source_ids = source_name_to_id()
    signals = []
    for raw in raw_items:
        labels, confidence, reasoning = classify(raw)
        classified = ClassifiedItem(
            **raw.model_dump(), labels=labels, confidence=confidence,
            classifier_reasoning=reasoning,
        )
        signals.append(item_to_signal(classified, source_ids))
    return signals


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Materialize real signals into the federation ledger.")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    signals = build_ledger(limit=args.limit)
    synthetic = [s for s in signals if s.get("is_synthetic")]
    if synthetic:
        raise SystemExit(f"bridge bug: {len(synthetic)} rows flagged synthetic")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for sig in signals:
            fh.write(json.dumps(sig, ensure_ascii=False, sort_keys=True) + "\n")
    beats: dict[str, int] = {}
    for sig in signals:
        beats[sig["beat"]] = beats.get(sig["beat"], 0) + 1
    print(f"wrote {out} — {len(signals)} real signals, beats={dict(sorted(beats.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
