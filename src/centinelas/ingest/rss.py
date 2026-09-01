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
_SOURCE_OVERLAYS = (Path(__file__).parent / "just_security_sources.yaml",)


def _load_source_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    feeds = payload.get("feeds", [])
    return [dict(feed) for feed in feeds if isinstance(feed, dict)]


def _load_sources() -> list[dict]:
    """Load the base source registry plus packaged source overlays idempotently."""
    sources = _load_source_file(_SOURCES_PATH)
    known_ids = {source.get("source_id") for source in sources if source.get("source_id")}
    known_urls = {source.get("url") for source in sources if source.get("url")}
    for overlay in _SOURCE_OVERLAYS:
        for source in _load_source_file(overlay):
            source_id = source.get("source_id")
            url = source.get("url")
            if (source_id and source_id in known_ids) or (url and url in known_urls):
                continue
            sources.append(source)
            if source_id:
                known_ids.add(source_id)
            if url:
                known_urls.add(url)
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
                    parts[0],
                    parts[1],
                    parts[2],
                    parts[3],
                    parts[4],
                    parts[5],
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
    content = entry.get("content") or []
    content_body = ""
    if content and isinstance(content[0], dict):
        content_body = str(content[0].get("value", ""))
    body = entry.get("summary", "") or content_body

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
    """Poll all configured feeds and return deduplicated RawItems."""
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
