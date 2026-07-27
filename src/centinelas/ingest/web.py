"""HTML scraper for non-RSS sources using httpx + BeautifulSoup.

Two layers live here:

* :func:`scrape_url` — fetch one page, return it as a single :class:`RawItem`.
* :func:`poll_scrape_sources` — the *listing* layer: read the ``scrape:`` block of
  ``sources.yaml`` and emit **one RawItem per list entry** for sources that
  publish no feed (OGPe, Junta de Planificación, EPA Region 2 NPDES).

The listing layer exists because Puerto Rico's central permitting bodies publish
their hearings, environmental determinations and permit tables as ordinary
server-rendered HTML — the content is in the markup, so httpx + BeautifulSoup is
enough and no browser is needed.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
import yaml
from bs4 import BeautifulSoup

from centinelas.models import RawItem

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "centinelas-monitor/1.0 (intelligence intake; contact: research@centinelas)",
    "Accept": "text/html,application/xhtml+xml",
}
_TIMEOUT = 15.0

_SOURCES_PATH = Path(__file__).parent / "sources.yaml"

# Webflow renders conditionally-hidden and empty CMS bindings into the DOM
# (e.g. a "[DEROGADO]" badge, or a placeholder "This is some text inside of a
# div block."). They are invisible to a reader, so they must not become body text.
_HIDDEN_CLASSES = ("w-condition-invisible", "w-dyn-bind-empty")

# Class-name fragments that identify the semantic parts of a CMS list item.
# Each source names its divs differently (documento-date, noticia-date,
# fecha-pot; documento-title, noticia-title, vista-publica-title, item-title),
# so match on substrings rather than hard-coding one site's selectors.
_DATE_CLASS_RE = re.compile(r"date|fecha", re.I)
_TITLE_CLASS_RE = re.compile(r"title|titulo", re.I)
# Project/applicant and municipality lines — real signal for the classifier and
# for municipality enrichment, so they are folded into the body.
_CONTEXT_CLASS_RE = re.compile(r"subtitle|programa", re.I)

# Date formats seen across these sources: "July 24, 2026", "12/13/2023",
# "July 31, 2026 9:30 AM".
_DATE_FORMATS = ("%B %d, %Y %I:%M %p", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d")

# Stand-in date used *only* when hashing the identity of an entry whose own date
# could not be parsed. See _entry_item_id.
_UNDATED = datetime(1970, 1, 1, tzinfo=timezone.utc)

_MAX_BODY_CHARS = 2000

# Unicode Private Use Area — where icon fonts put their glyphs.
_PUA_START, _PUA_END = "", ""


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
        # EvidenceTier is a typing.Literal alias — not callable; pydantic
        # validates the value against the Literal on the model. Calling it
        # raises "TypeError: Cannot instantiate typing.Literal" at runtime.
        evidence_tier=tier,
    )


# ── Listing scrape (one RawItem per list entry) ───────────────────────────────


def _load_scrape_config() -> dict:
    """Read the ``scrape:`` block of sources.yaml (mirrors ``rss._load_sources``)."""
    with open(_SOURCES_PATH) as f:
        return yaml.safe_load(f).get("scrape", {}) or {}


def _fetch_html(url: str) -> str | None:
    """GET a page and return its HTML, or None on failure.

    Single place the listing layer touches the network — the seam tests
    monkeypatch, so no test needs a live site.
    """
    try:
        with httpx.Client(
            headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True, trust_env=True
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        log.warning("HTTP fetch failed for %s: %s", url, exc)
        return None


def _slug(text: str) -> str:
    """ASCII slug used to keep link-less entries distinct in their synthetic URL."""
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")[:80]


def _is_hidden(node) -> bool:
    classes = node.get("class", []) or []
    return any(hidden in classes for hidden in _HIDDEN_CLASSES)


def _hidden_ancestor(string_node) -> bool:
    """True when a text node sits inside a hidden/placeholder Webflow binding."""
    for parent in string_node.parents:
        if getattr(parent, "get", None) and _is_hidden(parent):
            return True
    return False


def _visible_text(node) -> str:
    """Text of a node with Webflow's hidden/placeholder bindings removed."""
    # find_all(string=True) yields NavigableStrings (which keep .parents), unlike
    # stripped_strings, which yields plain str.
    parts = [
        chunk.strip()
        for chunk in node.find_all(string=True)
        if chunk.strip() and not _hidden_ancestor(chunk)
    ]
    # Icon-font glyphs (FontAwesome et al.) sit in the Unicode Private Use Area
    # and carry no meaning — drop chunks made up entirely of them.
    return " ".join(p for p in parts if not all(_PUA_START <= c <= _PUA_END for c in p))


