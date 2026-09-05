"""RSS/Atom feed poller using feedparser."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import feedparser
import httpx
import yaml

from centinelas.models import EvidenceTier, RawItem

log = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).parent / "sources.yaml"
_SOURCE_OVERLAYS = (Path(__file__).parent / "just_security_sources.yaml",)
_HTTP_HEADERS = {
    "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml, */*",
    "Accept-Encoding": "identity",
    "User-Agent": "Centinelas/0.1 (+https://github.com/jotaele44/centinelas-pr)",
}


@dataclass(frozen=True)
class FeedResponse:
    content: bytes
    status_code: int
    final_url: str
    content_type: str
    content_encoding: str
    redirect_statuses: tuple[int, ...]


def _fetch_feed(url: str, timeout_seconds: float) -> FeedResponse:
    response = httpx.get(
        url,
        follow_redirects=True,
        headers=_HTTP_HEADERS,
        timeout=timeout_seconds,
    )
    return FeedResponse(
        content=response.content,
        status_code=response.status_code,
        final_url=str(response.url),
        content_type=response.headers.get("content-type", ""),
        content_encoding=response.headers.get("content-encoding", ""),
        redirect_statuses=tuple(item.status_code for item in response.history),
    )


def _raw_filename(index: int, name: str, url: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "source"
    url_digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{index:03d}-{slug[:60]}-{url_digest}.feed"


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


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


def _configured_source(source_id: str) -> dict:
    """Return a configured source view without making code the source of truth."""
    return next(
        (source for source in _load_sources() if source.get("source_id") == source_id),
        {},
    )


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


def poll_all_with_receipts(
    *,
    raw_dir: Path | None = None,
    timeout_seconds: float = 20.0,
    sources: list[dict] | None = None,
) -> tuple[list[RawItem], list[dict]]:
    """Poll configured feeds and return deduplicated items plus source receipts."""
    if sources is None:
        sources = _load_sources()
    seen_ids: set[str] = set()
    items: list[RawItem] = []
    receipts: list[dict] = []

    for index, source in enumerate(sources, start=1):
        url = source.get("url", "")
        name = source.get("name", url)
        tier = source.get("tier", "T2")
        retrieved_at = datetime.now(timezone.utc).isoformat()
        receipt = {
            "source_index": index,
            "configured_source_id": source.get("source_id"),
            "name": name,
            "url": url,
            "tier": tier,
            "filter_term_count": len(source.get("match_any") or []),
            "retrieved_at": retrieved_at,
            "status": "UNRESOLVED",
            "http_status": None,
            "final_url": None,
            "redirect_statuses": [],
            "content_type": None,
            "content_encoding": None,
            "response_content_byte_scope": "decoded_http_entity_body",
            "response_content_bytes": None,
            "response_content_sha256": None,
            "raw_content_path": None,
            "parser_bozo": None,
            "parser_error": None,
            "entries_seen": 0,
            "entries_filtered": 0,
            "entries_without_link": 0,
            "accepted_entries": 0,
            "duplicates_suppressed": 0,
            "emitted_items": 0,
        }

        try:
            response = _fetch_feed(url, timeout_seconds)
            receipt.update(
                {
                    "http_status": response.status_code,
                    "final_url": response.final_url,
                    "redirect_statuses": list(response.redirect_statuses),
                    "content_type": response.content_type,
                    "content_encoding": response.content_encoding,
                    "response_content_bytes": len(response.content),
                    "response_content_sha256": hashlib.sha256(response.content).hexdigest(),
                }
            )
            if raw_dir is not None:
                raw_path = raw_dir / _raw_filename(index, name, url)
                _write_bytes_atomic(raw_path, response.content)
                receipt["raw_content_path"] = raw_path.name
            if not 200 <= response.status_code < 300:
                receipt["status"] = "HTTP_ERROR"
                receipts.append(receipt)
                log.warning("Feed poll returned HTTP %d for %s", response.status_code, name)
                continue

            feed = feedparser.parse(response.content)
            receipt["parser_bozo"] = bool(feed.get("bozo"))
            if feed.get("bozo_exception"):
                receipt["parser_error"] = str(feed["bozo_exception"])
            receipt["entries_seen"] = len(feed.entries)
            for entry in feed.entries:
                if not _source_accepts_entry(entry, source):
                    receipt["entries_filtered"] += 1
                    continue
                item = _entry_to_raw_item(entry, name, tier)
                if item is None:
                    receipt["entries_without_link"] += 1
                    continue
                receipt["accepted_entries"] += 1
                if item.item_id in seen_ids:
                    receipt["duplicates_suppressed"] += 1
                    continue
                seen_ids.add(item.item_id)
                items.append(item)
                receipt["emitted_items"] += 1

            if receipt["parser_bozo"]:
                receipt["status"] = (
                    "PARSE_WARNING_WITH_ROWS"
                    if receipt["emitted_items"]
                    else "PARSE_ERROR"
                )
            elif receipt["emitted_items"]:
                receipt["status"] = "SUCCESS_WITH_ROWS"
            elif receipt["entries_seen"]:
                receipt["status"] = "SUCCESS_FILTERED_EMPTY"
            else:
                receipt["status"] = "SUCCESS_EMPTY"
            log.info(
                "Polled %s: %d entries, %d accepted, %d filtered",
                name,
                len(feed.entries),
                receipt["emitted_items"],
                receipt["entries_filtered"],
            )
        except Exception as exc:
            receipt["status"] = "FETCH_ERROR"
            receipt["parser_error"] = f"{type(exc).__name__}: {exc}"
            log.warning("Feed poll failed for %s: %s", name, exc)
        receipts.append(receipt)

    return items, receipts


def poll_all() -> list[RawItem]:
    """Poll all configured feeds through the historical URL-based adapter."""
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
