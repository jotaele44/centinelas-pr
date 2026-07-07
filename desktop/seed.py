"""Seed the local pipeline state from the committed signal ledgers.

The dashboard API reads .centinelas/{queue,classified,dispatched}/*.json,
which are empty on a fresh clone even though real signals are committed in
data/signals/*.jsonl. This converts those ledger rows into ClassifiedItem
JSON files so the desktop app opens with the committed signal replay
instead of an empty pipeline.

Only runs when the classified directory is empty — real pipeline state is
never overwritten. Seeded rows carry "seeded_from_ledger": true.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGERS = [
    REPO_ROOT / "data" / "signals" / "live_signals.jsonl",
    REPO_ROOT / "data" / "signals" / "example_signals.jsonl",
]
DATA_DIR = Path(os.environ.get("CENTINELAS_DATA_DIR", str(REPO_ROOT / ".centinelas")))
CLASSIFIED_DIR = DATA_DIR / "classified"


def source_name(source_id: str) -> str:
    # CENT-SRC-RSS-THE-DRIVE-WAR-ZONE -> "The Drive War Zone"
    slug = source_id.removeprefix("CENT-SRC-RSS-").removeprefix("CENT-SRC-")
    return slug.replace("-", " ").title() or source_id


def item_from_signal(row: dict) -> dict | None:
    signal_id = row.get("signal_id") or ""
    item_id = signal_id.rsplit("-", 1)[-1].lower()
    if not item_id or not row.get("source_url") or not row.get("published_at"):
        return None
    confidence = float(row.get("confidence_score") or 0.0) / 100.0
    return {
        "item_id": item_id,
        "source_url": row["source_url"],
        "source_name": source_name(row.get("source_id") or ""),
        "title": row.get("title") or "(untitled signal)",
        "body_text": row.get("summary") or "",
        "published_at": row["published_at"],
        "captured_at": row.get("captured_at") or row["published_at"],
        "evidence_tier": row.get("evidence_tier") or "T2",
        "labels": row.get("labels") or ["UNCLASSIFIED"],
        "confidence": max(0.0, min(confidence, 1.0)),
        "classifier_reasoning": (
            f"Seeded from committed signal ledger (beat: {row.get('beat') or 'unclassified'}, "
            f"stage: {row.get('signal_stage') or 'unknown'})."
        ),
        "seeded_from_ledger": True,
    }


def seed(force: bool = False) -> int:
    if CLASSIFIED_DIR.exists() and any(CLASSIFIED_DIR.glob("*.json")) and not force:
        print("Pipeline state already present — not seeding (use --force to reseed).")
        return 0
    CLASSIFIED_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for ledger in LEDGERS:
        if not ledger.exists():
            continue
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = item_from_signal(row)
            if item is None:
                continue
            path = CLASSIFIED_DIR / f"{item['item_id']}.json"
            if not path.exists():
                path.write_text(json.dumps(item, indent=2), encoding="utf-8")
                written += 1
    print(f"Seeded {written} classified items from the committed ledgers → {CLASSIFIED_DIR}")
    return written


if __name__ == "__main__":
    seed(force="--force" in sys.argv[1:])