def _parse_date(text: str) -> datetime | None:
    cleaned = " ".join((text or "").split())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _feed_entry_date(entry) -> datetime | None:
    """UTC datetime from a feedparser entry, or None when it carries no date.

    Mirrors ``rss._parse_date`` but returns None instead of falling back to
    now(), so the caller can tell "undated" from "published today" — the
    distinction the item identity depends on. Using feedparser's already-parsed
    struct_time also handles RFC-822 (``Wed, 01 Oct 2025 14:48:00 GMT``), which
    the ``_DATE_FORMATS`` patterns do not cover.
    """
    for field in ("published_parsed", "updated_parsed"):
        value = entry.get(field)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


def _entry_item_id(url: str, title: str, published_at: datetime | None) -> str:
    """Stable identity for a listing entry.

    ``make_id`` hashes url + published_at, so an entry whose date could not be
    parsed must NOT fall back to now() here: that would mint a fresh item_id on
    every poll, and because the pipeline names files by item_id, the same
    unchanged entry would pile up as new queue/classified/intake records instead
    of overwriting its own. Undated entries are therefore identified by
    url + title against a fixed sentinel date.
    """
    if published_at is not None:
        return RawItem.make_id(url, published_at)
    return RawItem.make_id(f"{url}|{title}", _UNDATED)


def _first_by_class(item, pattern: re.Pattern[str], exclude=()) -> object | None:
    for node in item.find_all(True):
        if node in exclude or _is_hidden(node):
            continue
        classes = " ".join(node.get("class", []) or [])
        if classes and pattern.search(classes) and _visible_text(node):
            return node
    return None


def _parse_webflow_items(soup: BeautifulSoup, cfg: dict, base_url: str) -> list[dict]:
    """Extract entries from a Webflow CMS collection list.

    When ``tabs`` is configured, only the named ``.w-tab-pane`` panes are read —
    the mechanism that keeps OGPe's user manuals, tutorial videos and blank forms
    out of the signal pipeline while still ingesting its hearings and
    environmental determinations.
    """
    selector = cfg.get("item_selector") or ".w-dyn-item"
    tabs = cfg.get("tabs")

    # A "section" labels what kind of record the entry is. It matters because the
    # semantics often live in the tab name rather than the entry: an OGPe hearing
    # is titled with a bare case number ("2025-663228-PU-438754") and bodied with
    # the project and municipality — the words "Vistas Públicas" appear only on
    # the pane. Folding the section in lets the item classify itself instead of
    # falling through to the LLM as unlabelled text. `section` in config does the
    # same for untabbed pages whose whole listing is one record type.
    if tabs:
        wanted = {t.strip() for t in tabs}
        containers = [
            (pane, (pane.get("data-w-tab") or "").strip())
            for pane in soup.select(".w-tab-pane")
            if (pane.get("data-w-tab") or "").strip() in wanted
        ]
    else:
        containers = [(soup, cfg.get("section", ""))]

    entries: list[dict] = []
    for container, section in containers:
        for item in container.select(selector):
            date_node = _first_by_class(item, _DATE_CLASS_RE)
            # The title lookup must exclude the date node: on JP's vistas page the
            # date div also carries the .vista-publica-title class, so a naive
            # title selector returns the date string instead of the title.
            title_node = _first_by_class(item, _TITLE_CLASS_RE, exclude=(date_node,))

            title = _visible_text(title_node) if title_node else ""
            links = [
                urljoin(base_url, a["href"])
                for a in item.find_all("a", href=True)
                if not _is_hidden(a)
            ]
            if not title:
                anchor = item.find("a", href=True)
                title = _visible_text(anchor) if anchor else ""
            if not title:
                title = _visible_text(item)[:120]
            if not title:
                continue

            context = [
                _visible_text(node)
                for node in item.find_all(True)
                if node is not title_node
                and node is not date_node
                and not _is_hidden(node)
                and (node.get("class") and _CONTEXT_CLASS_RE.search(" ".join(node["class"])))
            ]
            body = _visible_text(item)
            if context:
                body = f"{' — '.join(dict.fromkeys(c for c in context if c))}. {body}"
            if section:
                body = f"{section}. {body}"

            entries.append({
                "title": title,
                "body": body[:_MAX_BODY_CHARS],
                "published_at": _parse_date(_visible_text(date_node)) if date_node else None,
                "url": links[0] if links else "",
            })
    return entries


