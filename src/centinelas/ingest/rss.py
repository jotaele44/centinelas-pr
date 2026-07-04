"""RSS/Atom feed poller using feedparser."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

from centinelas.models import RawItem

log = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).parent / "sources.yaml"


def _load_sources() -> list[dict]:
    with open(_SOURCES_PATH) as f:
        return yaml.safe_load(f).get("feeds", [])


def _parse_date(entry: dict) -> datetime:
    for field in ("published_parsed", "updated_parsed"):
        val = entry.get(field)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
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
        evidence_tier=tier,
    )


def poll_all() -> list[RawItem]:
    """Poll all feeds defined in sources.yaml. Returns deduplicated RawItems."""
    sources = _load_sources()
    seen_ids: set[str] = set()
    items: list[RawItem] = []

    for source in sources:
        url = source.get("url", "")
        name = source.get("name", url)
        tier = source.get("tier", "T2")

        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                item = _entry_to_raw_item(entry, name, tier)
                if item and item.item_id not in seen_ids:
                    seen_ids.add(item.item_id)
                    items.append(item)
            log.info("Polled %s: %d entries", name, len(feed.entries))
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
