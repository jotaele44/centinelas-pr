"""Federal Register JSON API poller.

Federal coastal/environmental permit actions touching Puerto Rico do not surface
through a usable RSS feed — the USACE district notice feeds carry only opaque
permit-ID stubs (no body, no location). The Federal Register JSON API, by
contrast, lets us filter server-side by search term *and* issuing agency, so the
result is content-rich and PR-scoped. This poller mirrors ``ingest/rss.py``:
it returns :class:`RawItem`s that flow into the same classify → route pipeline.

Config lives under the ``federal_register:`` key of ``sources.yaml`` (loaded the
same way ``rss.py`` loads ``feeds:``), so intake configuration stays in one file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from centinelas.models import RawItem

log = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).parent / "sources.yaml"
_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
_TIMEOUT = 20.0
# Only the fields we map onto RawItem — keeps the response small.
_FIELDS = ("document_number", "title", "publication_date", "html_url", "abstract", "type")


def _load_config() -> dict:
    with open(_SOURCES_PATH) as f:
        return yaml.safe_load(f).get("federal_register", {}) or {}


def _get_json(params: list[tuple[str, str]]) -> dict:
    """Fetch the API response as a dict. Isolated as a seam for testing.

    ``httpx.Client`` honours ``HTTPS_PROXY``/``trust_env`` by default, so this
    works behind the environment's outbound proxy without extra configuration.
    """
    with httpx.Client(timeout=_TIMEOUT, trust_env=True) as client:
        resp = client.get(_API_URL, params=params)
        resp.raise_for_status()
        return resp.json()


def _parse_date(value: str) -> datetime:
    """Parse a Federal Register ``publication_date`` (YYYY-MM-DD) as UTC midnight."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _result_to_raw_item(result: dict, tier: str) -> RawItem | None:
    url = result.get("html_url", "")
    if not url:
        return None

    published_at = _parse_date(result.get("publication_date", ""))
    doc_type = result.get("type", "")
    title = (result.get("title", "") or "").strip()
    body = result.get("abstract", "") or ""

    return RawItem(
        item_id=RawItem.make_id(url, published_at),
        source_url=url,
        source_name=f"Federal Register — {doc_type}" if doc_type else "Federal Register",
        title=title,
        body_text=body,
        published_at=published_at,
        captured_at=datetime.now(timezone.utc),
        evidence_tier=tier,
    )


def poll_federal_register() -> list[RawItem]:
    """Poll the Federal Register API per ``sources.yaml`` config. Returns deduped RawItems.

    Disabled (returns ``[]``) when ``federal_register.enabled`` is false or the key
    is absent, so the source can be toggled off without a code change. Network or
    parse failures are logged and yield an empty list — never raise into the pipeline.
    """
    cfg = _load_config()
    if not cfg.get("enabled", False):
        return []

    tier = cfg.get("tier", "T1")
    params: list[tuple[str, str]] = [
        ("conditions[term]", cfg.get("term", "Puerto Rico")),
        ("order", cfg.get("order", "newest")),
        ("per_page", str(cfg.get("per_page", 50))),
    ]
    for agency in cfg.get("agencies", []):
        params.append(("conditions[agencies][]", agency))
    for field in _FIELDS:
        params.append(("fields[]", field))

    try:
        data = _get_json(params)
    except Exception as exc:
        log.warning("Federal Register poll failed: %s", exc)
        return []

    seen_ids: set[str] = set()
    items: list[RawItem] = []
    for result in data.get("results", []):
        item = _result_to_raw_item(result, tier)
        if item and item.item_id not in seen_ids:
            seen_ids.add(item.item_id)
            items.append(item)

    log.info("Polled Federal Register: %d documents", len(items))
    return items
