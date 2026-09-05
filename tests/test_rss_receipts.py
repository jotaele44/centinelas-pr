from __future__ import annotations

import hashlib
from collections import Counter

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
