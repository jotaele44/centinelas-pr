#!/usr/bin/env python3
"""Poll official El Yunque alerts and emit only semantic access transitions.

Failure policy: network/parser failures never imply reopening. Existing state is
preserved and health is marked stale. Alert disappearance creates an UNKNOWN
removal_unconfirmed transition rather than OPEN/CLOSURE_ENDED.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import validate

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from centinelas.ingest.usfs_el_yunque import (  # noqa: E402
    LISTING_URL, fetch_html, listing_links, load_bindings, parse_alert, semantic_hash
)

CONFIG = REPO / "config" / "el_yunque_access_monitor.json"
SCHEMA = REPO / "schemas" / "access_condition.v1.schema.json"
STATE = REPO / "data" / "monitoring" / "el_yunque" / "current.json"
TRANSITIONS = REPO / "data" / "monitoring" / "el_yunque" / "transitions.jsonl"
HEALTH = REPO / "data" / "monitoring" / "el_yunque" / "health.json"
OUTBOX = REPO / ".centinelas" / "outbound" / "el_yunque_access"
GITHUB_API = "https://api.github.com"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _removed_unknown(previous: dict, now: datetime) -> dict:
    row = dict(previous)
    row.update({
        "status": "unknown",
        "status_basis": "removal_unconfirmed",
        "observed_at": now.isoformat(),
        "confidence": 1.0,
        "restriction_text": previous.get("restriction_text", "") + " [official alert absent from latest listing; reopening not inferred]",
    })
    row["semantic_hash"] = semantic_hash(row)
    return row


def _time_activate(row: dict, now: datetime) -> dict:
    if row.get("status") != "scheduled" or not row.get("effective_start"):
        return row
    try:
        start = datetime.fromisoformat(row["effective_start"].replace("Z", "+00:00"))
    except ValueError:
        return row
    if start > now:
        return row
    activated = dict(row)
    activated["status"] = "closed"
    activated["status_basis"] = "effective_time"
    activated["observed_at"] = now.isoformat()
    activated["semantic_hash"] = semantic_hash(activated)
    return activated


def compute_transitions(previous: dict[str, dict], observed: list[dict], now: datetime) -> tuple[dict[str, dict], list[dict]]:
    observed_by_id = {r["condition_id"]: _time_activate(r, now) for r in observed}
    current: dict[str, dict] = {}
    transitions: list[dict] = []

    for condition_id, row in observed_by_id.items():
        old = previous.get(condition_id)
        current[condition_id] = row
        if old is None or old.get("semantic_hash") != row.get("semantic_hash"):
            transitions.append({"transition_at": now.isoformat(), "previous": old, "current": row})

    for condition_id, old in previous.items():
        if condition_id in observed_by_id:
            continue
        row = _removed_unknown(old, now)
        current[condition_id] = row
        if old.get("semantic_hash") != row.get("semantic_hash"):
            transitions.append({"transition_at": now.isoformat(), "previous": old, "current": row})

    return current, transitions


def _envelope(row: dict) -> dict:
    import hashlib
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    key = f"centinelas:{row['condition_id']}:aguayluz-pr:{digest[:20]}"
    return {
        "schema_version": "1.0", "kind": "access_condition", "item_id": row["condition_id"],
        "target": "aguayluz-pr", "idempotency_key": key, "signal": row,
    }


def stage(transitions: list[dict]) -> list[Path]:
    staged: list[Path] = []
    for transition in transitions:
        row = transition["current"]
        envelope = _envelope(row)
        path = OUTBOX / f"{envelope['idempotency_key'].replace(':', '_')}.json"
        _write_json(path, envelope)
        staged.append(path)
    return staged


def dispatch(staged: list[Path], *, dry_run: bool) -> None:
    token = os.environ.get("FEDERATION_DISPATCH_TOKEN") or os.environ.get("CENTINELAS_GITHUB_TOKEN")
    if not dry_run and not token:
        raise RuntimeError("FEDERATION_DISPATCH_TOKEN or CENTINELAS_GITHUB_TOKEN is required")
    for path in staged:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if dry_run:
            print(f"[dry-run] centinelas-handoff -> aguayluz-pr {envelope['idempotency_key']}")
            continue
        request = urllib.request.Request(
            f"{GITHUB_API}/repos/jotaele44/aguayluz-pr/dispatches",
            data=json.dumps({"event_type": "centinelas-handoff", "client_payload": envelope}).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 204:
                raise RuntimeError(f"unexpected dispatch HTTP {response.status}")


def poll(now: datetime) -> list[dict]:
    cfg = _read_json(CONFIG, {})
    bindings = load_bindings(CONFIG)
    listing_html = fetch_html(cfg.get("source_listing_url", LISTING_URL))
    links = listing_links(listing_html, cfg.get("source_listing_url", LISTING_URL))
    if not links:
        raise RuntimeError("official alerts listing parsed zero detail links")
    records: list[dict] = []
    for url, title in links:
        try:
            detail = fetch_html(url)
        except Exception as exc:
            print(f"detail unavailable {url}: {exc}", file=sys.stderr)
            continue
        records.extend(parse_alert(title=title, url=url, detail_html=detail, observed_at=now, bindings=bindings))
    if not records:
        raise RuntimeError("official alerts yielded zero access-condition records")
    schema = _read_json(SCHEMA, {})
    for row in records:
        validate(instance=row, schema=schema)
    return records


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-dispatch", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    previous = _read_json(STATE, {})
    try:
        observed = poll(now)
    except Exception as exc:
        _write_json(HEALTH, {"status": "stale", "checked_at": now.isoformat(), "last_error": str(exc), "preserved_condition_count": len(previous)})
        print(f"monitor stale; preserved {len(previous)} condition(s): {exc}", file=sys.stderr)
        return 2

    current, transitions = compute_transitions(previous, observed, now)
    _write_json(STATE, current)
    _append_jsonl(TRANSITIONS, transitions)
    _write_json(HEALTH, {"status": "healthy", "checked_at": now.isoformat(), "condition_count": len(current), "transition_count": len(transitions)})
    staged = stage(transitions)
    if staged and not args.no_dispatch:
        dispatch(staged, dry_run=args.dry_run)
    print(f"conditions={len(current)} transitions={len(transitions)} staged={len(staged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
