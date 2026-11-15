#!/usr/bin/env python3
"""Stateful T1 monitor for official USDA Forest Service El Yunque access alerts.

Internal federation plumbing: deterministic HTML parsing, semantic access-state
transitions, fail-closed persistence, and idempotent centinelas-handoff delivery.
No geometry is created or accepted here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from jsonschema import validate

REPO = Path(__file__).resolve().parent.parent
LISTING_URL = "https://www.fs.usda.gov/r08/elyunque/alerts"
CONFIG = REPO / "config" / "el_yunque_access_monitor.json"
SCHEMA = REPO / "schemas" / "access_condition.v1.schema.json"
STATE = REPO / "data" / "monitoring" / "el_yunque" / "current.json"
TRANSITIONS_DIR = REPO / "data" / "monitoring" / "el_yunque" / "transitions"
STATE_REPAIRS = REPO / "data" / "monitoring" / "el_yunque" / "state_repairs.jsonl"
HEALTH = REPO / "data" / "monitoring" / "el_yunque" / "health.json"
# Each monthly segment must stay far below GitHub's 100 MB hard per-file limit.
SEGMENT_BYTE_LIMIT = 50 * 1024 * 1024
REMOVAL_MARKER = " [official alert absent from latest listing; reopening not inferred]"
OUTBOX = REPO / ".centinelas" / "outbound" / "el_yunque_access"
GITHUB_API = "https://api.github.com"
_HEADERS = {"User-Agent": "centinelas-monitor/1.0", "Accept": "text/html,application/xhtml+xml"}
_DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b", re.I)
_ORDER_RE = re.compile(r"(?:Forest\s+Order|Order)\s*(?:No\.?|#)?\s*([A-Z0-9-]{4,})", re.I)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def first_date(text: str) -> datetime | None:
    match = _DATE_RE.search(text or "")
    if not match:
        return None
    try:
        return datetime.strptime(" ".join(match.groups()), "%B %d %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_html(url: str) -> str:
    with httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True, trust_env=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def listing_links(html: str, base_url: str = LISTING_URL) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"])
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not title or "/alerts/" not in href or href.rstrip("/") == base_url.rstrip("/"):
            continue
        found[href] = title
    return sorted(found.items())


@dataclass(frozen=True)
class Scope:
    scope_type: str
    scope_name: str
    asset_key: str | None
    context: str


def local_context(title: str, text: str, needle: str) -> str:
    wanted = fold(needle)
    parts = [part.strip() for part in _SENTENCE_RE.split(text) if part.strip()]
    matched = [part for part in parts if wanted in fold(part)]
    return " ".join([title, *matched]) if matched else title


def scope_contexts(title: str, text: str, bindings: dict) -> list[Scope]:
    folded_all = fold(f"{title}\n{text}")
    scopes: list[Scope] = []
    for needle, spec in bindings.items():
        if fold(needle) in folded_all:
            scopes.append(Scope(
                spec["scope_type"], spec["scope_name"], spec["asset_key"],
                local_context(title, text, needle),
            ))
    for part in [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]:
        candidate = fold(part)
        if (
            "los picachos" in candidate
            and "el yunque" in candidate
            and any(word in candidate for word in ("closed", "closure", "restricted"))
        ):
            scopes.append(Scope(
                "trail_segment",
                "El Yunque Trail — Los Picachos spur to peak",
                "elyunque.trail.el_yunque.los_picachos_to_peak",
                f"{title} {part}",
            ))
            break
    if not scopes:
        scopes.append(Scope("unknown", title.strip() or "Unresolved El Yunque alert scope", None, f"{title} {text}"))
    unique: dict[tuple[str | None, str], Scope] = {}
    for scope in scopes:
        unique[(scope.asset_key, scope.scope_name)] = scope
    return list(unique.values())


def infer_status(text: str, now: datetime, effective_start: datetime | None) -> tuple[str, str]:
    normalized = fold(text)
    if effective_start and effective_start > now:
        return "scheduled", "explicit_official_text"
    if any(p in normalized for p in ("reopened", "re-opened", "closure has ended", "now open", "open to the public")):
        return "closure_ended", "explicit_official_text"
    partial = any(p in normalized for p in ("portion", "segment", "from los picachos", "beyond los picachos", "partially closed"))
    if partial and any(p in normalized for p in ("closed", "closure", "restricted")):
        return "restricted", "explicit_official_text"
    if any(p in normalized for p in ("remains closed", "is closed", "are closed", "closure", "closed to")):
        return "closed", "explicit_official_text"
    if any(p in normalized for p in ("restricted", "restriction")):
        return "restricted", "explicit_official_text"
    return "unknown", "explicit_official_text"


def semantic_hash(record: dict) -> str:
    material = {key: record.get(key) for key in (
        "alert_id", "scope_type", "scope_name", "asset_key", "status",
        "effective_start", "effective_end", "forest_order_identifier", "restriction_text"
    )}
    return sha(json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def parse_alert(*, title: str, url: str, detail_html: str, observed_at: datetime, bindings: dict,
                listing_confirmed: bool = True) -> list[dict]:
    soup = BeautifulSoup(detail_html, "html.parser")
    text = "\n".join(value.strip() for value in soup.stripped_strings if value.strip())
    order = _ORDER_RE.search(text)
    source_hash = sha(detail_html)
    alert_id = "usfs-elyunque-" + sha(url)[:20]
    scopes = scope_contexts(title, text, bindings)
    page_start = first_date(text) if len(scopes) == 1 else None
    rows: list[dict] = []
    for scope in scopes:
        effective_start = first_date(scope.context) or page_start
        status, basis = infer_status(scope.context, observed_at, effective_start)
        row = {
            "schema_version": "1.0", "kind": "access_condition",
            "condition_id": f"{alert_id}:{sha(scope.asset_key or scope.scope_name)[:16]}",
            "alert_id": alert_id, "authority": "USDA Forest Service", "forest": "el_yunque",
            "source_listing_url": LISTING_URL, "source_url": url, "source_hash": source_hash,
            "forest_order_identifier": order.group(1) if order else None,
            "published_at": None, "last_source_update": None,
            "effective_start": iso(effective_start), "effective_end": None,
            "observed_at": iso(observed_at), "evidence_tier": "T1",
            "scope_type": scope.scope_type, "scope_name": scope.scope_name, "asset_key": scope.asset_key,
            "status": status, "status_basis": basis, "confidence": 1.0,
            "restriction_text": " ".join(scope.context.split())[:4000],
            "corroboration": {
                "authority_count": 1, "document_count": 2 if listing_confirmed else 1,
                "listing_confirmed": listing_confirmed, "detail_confirmed": True,
                "forest_order_confirmed": bool(order),
            },
        }
        row["semantic_hash"] = semantic_hash(row)
        rows.append(row)
    return rows


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def jsonl_lines(rows: list[dict]) -> list[str]:
    return [json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows]


def transitions_segment(now: datetime) -> Path:
    """Monthly append-only segment; one unbounded file outgrew GitHub's 100 MB limit."""
    return TRANSITIONS_DIR / f"{now.astimezone(timezone.utc):%Y-%m}.jsonl"


