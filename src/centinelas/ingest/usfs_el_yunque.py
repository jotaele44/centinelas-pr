"""Deterministic USDA Forest Service El Yunque access-status parser.

This module treats the official Forest Service page as T1 status evidence only.
It never creates geometry. Exact asset keys are emitted only for configured names
or the explicitly named Los Picachos-to-peak segment.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

LISTING_URL = "https://www.fs.usda.gov/r08/elyunque/alerts"
_HEADERS = {"User-Agent": "centinelas-monitor/1.0", "Accept": "text/html,application/xhtml+xml"}
_DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b", re.I)
_ORDER_RE = re.compile(r"(?:Forest\s+Order|Order)\s*(?:No\.?|#)?\s*([A-Z0-9-]{4,})", re.I)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def _first_date(text: str) -> datetime | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime.strptime(" ".join(m.groups()), "%B %d %Y").replace(tzinfo=timezone.utc)
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
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        title = " ".join(a.get_text(" ", strip=True).split())
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


def _scope_contexts(title: str, text: str, bindings: dict) -> list[Scope]:
    folded = _fold(f"{title}\n{text}")
    scopes: list[Scope] = []
    for needle, spec in bindings.items():
        if _fold(needle) in folded:
            scopes.append(Scope(spec["scope_type"], spec["scope_name"], spec["asset_key"], folded))

    # Only bind this partial trail closure when BOTH endpoints/scope and closure language
    # are present in the official text. This is a semantic segment key, not geometry.
    if "los picachos" in folded and "el yunque" in folded and ("closed" in folded or "closure" in folded):
        scopes.append(Scope(
            "trail_segment",
            "El Yunque Trail — Los Picachos spur to peak",
            "elyunque.trail.el_yunque.los_picachos_to_peak",
            folded,
        ))

    if not scopes:
        scopes.append(Scope("unknown", title.strip() or "Unresolved El Yunque alert scope", None, folded))
    # stable de-duplication by asset/scope name
    uniq: dict[tuple[str | None, str], Scope] = {}
    for scope in scopes:
        uniq[(scope.asset_key, scope.scope_name)] = scope
    return list(uniq.values())


def infer_status(text: str, now: datetime, effective_start: datetime | None) -> tuple[str, str]:
    folded = _fold(text)
    if effective_start and effective_start > now:
        return "scheduled", "explicit_official_text"
    if any(p in folded for p in ("reopened", "re-opened", "closure has ended", "now open", "open to the public")):
        return "closure_ended", "explicit_official_text"
    partial = any(p in folded for p in ("portion", "segment", "from los picachos", "beyond los picachos", "partially closed"))
    if partial and any(p in folded for p in ("closed", "closure", "restricted")):
        return "restricted", "explicit_official_text"
    if any(p in folded for p in ("remains closed", "is closed", "are closed", "closure", "closed to")):
        return "closed", "explicit_official_text"
    if any(p in folded for p in ("restricted", "restriction")):
        return "restricted", "explicit_official_text"
    return "unknown", "explicit_official_text"


def semantic_hash(record: dict) -> str:
    material = {k: record.get(k) for k in (
        "alert_id", "scope_type", "scope_name", "asset_key", "status",
        "effective_start", "effective_end", "forest_order_identifier", "restriction_text"
    )}
    return _sha(json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def parse_alert(*, title: str, url: str, detail_html: str, observed_at: datetime, bindings: dict,
                listing_confirmed: bool = True) -> list[dict]:
    soup = BeautifulSoup(detail_html, "html.parser")
    text = " ".join(soup.stripped_strings)
    effective_start = _first_date(text)
    order = _ORDER_RE.search(text)
    source_hash = _sha(detail_html)
    alert_id = "usfs-elyunque-" + _sha(url)[:20]
    rows: list[dict] = []
    for scope in _scope_contexts(title, text, bindings):
        status, basis = infer_status(scope.context, observed_at, effective_start)
        row = {
            "schema_version": "1.0", "kind": "access_condition",
            "condition_id": f"{alert_id}:{_sha((scope.asset_key or scope.scope_name))[:16]}",
            "alert_id": alert_id, "authority": "USDA Forest Service", "forest": "el_yunque",
            "source_listing_url": LISTING_URL, "source_url": url, "source_hash": source_hash,
            "forest_order_identifier": order.group(1) if order else None,
            "published_at": None, "last_source_update": None,
            "effective_start": _iso(effective_start), "effective_end": None,
            "observed_at": _iso(observed_at), "evidence_tier": "T1",
            "scope_type": scope.scope_type, "scope_name": scope.scope_name, "asset_key": scope.asset_key,
            "status": status, "status_basis": basis, "confidence": 1.0,
            "restriction_text": " ".join(text.split())[:4000],
            "corroboration": {
                "authority_count": 1, "document_count": 2 if listing_confirmed else 1,
                "listing_confirmed": listing_confirmed, "detail_confirmed": True,
                "forest_order_confirmed": bool(order),
            },
        }
        row["semantic_hash"] = semantic_hash(row)
        rows.append(row)
    return rows


def load_bindings(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["asset_bindings"]
