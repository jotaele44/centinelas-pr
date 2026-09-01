"""Offline regression gates for the Just Security Puerto Rico integration."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from centinelas.ingest import rss  # noqa: E402
from just_security_monitor_core import (  # noqa: E402
    MAIN_FEED,
    SEARCH_URL,
    TAG_FEED,
    TAG_URL,
    content_fingerprint,
    is_pr_relevant,
    linked_document_policy,
    poll_relevant_feeds,
    reconcile_listing,
    set_differences,
    snapshot_listing,
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_rss_registration_and_filtering(monkeypatch):
    registered = [s for s in rss._load_sources() if s.get("name") == "Just Security"]
    assert len(registered) == 1
    assert registered[0]["tier"] == "T4"
    source = registered[0]
    entries = [
        {
            "link": "https://www.justsecurity.org/1/pr-item/",
            "title": "Puerto Rico policy update",
            "summary": "Relevant item",
            "published_parsed": (2026, 9, 1, 12, 0, 0, 0, 0, 0),
        },
        {
            "link": "https://www.justsecurity.org/2/other-item/",
            "title": "International law elsewhere",
            "summary": "No territorial connection",
            "published_parsed": (2026, 9, 1, 13, 0, 0, 0, 0, 0),
        },
    ]
    monkeypatch.setattr(rss, "_load_sources", lambda: [source])
    monkeypatch.setattr(rss.feedparser, "parse", lambda _url: SimpleNamespace(entries=entries))
    items = rss.poll_all()
    assert len(items) == 1
    assert items[0].source_name == "Just Security"
    assert items[0].evidence_tier == "T4"
    assert "Puerto Rico" in items[0].title


def test_high_precision_relevance_positive_and_negative():
    assert is_pr_relevant("A Puerto Rican constitutional dispute")
    assert is_pr_relevant("Proceedings concerning Vieques")
    assert is_pr_relevant("The Financial Oversight and Management Board filed a motion")
    assert not is_pr_relevant("A Caribbean security operation")
    assert not is_pr_relevant("A dispute concerning an unnamed U.S. territory")


def test_literal_search_403_fails_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SEARCH_URL
        return httpx.Response(403, request=request, text="Access denied")

    with _client(handler) as client:
        snap = snapshot_listing(client, "PUERTO_RICO_LITERAL_SEARCH", SEARCH_URL)
    assert snap["certification"] == "BLOCKED"
    assert snap["declared_count"] is None
    assert snap["parsed_count"] == 0
    assert snap["receipts"][0]["http_status"] == 403


def test_declared_count_mismatch_is_provisional():
    html = b"""
    <html><body><div>50 Articles</div>
      <article><h2><a href="https://www.justsecurity.org/1/a/">A</a></h2></article>
      <article><h2><a href="https://www.justsecurity.org/2/b/">B</a></h2></article>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, content=html)

    with _client(handler) as client:
        snap = snapshot_listing(client, "TEST", TAG_URL)
    assert snap["declared_count"] == 50
    assert snap["parsed_count"] == 2
    assert snap["certification"] == "PROVISIONAL"
    assert snap["residue"] == "declared=50;parsed=2"


