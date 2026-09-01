"""Core helpers for the bounded Just Security Puerto Rico monitor."""
from __future__ import annotations

import hashlib
import html as html_lib
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import httpx
from bs4 import BeautifulSoup

from centinelas.ingest import rss

SOURCE = rss._configured_source("CENT-SRC-RSS-JUST-SECURITY")
TAG_SOURCE = rss._configured_source("CENT-SRC-RSS-JUST-SECURITY-PUERTO-RICO-TAG")
SOURCE_ID = str(SOURCE["source_id"])
SOURCE_NAME = str(SOURCE["name"])
TIER = str(SOURCE["tier"])
MAIN_FEED = str(SOURCE["url"])
TAG_FEED = str(TAG_SOURCE["url"])
TAG_URL = "https://www.justsecurity.org/tag/puerto-rico/"
SEARCH_URL = "https://www.justsecurity.org/?s=puerto%20rico"
LIVING_URLS = (
    TAG_URL,
    SEARCH_URL,
    "https://www.justsecurity.org/124002/timeline-vessel-strikes-related-actions/",
    "https://www.justsecurity.org/107087/tracker-litigation-legal-challenges-trump-administration/",
)
ARTICLE_RE = re.compile(r"^https://www\.justsecurity\.org/\d+/[^?#]+/?$")
COUNT_RE = re.compile(r"(?P<n>[\d,]+)\s+Articles?", re.I)
RANGE_RE = re.compile(r"\b\d[\d,]*-\d[\d,]*\s+of\s+(?P<n>[\d,]+)\s+items\b", re.I)
MAX_BYTES = 5_000_000
_BLOCKED_HTTP = {401, 403, 429, 451}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_url(url: str, *, base_url: str | None = None) -> str:
    value = urljoin(base_url, url) if base_url else url
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"unsupported URL: {url!r}")
    path = parts.path or "/"
    if not path.endswith("/") and not path.lower().endswith(".pdf"):
        path += "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def normalized_text(*values: str) -> str:
    raw = html_lib.unescape(" ".join(values))
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip().casefold()


def is_pr_relevant(*values: str) -> bool:
    text = normalized_text(*values)
    return any(str(term).casefold() in text for term in SOURCE["match_any"])


