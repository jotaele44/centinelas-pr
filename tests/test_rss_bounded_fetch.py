from __future__ import annotations

import httpx

from centinelas.ingest import rss


def test_poll_all_continues_after_feed_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        rss,
        "_load_sources",
        lambda: [{"url": "https://example.invalid/feed", "name": "timeout-feed", "tier": "T2"}],
    )

    calls = []

    def fake_get(url, *, timeout, follow_redirects):
        calls.append((url, timeout, follow_redirects))
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(rss.httpx, "get", fake_get)

    assert rss.poll_all() == []
    assert calls == [("https://example.invalid/feed", rss._FEED_TIMEOUT_SECONDS, True)]


def test_fetch_feed_parses_received_bytes(monkeypatch) -> None:
    class Response:
        content = b"<rss><channel><title>fixture</title></channel></rss>"

        def raise_for_status(self) -> None:
            return None

    seen = {}

    def fake_get(url, *, timeout, follow_redirects):
        seen["request"] = (url, timeout, follow_redirects)
        return Response()

    def fake_parse(payload):
        seen["payload"] = payload
        return "parsed"

    monkeypatch.setattr(rss.httpx, "get", fake_get)
    monkeypatch.setattr(rss.feedparser, "parse", fake_parse)

    assert rss._fetch_feed("https://example.test/feed") == "parsed"
    assert seen["request"] == ("https://example.test/feed", rss._FEED_TIMEOUT_SECONDS, True)
    assert seen["payload"] == Response.content
