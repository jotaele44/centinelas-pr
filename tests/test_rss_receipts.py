from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from centinelas.ingest import rss

ITEM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Fixture</title>
<item><title>Earthquake bulletin</title><link>https://example.test/item-1</link>
<pubDate>Fri, 05 Sep 2026 12:00:00 GMT</pubDate><description>Observed event</description></item>
</channel></rss>
"""
EMPTY_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Empty fixture</title></channel></rss>
"""
ADJUDICATION_PATH = Path("docs/source_adjudication_20260905.json")


def test_packaged_source_lifecycle_inventory_is_conserved():
    inventory = rss._load_source_inventory()
    active = rss._load_sources()
    excluded = rss._load_excluded_sources()

    assert len(inventory) == 52
    assert len(active) == 48
    assert len(excluded) == 4
    assert len(inventory) == len(active) + len(excluded)
    assert {source["name"] for source in excluded} == {
        "NOAA News",
        "Reuters Business",
        "Associated Press Top News",
        "Reuters World",
    }
    assert all(source.get("lifecycle_state") for source in excluded)
    assert all(source.get("retired_at") for source in excluded)
    assert all(source.get("retirement_reason") for source in excluded)
    assert all(source.get("adjudication_ref") for source in excluded)


def test_packaged_endpoint_refreshes_and_request_identity_are_exact():
    active = {source["name"]: source for source in rss._load_sources()}
    assert active["Yale Environment 360"]["url"] == "https://e360.yale.edu/feed.xml"
    assert active["Volcano Discovery"]["url"] == (
        "https://www.volcanodiscovery.com/volcanoesandearthquakenews.rss"
    )
    assert active["The Black Vault"]["url"] == (
        "https://www.theblackvault.com/documentarchive/feed/"
    )
    assert active["MUFON"]["url"] == "https://mufon.com/feed/"
    assert rss._HTTP_HEADERS["User-Agent"].startswith("Mozilla/5.0 (compatible;")
    assert "Centinelas/0.1" in rss._HTTP_HEADERS["User-Agent"]
    assert "github.com/jotaele44/centinelas-pr" in rss._HTTP_HEADERS["User-Agent"]


def test_source_adjudication_arithmetic_closes():
    adjudication = json.loads(ADJUDICATION_PATH.read_text(encoding="utf-8"))
    classifications = Counter(
        source["classification"] for source in adjudication["sources"]
    )
    excluded_states = {
        "NONCANONICAL_ACCESS_BLOCKED",
        "RETIRED_NO_EQUIVALENT_PUBLIC_FEED",
        "RETIRED_NO_PUBLIC_FEED",
    }
    excluded_count = sum(
        count for state, count in classifications.items() if state in excluded_states
    )

    assert classifications == adjudication["classification_counts"]
    assert len(adjudication["sources"]) == adjudication["source_count"] == 13
    assert adjudication["arithmetic"] == {
        "classified": 13,
        "unresolved": 0,
        "active_after_adjudication": 13 - excluded_count,
        "excluded_after_adjudication": excluded_count,
    }


def response(content: bytes, status: int = 200) -> rss.FeedResponse:
    return rss.FeedResponse(
        content=content,
        status_code=status,
        final_url="https://example.test/final",
        content_type="application/rss+xml",
        content_encoding="",
        redirect_statuses=(301,),
    )


def test_poll_receipts_distinguish_every_zero_row_state(tmp_path, monkeypatch):
    sources = [
        {"name": "Rows", "url": "https://example.test/rows", "tier": "T1"},
        {"name": "Empty", "url": "https://example.test/empty", "tier": "T2"},
        {
            "name": "Filtered",
            "url": "https://example.test/filtered",
            "tier": "T3",
            "match_any": ["Puerto Rico"],
        },
        {"name": "Malformed", "url": "https://example.test/malformed", "tier": "T2"},
        {"name": "HTTP Error", "url": "https://example.test/http-error", "tier": "T2"},
        {"name": "Fetch Error", "url": "https://example.test/fetch-error", "tier": "T2"},
    ]
    responses = {
        "https://example.test/rows": response(ITEM_FEED),
        "https://example.test/empty": response(EMPTY_FEED),
        "https://example.test/filtered": response(ITEM_FEED),
        "https://example.test/malformed": response(b"<not-a-feed"),
        "https://example.test/http-error": response(b"upstream failure", 503),
    }

    def fake_fetch(url: str, timeout_seconds: float) -> rss.FeedResponse:
        assert timeout_seconds == 7.0
        if url.endswith("fetch-error"):
            raise RuntimeError("network unavailable")
        return responses[url]

    monkeypatch.setattr(rss, "_load_sources", lambda: sources)
    monkeypatch.setattr(rss, "_fetch_feed", fake_fetch)
    raw_dir = tmp_path / "raw"
    items, receipts = rss.poll_all_with_receipts(raw_dir=raw_dir, timeout_seconds=7.0)

    assert len(items) == 1
    assert len(receipts) == len(sources)
    assert Counter(row["status"] for row in receipts) == {
        "SUCCESS_WITH_ROWS": 1,
        "SUCCESS_EMPTY": 1,
        "SUCCESS_FILTERED_EMPTY": 1,
        "PARSE_ERROR": 1,
        "HTTP_ERROR": 1,
        "FETCH_ERROR": 1,
    }
    assert len(list(raw_dir.iterdir())) == 5

    for receipt in receipts:
        if receipt["response_content_sha256"] is None:
            assert receipt["raw_content_path"] is None
            continue
        raw_path = raw_dir / receipt["raw_content_path"]
        assert raw_path.is_file()
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == receipt[
            "response_content_sha256"
        ]

    parsed = [row for row in receipts if row["http_status"] == 200]
    for receipt in parsed:
        assert receipt["entries_seen"] == (
            receipt["entries_filtered"]
            + receipt["entries_without_link"]
            + receipt["accepted_entries"]
        )
        assert receipt["accepted_entries"] == (
            receipt["duplicates_suppressed"] + receipt["emitted_items"]
        )