def test_pagination_closes_declared_denominator():
    page1 = b"""
    <html><body><div>3 Articles</div>
      <article><h2><a href="https://www.justsecurity.org/1/a/">A</a></h2></article>
      <article><h2><a href="https://www.justsecurity.org/2/b/">B</a></h2></article>
      <a rel="next" href="https://www.justsecurity.org/tag/puerto-rico/page/2/">Next</a>
    </body></html>
    """
    page2 = b"""
    <html><body>
      <article><h2><a href="https://www.justsecurity.org/3/c/">C</a></h2></article>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = page2 if "/page/2/" in str(request.url) else page1
        return httpx.Response(200, request=request, content=body)

    with _client(handler) as client:
        snap = snapshot_listing(client, "TEST", TAG_URL)
    assert snap["declared_count"] == 3
    assert snap["parsed_count"] == 3
    assert snap["pages_checked"] == 2
    assert snap["certification"] == "PASS"
    assert snap["residue"] is None


def test_set_difference_contract_is_complete():
    diff = set_differences(["a", "b", "d"], ["b", "c", "d"])
    assert diff == {
        "INTERSECTION": ["b", "d"],
        "A_ONLY": ["a"],
        "B_ONLY": ["c"],
        "UNION": ["a", "b", "c", "d"],
        "SYMMETRIC_DIFFERENCE": ["a", "c"],
    }


def test_search_disappearance_is_not_document_deletion():
    state = {
        "listings": {
            "SEARCH": {
                "result_urls": ["https://www.justsecurity.org/1/a/", "https://www.justsecurity.org/2/b/"]
            }
        }
    }
    snapshot = {
        "manifestation": "SEARCH",
        "certification": "PASS",
        "result_urls": ["https://www.justsecurity.org/2/b/"],
    }
    events = reconcile_listing(state, snapshot, "RUN-1")
    assert len(events) == 1
    event = events[0]
    assert event["differences"]["A_ONLY"] == ["https://www.justsecurity.org/1/a/"]
    assert event["a_only_semantics"] == "SEARCH_OR_TAG_ABSENCE_ONLY_NOT_DOCUMENT_DELETION"
    assert "deletion" not in event["event_type"].lower()


def test_feed_detail_recall_cross_manifest_dedup_and_t4():
    first = "https://www.justsecurity.org/100/pr-direct/"
    second = "https://www.justsecurity.org/101/detail-only/"
    main_xml = f"""<?xml version="1.0"?><rss><channel>
      <item><title>Puerto Rico direct</title><link>{first}</link><description>Direct match</description></item>
      <item><title>Regional policy</title><link>{second}</link><description>No direct term here</description></item>
    </channel></rss>""".encode()
    tag_xml = f"""<?xml version="1.0"?><rss><channel>
      <item><title>Puerto Rico direct</title><link>{first}</link><description>Tagged duplicate</description></item>
    </channel></rss>""".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == MAIN_FEED:
            return httpx.Response(200, request=request, content=main_xml)
        if url == TAG_FEED:
            return httpx.Response(200, request=request, content=tag_xml)
        if url == first:
            return httpx.Response(200, request=request, text="<article>Puerto Rico direct article</article>")
        if url == second:
            return httpx.Response(200, request=request, text="<article>Detailed reporting concerning Vieques</article>")
        raise AssertionError(url)

    with _client(handler) as client:
        items, run = poll_relevant_feeds(client)
    assert {item["canonical_url"] for item in items} == {first, second}
    assert all(item["evidence_tier"] == "T4" for item in items)
    assert all(item["linked_document_tier_inheritance"] is False for item in items)
    assert run["counts"]["seen"] == 3
    assert run["counts"]["relevant"] == 2
    assert run["counts"]["duplicate"] == 1
    assert run["counts"]["excluded"] == 0
    assert run["counts"]["seen"] == (
        run["counts"]["relevant"] + run["counts"]["duplicate"] + run["counts"]["excluded"]
    )


def test_linked_document_never_inherits_publisher_tier():
    policy = linked_document_policy(
        "https://www.justsecurity.org/wp-content/uploads/example-primary-document.pdf"
    )
    assert policy["parent_source_tier"] == "T4"
    assert policy["inherits_parent_tier"] is False
    assert policy["classification"] == "INDEPENDENT_EVIDENCE_ADJUDICATION_REQUIRED"
    assert "T1" in policy["possible_outcomes"]
    assert "UNRESOLVED" in policy["possible_outcomes"]


def test_living_page_fingerprint_normalizes_whitespace():
    a = b"<html><body><article>Alpha   Beta</article></body></html>"
    b = b"<html>\n<body><article>Alpha\n Beta</article></body>\n</html>"
    assert content_fingerprint(a) == content_fingerprint(b)
