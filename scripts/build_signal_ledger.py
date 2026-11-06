#!/usr/bin/env python3
"""Bridge the live intake engine into the federation signal ledger.

The engine (src/centinelas) ingests real RSS feeds and classifies items, but
its output (`ClassifiedItem`) never reached `data/signals/` — the federation
export could only read the synthetic seed ledger, so `--mode production` was
permanently refused. This bridge closes that gap:

    RSS + Federal Register + listing scrapers -> per-source cap -> classify()
        -> signal rows -> data/signals/live_signals.jsonl

Every emitted row is a REAL public signal (`is_synthetic: false`) captured
from the configured sources at run time (stage `raw_observation`, one matter
per item). The ledger polls the same three intake layers as `centinelas run`:
RSS/Atom feeds (including the DRNA permit and notice categories), the Federal
Register API (USACE/EPA, Puerto Rico) and the listing scrapers (OGPe, JP, ASG,
EPA Region 2 NPDES). A per-source cap keeps any single high-volume feed from
crowding the Puerto Rico permit sources out of a bounded ledger: the old
first-N cut over RSS alone dropped every DRNA feed, because they are listed
last in sources.yaml. Other pre-officialization families in the registry
(legislative calendars, municipal agendas, ...) remain future intake.

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
    python scripts/build_signal_ledger.py --per-source 10 --limit 300
    python scripts/build_signal_ledger.py --rss-only --limit 100   # previous behaviour
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
from centinelas.ingest.federal_register import poll_federal_register  # noqa: E402
from centinelas.ingest.web import poll_scrape_sources  # noqa: E402
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


def collect_raw_items(rss_only: bool = False) -> list:
    """Poll every intake layer and merge, deduping by item_id in first-seen order."""
    layers = [rss.poll_all()]
    if not rss_only:
        layers += [poll_federal_register(), poll_scrape_sources()]
    seen: set[str] = set()
    merged: list = []
    for items in layers:
        for item in items:
            if item.item_id not in seen:
                seen.add(item.item_id)
                merged.append(item)
    return merged


def cap_items(items: list, per_source: int | None = None, total: int | None = None) -> list:
    """Bound the ledger without letting one source crowd out the rest.

    Keeps at most ``per_source`` items from each source (in poll order), then
    takes items round-robin across sources until ``total`` is reached, so a
    total cap removes items from the largest sources first rather than dropping
    whole sources that happen to be polled last.
    """
    by_source: dict[str, list] = {}
    for item in items:
        bucket = by_source.setdefault(item.source_name, [])
        if per_source is None or len(bucket) < per_source:
            bucket.append(item)
    queues = list(by_source.values())
    out: list = []
    depth = 0
    while any(depth < len(q) for q in queues):
        for q in queues:
            if depth < len(q):
                if total is not None and len(out) >= total:
                    return out
                out.append(q[depth])
        depth += 1
    return out


def build_ledger(
    limit: int | None = None,
    per_source: int | None = None,
    rss_only: bool = False,
) -> list[dict]:
    raw_items = collect_raw_items(rss_only=rss_only)
    if not raw_items:
        raise SystemExit("FAIL — no feeds returned items; refusing to write an empty live ledger")
    raw_items = cap_items(raw_items, per_source=per_source, total=limit or None)
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
    ap.add_argument("--limit", type=int, default=None, help="total row cap")
    ap.add_argument("--per-source", type=int, default=None, help="row cap per source")
    ap.add_argument("--rss-only", action="store_true",
                    help="poll RSS feeds only (skip Federal Register and scrapers)")
    args = ap.parse_args(argv)

    signals = build_ledger(limit=args.limit, per_source=args.per_source, rss_only=args.rss_only)
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
