"""RSS/Atom feed poller using feedparser."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import feedparser
import yaml

from centinelas.models import EvidenceTier, RawItem

log = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).parent / "sources.yaml"

# Just Security is a global law/policy publication.  It is deliberately filtered
# at intake so the global feed cannot silently flood the Puerto Rico signal
# denominator.  The broader historical/search reconciliation lives in
# tools/just_security_monitor.py; this source configuration is only the
# prospective signal-intake gate.
_JUST_SECURITY_SOURCE = {
    "name": "Just Security",
    "url": "https://www.justsecurity.org/feed/",
    "tier": "T4",
    "source_id": "CENT-SRC-RSS-JUST-SECURITY",
    "match_any": [
        "Puerto Rico",
        "Puerto Rican",
        "Commonwealth of Puerto Rico",
        "PROMESA",
        "Financial Oversight and Management Board",
        "Roosevelt Roads",
        "Fort Buchanan",
        "Vieques",
        "José Aponte de la Torre",
        "Jose Aponte de la Torre",
        "Ramey Air Force Base",
    ],
}


def _load_sources() -> list[dict]:
    with open(_SOURCES_PATH) as f:
        sources = yaml.safe_load(f).get("feeds", [])
    # Keep this code-side registration idempotent.  A future migration may move
    # it into sources.yaml without creating a duplicate feed.
    if not any(source.get("name") == _JUST_SECURITY_SOURCE["name"] for source in sources):
        sources.append(dict(_JUST_SECURITY_SOURCE))
    return sources


def _entry_filter_text(entry: dict) -> str:
    content = entry.get("content") or []
    content_text = " ".join(
        str(block.get("value", "")) for block in content if isinstance(block, dict)
    )
    tags = " ".join(
        str(tag.get("term", "")) for tag in entry.get("tags") or [] if isinstance(tag, dict)
    )
    return " ".join(
        [
            str(entry.get("title", "")),
            str(entry.get("summary", "")),
            content_text,
            tags,
        ]
    ).casefold()


def _source_accepts_entry(entry: dict, source: dict) -> bool:
    terms = [
        str(term).strip().casefold()
        for term in source.get("match_any") or []
        if str(term).strip()
    ]
    if not terms:
        return True
    text = _entry_filter_text(entry)
    return any(term in text for term in terms)


def _parse_date(entry: dict) -> datetime:
    for field in ("published_parsed", "updated_parsed"):
        val = entry.get(field)
        if val:
            try:
                parts = tuple(val[:6])
                return datetime(
                    parts[0], parts[1], parts[2], parts[3], parts[4], parts[5],
                    tzinfo=timezone.utc,
                )
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _entry_to_raw_item(entry: dict, source_name: str, tier: str) -> RawItem | None:
    url = entry.get("link", "")
    if not url:
        return None

    title = entry.get("title", "").strip()
    body = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")

    published_at = _parse_date(entry)
    item_id = RawItem.make_id(url, published_at)

    return RawItem(
        item_id=item_id,
        source_url=url,
        source_name=source_name,
        title=title,
        body_text=body,
        published_at=published_at,
        captured_at=datetime.now(timezone.utc),
        # EvidenceTier is a typing.Literal alias — not callable; pydantic
        # validates the value against the Literal on the model.
        evidence_tier=cast(EvidenceTier, tier),
    )


def poll_all() -> list[RawItem]:
    """Poll all feeds defined in sources.yaml plus bounded code-registered sources."""
    sources = _load_sources()
    seen_ids: set[str] = set()
    items: list[RawItem] = []

    for source in sources:
        url = source.get("url", "")
        name = source.get("name", url)
        tier = source.get("tier", "T2")
        accepted = 0
        rejected = 0

        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if not _source_accepts_entry(entry, source):
                    rejected += 1
                    continue
                item = _entry_to_raw_item(entry, name, tier)
                if item and item.item_id not in seen_ids:
                    seen_ids.add(item.item_id)
                    items.append(item)
                    accepted += 1
            log.info(
                "Polled %s: %d entries, %d accepted, %d filtered",
                name,
                len(feed.entries),
                accepted,
                rejected,
            )
        except Exception as exc:
            log.warning("Feed poll failed for %s: %s", name, exc)

    return items


def poll_feed(url: str, source_name: str = "", tier: str = "T2") -> list[RawItem]:
    """Poll a single feed URL."""
    seen_ids: set[str] = set()
    items: list[RawItem] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            item = _entry_to_raw_item(entry, source_name or url, tier)
            if item and item.item_id not in seen_ids:
                seen_ids.add(item.item_id)
                items.append(item)
    except Exception as exc:
        log.warning("Feed poll failed for %s: %s", url, exc)
    return items