def ensure_segment_capacity(path: Path, lines: list[str], limit: int = SEGMENT_BYTE_LIMIT) -> None:
    """Fail closed before any state is written if an append would cross the segment ceiling."""
    existing = path.stat().st_size if path.exists() else 0
    added = sum(len(line.encode("utf-8")) for line in lines)
    if existing + added > limit:
        raise RuntimeError(
            f"transition segment {path.name} would reach {existing + added} bytes (limit {limit}); "
            "refusing to persist a run that cannot be pushed"
        )


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for line in jsonl_lines(rows):
            handle.write(line)


def strip_removal_markers(text: str) -> tuple[str, int]:
    """Remove every trailing removal marker; return the base text and how many were removed."""
    count = 0
    while text.endswith(REMOVAL_MARKER):
        text = text[: -len(REMOVAL_MARKER)]
        count += 1
    return text, count


def removed_unknown(previous: dict, now: datetime) -> dict:
    """Mark an alert absent from the listing as unknown, exactly once.

    The marker is appended to the base text a single time. A condition that is already
    recorded as removal_unconfirmed with that text is returned unchanged, so repeated
    absence is not a new semantic state and produces no transition or handoff.
    """
    base, _ = strip_removal_markers(previous.get("restriction_text") or "")
    text = base + REMOVAL_MARKER
    if (
        previous.get("status") == "unknown"
        and previous.get("status_basis") == "removal_unconfirmed"
        and previous.get("restriction_text") == text
    ):
        return previous
    row = dict(previous)
    row.update({
        "status": "unknown", "status_basis": "removal_unconfirmed",
        "observed_at": now.isoformat(), "confidence": 1.0,
        "restriction_text": text,
    })
    row["semantic_hash"] = semantic_hash(row)
    return row


def normalize_state(previous: dict[str, dict], now: datetime) -> tuple[dict[str, dict], list[dict]]:
    """Collapse removal markers that earlier, non-idempotent runs stacked onto persisted state.

    Returns the repaired state and one explicit receipt per repaired condition. Receipts are
    written to STATE_REPAIRS rather than the transition log: the repair corrects this
    monitor's own derived state, not an official observation, so it is never handed off.
    """
    repaired: dict[str, dict] = {}
    receipts: list[dict] = []
    for condition_id, row in previous.items():
        text = row.get("restriction_text") or ""
        base, count = strip_removal_markers(text)
        if count <= 1:
            repaired[condition_id] = row
            continue
        fixed = dict(row)
        fixed["restriction_text"] = base + REMOVAL_MARKER
        fixed["semantic_hash"] = semantic_hash(fixed)
        repaired[condition_id] = fixed
        receipts.append({
            "repaired_at": now.isoformat(),
            "condition_id": condition_id,
            "reason": "collapse_stacked_removal_markers",
            "markers_before": count,
            "markers_after": 1,
            "restriction_text_bytes_before": len(text.encode("utf-8")),
            "restriction_text_bytes_after": len(fixed["restriction_text"].encode("utf-8")),
            "semantic_hash_before": row.get("semantic_hash"),
            "semantic_hash_after": fixed["semantic_hash"],
        })
    return repaired, receipts


