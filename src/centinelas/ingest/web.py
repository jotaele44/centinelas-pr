"""HTML scraper for non-RSS sources using httpx + BeautifulSoup."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from centinelas.models import EvidenceTier, RawItem

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "centinelas-monitor/1.0 (intelligence intake; contact: research@centinelas)",
    "Accept": "text/html,application/xhtml+xml",
}
_TIMEOUT = 15.0


def scrape_url(
    url: str,
    source_name: str = "",
    tier: str = "T2",
    published_at: datetime | None = None,
) -> RawItem | None:
    """Scrape a single URL and return a RawItem, or None on failure."""
    try:
        with httpx.Client(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        log.warning("HTTP fetch failed for %s: %s", url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    tag = soup.find("meta", property="og:title") or soup.find("title")
    if tag:
        title = tag.get("content") or tag.get_text()
    title = title.strip()

    # Prefer article body; fall back to <p> tags
    body_parts: list[str] = []
    article = soup.find("article") or soup.find(class_=lambda c: c and "article" in c.lower())
    if article:
        body_parts = [p.get_text(" ", strip=True) for p in article.find_all("p")]
    else:
        body_parts = [p.get_text(" ", strip=True) for p in soup.find_all("p")]

    body_text = " ".join(body_parts[:30])  # cap at ~30 paragraphs

    pub = published_at or datetime.now(timezone.utc)
    item_id = RawItem.make_id(url, pub)

    return RawItem(
        item_id=item_id,
        source_url=url,
        source_name=source_name or url,
        title=title,
        body_text=body_text,
        published_at=pub,
        captured_at=datetime.now(timezone.utc),
        evidence_tier=EvidenceTier(tier),
    )