def readable_html(body: bytes) -> str:
    soup = BeautifulSoup(body, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    return re.sub(r"\s+", " ", root.get_text(" ", strip=True)).strip()


def content_fingerprint(body: bytes) -> str:
    return sha256_bytes(readable_html(body).encode())


def fetch_url(client: httpx.Client, url: str) -> tuple[bytes | None, dict]:
    retrieved_at = now_utc()
    try:
        response = client.get(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        return None, {
            "url": url,
            "retrieved_at": retrieved_at,
            "state": "UNRESOLVED",
            "http_status": None,
            "byte_count": 0,
            "content_sha256": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    body = response.content
    if len(body) > MAX_BYTES:
        return None, {
            "url": url,
            "retrieved_at": retrieved_at,
            "state": "FAIL",
            "http_status": response.status_code,
            "byte_count": len(body),
            "content_sha256": None,
            "error": "payload_too_large",
        }
    if response.status_code == 200:
        state = "PASS"
    elif response.status_code in _BLOCKED_HTTP:
        state = "BLOCKED"
    else:
        state = "UNRESOLVED"
    return body, {
        "url": url,
        "retrieved_at": retrieved_at,
        "state": state,
        "http_status": response.status_code,
        "byte_count": len(body),
        "content_sha256": sha256_bytes(body),
        "content_type": response.headers.get("content-type"),
        "error": None if state == "PASS" else f"HTTP {response.status_code}",
    }


def listing_article_records(body: bytes, *, base_url: str | None = None) -> list[dict]:
    """Return unique listing records in source order without promoting title to identity."""
    records: list[dict] = []
    seen: set[str] = set()
    soup = BeautifulSoup(body, "html.parser")
    for anchor in soup.select("h1 a[href],h2 a[href],h3 a[href],article a[href]"):
        try:
            url = canonical_url(str(anchor.get("href", "")), base_url=base_url)
        except ValueError:
            continue
        if not ARTICLE_RE.fullmatch(url) or url in seen:
            continue
        seen.add(url)
        records.append(
            {
                "canonical_url": url,
                "title_raw": " ".join(anchor.stripped_strings).strip() or None,
            }
        )
    return records


def listing_article_urls(body: bytes, *, base_url: str | None = None) -> list[str]:
    return [record["canonical_url"] for record in listing_article_records(body, base_url=base_url)]


def listing_declared_count(body: bytes) -> int | None:
    text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
    for pattern in (COUNT_RE, RANGE_RE):
        match = pattern.search(text)
        if match:
            return int(match.group("n").replace(",", ""))
    return None


def listing_next_page(body: bytes, current_url: str) -> str | None:
    soup = BeautifulSoup(body, "html.parser")
    selectors = "a[rel='next'][href],a.next[href],.pagination a[href],.nav-links a[href]"
    for anchor in soup.select(selectors):
        label = " ".join(anchor.stripped_strings).casefold()
        rel = " ".join(anchor.get("rel") or []).casefold()
        if "next" in rel or label in {"next", "next »", "older", "older posts"}:
            return urljoin(current_url, str(anchor["href"]))
    return None


def snapshot_listing(
    client: httpx.Client,
    manifestation: str,
    url: str,
    *,
    max_pages: int = 250,
) -> dict:
    current = url
    visited: set[str] = set()
    records: list[dict] = []
    seen_urls: set[str] = set()
    receipts: list[dict] = []
    declared: int | None = None
    residue: str | None = None
    while current and current not in visited and len(visited) < max_pages:
        visited.add(current)
        body, receipt = fetch_url(client, current)
        receipts.append(receipt)
        if body is None or receipt.get("http_status") != 200:
            residue = receipt.get("error") or receipt["state"]
            break
        if declared is None:
            declared = listing_declared_count(body)
        for record in listing_article_records(body, base_url=current):
            item_url = record["canonical_url"]
            if item_url in seen_urls:
                continue
            seen_urls.add(item_url)
            records.append(
                {
                    **record,
                    "result_position": len(records) + 1,
                    "listing_page": current,
                }
            )
        current = listing_next_page(body, current)
    urls = [record["canonical_url"] for record in records]
    if current in visited:
        residue = f"pagination_loop:{current}"
    elif current and len(visited) >= max_pages:
        residue = f"max_pages:{max_pages}"
    first_state = receipts[0]["state"] if receipts else "UNRESOLVED"
    if first_state == "BLOCKED":
        certification = "BLOCKED"
    elif first_state != "PASS":
        certification = "PROVISIONAL"
    elif residue:
        certification = "PROVISIONAL"
    elif declared is not None and declared != len(urls):
        certification = "PROVISIONAL"
        residue = f"declared={declared};parsed={len(urls)}"
    elif declared is None and not urls:
        certification = "PROVISIONAL"
        residue = "zero_results_without_declared_denominator"
    else:
        certification = "PASS"
    return {
        "manifestation": manifestation,
        "url": url,
        "certification": certification,
        "declared_count": declared,
        "parsed_count": len(urls),
        "result_records": records,
        "result_urls": urls,
        "pages_checked": len(visited),
        "receipts": receipts,
        "residue": residue,
    }


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = node.get("content") or node.get("datetime")
        if value:
            return str(value).strip() or None
        text = " ".join(node.stripped_strings).strip()
        if text:
            return text
    return None


def extract_article_metadata(body: bytes) -> dict:
    """Extract raw descriptive fields without using them as identity proof."""
    soup = BeautifulSoup(body, "html.parser")
    title = _meta_content(
        soup,
        "meta[property='og:title']",
        "meta[name='twitter:title']",
        "h1",
        "title",
    )
    author = _meta_content(
        soup,
        "meta[name='author']",
        "meta[property='article:author']",
        "[rel='author']",
        "[itemprop='author']",
    )
    published = _meta_content(
        soup,
        "meta[property='article:published_time']",
        "meta[name='article:published_time']",
        "time[datetime]",
    )
    modified = _meta_content(
        soup,
        "meta[property='article:modified_time']",
        "meta[name='article:modified_time']",
    )
    return {
        "title_raw": title,
        "author_raw": author,
        "published_at_raw": published,
        "modified_at_raw": modified,
    }


def acquire_article_receipts(client: httpx.Client, urls: list[str]) -> list[dict]:
    """Fetch every unique URL once, retaining source order and descriptive metadata."""
    receipts: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        body, receipt = fetch_url(client, url)
        receipt["result_position"] = len(receipts) + 1
        if body is not None and receipt.get("http_status") == 200:
            receipt["normalized_content_sha256"] = content_fingerprint(body)
            receipt.update(extract_article_metadata(body))
        else:
            receipt["normalized_content_sha256"] = None
            receipt.update(
                {
                    "title_raw": None,
                    "author_raw": None,
                    "published_at_raw": None,
                    "modified_at_raw": None,
                }
            )
        receipts.append(receipt)
    return receipts


def set_differences(previous: list[str], current: list[str]) -> dict[str, list[str]]:
    a, b = set(previous), set(current)
    return {
        "INTERSECTION": sorted(a & b),
        "A_ONLY": sorted(a - b),
        "B_ONLY": sorted(b - a),
        "UNION": sorted(a | b),
        "SYMMETRIC_DIFFERENCE": sorted(a ^ b),
    }


def _feed_text(entry: dict) -> str:
    content = " ".join(
        str(block.get("value", ""))
        for block in entry.get("content") or []
        if isinstance(block, dict)
    )
    tags = " ".join(
        str(tag.get("term", ""))
        for tag in entry.get("tags") or []
        if isinstance(tag, dict)
    )
    return " ".join(
        (str(entry.get("title", "")), str(entry.get("summary", "")), content, tags)
    )


def poll_relevant_feeds(
    client: httpx.Client,
    *,
    fetch_detail: bool = True,
) -> tuple[list[dict], dict]:
    retained: dict[str, dict] = {}
    counts = {
        "seen": 0,
        "relevant": 0,
        "excluded": 0,
        "duplicate": 0,
        "unresolved": 0,
        "detail_failures": 0,
    }
    receipts: list[dict] = []
    source_states: dict[str, str] = {}
    sources = (
        ("MAIN_FEED", MAIN_FEED, False),
        ("PR_TAG_FEED", TAG_FEED, True),
    )
    for manifestation, feed_url, tag_authoritative in sources:
        body, receipt = fetch_url(client, feed_url)
        receipts.append(receipt)
        source_states[manifestation] = receipt["state"]
        if body is None or receipt.get("http_status") != 200:
            continue
        parsed = feedparser.parse(body)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            source_states[manifestation] = "FAIL"
            continue
        for raw_entry in parsed.entries:
            entry = dict(raw_entry)
            counts["seen"] += 1
            try:
                url = canonical_url(str(entry.get("link", "")))
            except ValueError:
                counts["unresolved"] += 1
                continue
            if url in retained:
                current = retained[url]["manifestations"]
                retained[url]["manifestations"] = sorted(set(current + [manifestation]))
                counts["duplicate"] += 1
                continue
            matched = is_pr_relevant(_feed_text(entry))
            detail_hash = None
            detail_text = ""
            detail_failed = False
            if fetch_detail and (tag_authoritative or not matched):
                page, page_receipt = fetch_url(client, url)
                receipts.append(page_receipt)
                if page is not None and page_receipt.get("http_status") == 200:
                    detail_hash = page_receipt["content_sha256"]
                    detail_text = readable_html(page)
                    if not tag_authoritative and not matched:
                        matched = is_pr_relevant(detail_text)
                else:
                    detail_failed = True
                    counts["detail_failures"] += 1
            if not tag_authoritative and not matched:
                if fetch_detail and detail_failed:
                    counts["unresolved"] += 1
                else:
                    counts["excluded"] += 1
                continue
            if fetch_detail and detail_hash is None and not detail_failed:
                page, page_receipt = fetch_url(client, url)
                receipts.append(page_receipt)
                if page is not None and page_receipt.get("http_status") == 200:
                    detail_hash = page_receipt["content_sha256"]
                    detail_text = readable_html(page)
                else:
                    counts["detail_failures"] += 1
            retained[url] = {
                "canonical_url": url,
                "title": str(entry.get("title", "")),
                "body_text": detail_text or normalized_text(_feed_text(entry)),
                "evidence_tier": TIER,
                "manifestations": [manifestation],
                "content_sha256": detail_hash,
                "linked_document_tier_inheritance": False,
            }
            counts["relevant"] += 1
    partition = (
        counts["relevant"]
        + counts["excluded"]
        + counts["duplicate"]
        + counts["unresolved"]
    )
    assert counts["seen"] == partition
    values = list(source_states.values())
    if values and all(state == "PASS" for state in values):
        certification = "PASS"
    elif values and all(state == "BLOCKED" for state in values):
        certification = "BLOCKED"
    else:
        certification = "PROVISIONAL"
    return list(retained.values()), {
        "counts": counts,
        "receipts": receipts,
        "source_states": source_states,
        "certification": certification,
    }


def reconcile_listing(state: dict, snapshot: dict, run_id: str) -> list[dict]:
    previous = state.setdefault("listings", {}).get(snapshot["manifestation"], {})
    differences = set_differences(previous.get("result_urls", []), snapshot["result_urls"])
    events = []
    if (
        snapshot["certification"] in {"PASS", "PROVISIONAL"}
        and differences["SYMMETRIC_DIFFERENCE"]
    ):
        events.append(
            {
                "event_type": "LISTING_COVERAGE_CHANGE",
                "run_id": run_id,
                "manifestation": snapshot["manifestation"],
                "differences": differences,
                "a_only_semantics": "SEARCH_OR_TAG_ABSENCE_ONLY_NOT_DOCUMENT_DELETION",
            }
        )
    state["listings"][snapshot["manifestation"]] = snapshot
    return events


def linked_document_policy(url: str) -> dict:
    return {
        "url": url,
        "parent_source_tier": TIER,
        "inherits_parent_tier": False,
        "classification": "INDEPENDENT_EVIDENCE_ADJUDICATION_REQUIRED",
        "possible_outcomes": ["T1", "T2", "T3", "T4", "UNRESOLVED"],
    }