def time_activate(row: dict, now: datetime) -> dict:
    if row.get("status") != "scheduled" or not row.get("effective_start"):
        return row
    try:
        start = datetime.fromisoformat(row["effective_start"].replace("Z", "+00:00"))
    except ValueError:
        return row
    if start > now:
        return row
    activated = dict(row)
    activated.update({"status": "closed", "status_basis": "effective_time", "observed_at": now.isoformat()})
    activated["semantic_hash"] = semantic_hash(activated)
    return activated


def compute_transitions(previous: dict[str, dict], observed: list[dict], now: datetime) -> tuple[dict[str, dict], list[dict]]:
    observed_by_id = {row["condition_id"]: time_activate(row, now) for row in observed}
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
        row = removed_unknown(old, now)
        current[condition_id] = row
        if old.get("semantic_hash") != row.get("semantic_hash"):
            transitions.append({"transition_at": now.isoformat(), "previous": old, "current": row})
    return current, transitions


def envelope(row: dict) -> dict:
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = sha(canonical)
    key = f"centinelas:{row['condition_id']}:aguayluz-pr:{digest[:20]}"
    return {"schema_version": "1.0", "kind": "access_condition", "item_id": row["condition_id"], "target": "aguayluz-pr", "idempotency_key": key, "signal": row}


def stage(transitions: list[dict]) -> list[Path]:
    staged: list[Path] = []
    for transition in transitions:
        payload = envelope(transition["current"])
        path = OUTBOX / f"{payload['idempotency_key'].replace(':', '_')}.json"
        write_json(path, payload)
        staged.append(path)
    return staged


def dispatch(staged: list[Path], *, dry_run: bool) -> None:
    token = os.environ.get("FEDERATION_DISPATCH_TOKEN") or os.environ.get("CENTINELAS_GITHUB_TOKEN")
    if not dry_run and not token:
        raise RuntimeError("FEDERATION_DISPATCH_TOKEN or CENTINELAS_GITHUB_TOKEN is required")
    for path in staged:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if dry_run:
            print(f"[dry-run] centinelas-handoff -> aguayluz-pr {payload['idempotency_key']}")
            continue
        request = urllib.request.Request(
            f"{GITHUB_API}/repos/jotaele44/aguayluz-pr/dispatches",
            data=json.dumps({"event_type": "centinelas-handoff", "client_payload": payload}).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 204:
                raise RuntimeError(f"unexpected dispatch HTTP {response.status}")


def poll(now: datetime, previous: dict[str, dict] | None = None) -> list[dict]:
    previous = previous or {}
    cfg = read_json(CONFIG, {})
    bindings = cfg["asset_bindings"]
    listing_html = fetch_html(cfg.get("source_listing_url", LISTING_URL))
    links = listing_links(listing_html, cfg.get("source_listing_url", LISTING_URL))
    if not links:
        raise RuntimeError("official alerts listing parsed zero detail links")
    records: list[dict] = []
    for url, title in links:
        try:
            detail = fetch_html(url)
        except Exception as exc:
            print(f"detail unavailable {url}: {exc}; preserving prior state for this alert")
            records.extend(row for row in previous.values() if row.get("source_url") == url)
            continue
        records.extend(parse_alert(title=title, url=url, detail_html=detail, observed_at=now, bindings=bindings))
    if not records:
        raise RuntimeError("official alerts yielded zero access-condition records")
    schema = read_json(SCHEMA, {})
    for row in records:
        validate(instance=row, schema=schema)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-dispatch", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    previous, repairs = normalize_state(read_json(STATE, {}), now)
    try:
        observed = poll(now, previous)
    except Exception as exc:
        write_json(HEALTH, {"status": "stale", "checked_at": now.isoformat(), "last_error": str(exc), "preserved_condition_count": len(previous)})
        print(f"monitor stale; preserved {len(previous)} condition(s): {exc}")
        return 2
    current, transitions = compute_transitions(previous, observed, now)
    segment = transitions_segment(now)
    try:
        ensure_segment_capacity(segment, jsonl_lines(transitions))
    except RuntimeError as exc:
        write_json(HEALTH, {"status": "stale", "checked_at": now.isoformat(), "last_error": str(exc), "preserved_condition_count": len(previous)})
        print(f"monitor stale; {exc}")
        return 3
    append_jsonl(STATE_REPAIRS, repairs)
    write_json(STATE, current)
    append_jsonl(segment, transitions)
    write_json(HEALTH, {"status": "healthy", "checked_at": now.isoformat(), "condition_count": len(current), "transition_count": len(transitions), "state_repair_count": len(repairs)})
    staged = stage(transitions)
    if staged and not args.no_dispatch:
        dispatch(staged, dry_run=args.dry_run)
    print(f"conditions={len(current)} transitions={len(transitions)} staged={len(staged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
