"""Additional fail-closed regression gates for Just Security monitoring."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import just_security_monitor as monitor  # noqa: E402
from just_security_monitor_core import (  # noqa: E402
    MAIN_FEED,
    TAG_FEED,
    acquire_article_receipts,
    fetch_url,
    poll_relevant_feeds,
    snapshot_listing,
)

from centinelas.ingest import rss  # noqa: E402


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tag_feed_is_registered_as_independent_t4_manifestation():
    sources = rss._load_sources()
    main = [s for s in sources if s.get("source_id") == "CENT-SRC-RSS-JUST-SECURITY"]
    tag = [
        s
        for s in sources
        if s.get("source_id") == "CENT-SRC-RSS-JUST-SECURITY-PUERTO-RICO-TAG"
    ]
    assert len(main) == 1
    assert len(tag) == 1
    assert main[0]["tier"] == tag[0]["tier"] == "T4"
    assert main[0]["url"] != tag[0]["url"]


def test_failed_detail_fetch_is_unresolved_not_false_exclusion():
    article = "https://www.justsecurity.org/201/detail-unavailable/"
    main_xml = f"""<?xml version="1.0"?><rss><channel>
      <item><title>Regional law</title><link>{article}</link><description>No direct PR term</description></item>
    </channel></rss>""".encode()
    tag_xml = b"<?xml version='1.0'?><rss><channel></channel></rss>"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == MAIN_FEED:
            return httpx.Response(200, request=request, content=main_xml)
        if url == TAG_FEED:
            return httpx.Response(200, request=request, content=tag_xml)
        if url == article:
            return httpx.Response(503, request=request, text="unavailable")
        raise AssertionError(url)

    with _client(handler) as client:
        items, run = poll_relevant_feeds(client)
    assert items == []
    assert run["counts"]["seen"] == 1
    assert run["counts"]["unresolved"] == 1
    assert run["counts"]["excluded"] == 0
    assert run["counts"]["detail_failures"] == 1
    assert any(
        receipt["state"] == "UNRESOLVED" and receipt["http_status"] == 503
        for receipt in run["receipts"]
    )


def test_transport_failure_is_unresolved_not_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    with _client(handler) as client:
        body, receipt = fetch_url(client, "https://www.justsecurity.org/feed/")
    assert body is None
    assert receipt["state"] == "UNRESOLVED"
    assert receipt["http_status"] is None


def test_503_listing_is_provisional_not_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request, text="temporary outage")

    with _client(handler) as client:
        snapshot = snapshot_listing(client, "OUTAGE", "https://www.justsecurity.org/tag/test/")
    assert snapshot["certification"] == "PROVISIONAL"
    assert snapshot["receipts"][0]["state"] == "UNRESOLVED"


def test_403_listing_remains_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request, text="access denied")

    with _client(handler) as client:
        snapshot = snapshot_listing(client, "DENIED", "https://www.justsecurity.org/tag/test/")
    assert snapshot["certification"] == "BLOCKED"
    assert snapshot["receipts"][0]["state"] == "BLOCKED"


def test_partial_state_is_schema_upgraded_without_discarding_existing_data(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"items": {"existing": {"value": 1}}}), encoding="utf-8")
    state = monitor._load_state(path)
    assert state["items"] == {"existing": {"value": 1}}
    assert state["listings"] == {}
    assert state["living"] == {}
    assert state["schema_version"] == "just_security_monitor_state.v0.1"


def test_listing_article_acquisition_hashes_metadata_and_preserves_order():
    urls = [
        "https://www.justsecurity.org/301/a/",
        "https://www.justsecurity.org/302/b/",
        "https://www.justsecurity.org/301/a/",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        slug = request.url.path.strip("/").split("/")[-1]
        return httpx.Response(
            200,
            request=request,
            text=(
                "<html><head>"
                f"<meta property='og:title' content='Title {slug}'>"
                f"<meta name='author' content='Author {slug}'>"
                "<meta property='article:published_time' content='2026-09-01T12:00:00Z'>"
                "<meta property='article:modified_time' content='2026-09-01T13:00:00Z'>"
                "</head>"
                f"<body><article>{request.url.path}</article></body></html>"
            ),
        )

    with _client(handler) as client:
        receipts = acquire_article_receipts(client, urls)
    assert len(receipts) == 2
    assert [receipt["url"] for receipt in receipts] == urls[:2]
    assert [receipt["result_position"] for receipt in receipts] == [1, 2]
    assert all(receipt["state"] == "PASS" for receipt in receipts)
    assert all(len(receipt["content_sha256"]) == 64 for receipt in receipts)
    assert all(len(receipt["normalized_content_sha256"]) == 64 for receipt in receipts)
    assert receipts[0]["title_raw"] == "Title a"
    assert receipts[0]["author_raw"] == "Author a"
    assert receipts[0]["published_at_raw"] == "2026-09-01T12:00:00Z"
    assert receipts[0]["modified_at_raw"] == "2026-09-01T13:00:00Z"


def test_relative_listing_article_links_resolve_and_preserve_position():
    body = b"""
    <html><body><div>1 Article</div>
      <article><h2><a href="/401/relative-article/">Relative Title</a></h2></article>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, content=body)

    with _client(handler) as client:
        snapshot = snapshot_listing(client, "RELATIVE", "https://www.justsecurity.org/tag/test/")
    assert snapshot["certification"] == "PASS"
    assert snapshot["result_urls"] == ["https://www.justsecurity.org/401/relative-article/"]
    assert snapshot["result_records"] == [
        {
            "canonical_url": "https://www.justsecurity.org/401/relative-article/",
            "title_raw": "Relative Title",
            "result_position": 1,
            "listing_page": "https://www.justsecurity.org/tag/test/",
        }
    ]


def test_zero_results_without_declared_denominator_fails_closed():
    body = b"<html><body><main>Search results</main></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, content=body)

    with _client(handler) as client:
        snapshot = snapshot_listing(client, "EMPTY", "https://www.justsecurity.org/?s=opaque")
    assert snapshot["certification"] == "PROVISIONAL"
    assert snapshot["parsed_count"] == 0
    assert snapshot["declared_count"] is None
    assert snapshot["residue"] == "zero_results_without_declared_denominator"