def _parse_html_table(soup: BeautifulSoup, cfg: dict, base_url: str) -> list[dict]:
    """Extract one entry per data row of an HTML table (EPA's NPDES listing).

    The header row names the columns, so the remaining cells can be serialized
    into the body as ``Column: value`` pairs — this is what carries the
    municipality (``Location``) and the comment-period deadline downstream.
    """
    table = soup.select_one(cfg.get("item_selector") or "table")
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    columns = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
    title_columns = cfg.get("title_columns") or columns[:1]
    date_column = cfg.get("date_column")

    entries: list[dict] = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells:
            continue
        values = dict(zip(columns, (c.get_text(" ", strip=True) for c in cells)))
        if not any(values.values()):
            continue

        title = " — ".join(v for c in title_columns if (v := values.get(c, "").strip()))
        if not title:
            continue

        body = "; ".join(f"{col}: {val}" for col, val in values.items() if val)
        link = row.find("a", href=True)

        entries.append({
            "title": title,
            "body": body[:_MAX_BODY_CHARS],
            "published_at": _parse_date(values.get(date_column, "")) if date_column else None,
            "url": urljoin(base_url, link["href"]) if link else "",
        })
    return entries


def _parse_rss_detail(cfg: dict, base_url: str) -> list[dict]:
    """Walk an RSS index whose items are stubs, fetching each linked notice page.

    Some agencies (USACE Jacksonville) publish a feed whose entries are only
    opaque permit IDs — the body and the location live on the linked page, so the
    text needed to filter by jurisdiction and classify requires a second fetch
    per entry. ``match_any`` keeps only pages mentioning one of its terms.
    """
    import feedparser

    index = _fetch_html(base_url)
    if not index:
        return []

    match_any = [m.lower() for m in cfg.get("match_any") or []]
    entries: list[dict] = []

    for entry in feedparser.parse(index).entries:
        link = entry.get("link", "")
        if not link:
            continue
        page = _fetch_html(link)
        if not page:
            continue

        soup = BeautifulSoup(page, "html.parser")
        body = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))[:_MAX_BODY_CHARS]
        if match_any and not any(term in body.lower() for term in match_any):
            continue

        entries.append({
            "title": entry.get("title", "").strip(),
            "body": body,
            "published_at": _feed_entry_date(entry),
            "url": link,
        })
    return entries


_PARSERS = {
    "webflow_cms": _parse_webflow_items,
    "html_table": _parse_html_table,
}


def scrape_listing(source: dict) -> list[RawItem]:
    """Scrape one configured listing source into RawItems (one per entry)."""
    url = source.get("url", "")
    name = source.get("name", url)
    tier = source.get("tier", "T2")
    parser = source.get("parser", "webflow_cms")

    if parser == "rss_detail":
        entries = _parse_rss_detail(source, url)
    else:
        parse = _PARSERS.get(parser)
        if parse is None:
            log.warning("Unknown parser %r for source %s", parser, name)
            return []
        html = _fetch_html(url)
        if not html:
            return []
        entries = parse(BeautifulSoup(html, "html.parser"), source, url)

    items: list[RawItem] = []
    for entry in entries:
        # Keep the parsed date separate from the stored one: the record still
        # falls back to now() (published_at is required, and rss.py /
        # federal_register.py do the same), but only a *parsed* date may take
        # part in the identity — see _entry_item_id.
        parsed_at = entry.get("published_at")
        published_at = parsed_at or datetime.now(timezone.utc)
        # Entries without their own link (a hearing listed as plain text) would
        # otherwise all share the listing URL and collide in make_id, so give
        # them a stable per-entry fragment.
        item_url = entry.get("url") or f"{url}#{_slug(entry['title'])}"
        items.append(
            RawItem(
                item_id=_entry_item_id(item_url, entry["title"], parsed_at),
                source_url=item_url,
                source_name=name,
                title=entry["title"],
                body_text=entry.get("body", ""),
                published_at=published_at,
                captured_at=datetime.now(timezone.utc),
                evidence_tier=tier,
            )
        )

    log.info("Scraped %s: %d entries", name, len(items))
    return items


def poll_scrape_sources() -> list[RawItem]:
    """Scrape every enabled listing source in sources.yaml. Returns deduped RawItems.

    Mirrors ``rss.poll_all``: a failing source is logged and skipped rather than
    aborting intake, and the whole layer can be switched off via
    ``scrape.enabled``.
    """
    cfg = _load_scrape_config()
    if not cfg.get("enabled", False):
        return []

    seen_ids: set[str] = set()
    items: list[RawItem] = []

    for source in cfg.get("sources", []):
        if not source.get("enabled", True):
            log.info("Skipping disabled scrape source: %s", source.get("name", source.get("url")))
            continue
        try:
            for item in scrape_listing(source):
                if item.item_id not in seen_ids:
                    seen_ids.add(item.item_id)
                    items.append(item)
        except Exception as exc:
            log.warning("Scrape failed for %s: %s", source.get("name", source.get("url")), exc)

    return items
