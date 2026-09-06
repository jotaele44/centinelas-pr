"""Regression gates for the receipt-first Puerto Rico source tranche."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

from centinelas.ingest import puerto_rico as pr


def test_every_configured_manifestation_has_a_dedicated_registry_row() -> None:
    config_ids = {row["source_registry_id"] for row in pr.load_config()["sources"]}
    with pr.REGISTRY_PATH.open(encoding="utf-8") as handle:
        registry_ids = {row["source_id"] for row in csv.DictReader(handle)}
    assert config_ids == registry_ids


def source(**overrides) -> dict:
    row = {
        "source_registry_id": "CENT-SRC-PREB-NOTICES",
        "name": "Fixture",
        "family": "PREB",
        "manifestation": "fixture",
        "url": "https://example.test/notices/",
        "parser": "preb_notices",
        "next_selector": ".pager a.next_page",
        "max_requests": 10,
        "bound": "fixture bound",
        "tier": "T1",
    }
    row.update(overrides)
    return row


def preb_page(post_id: int, *, next_url: str | None = None) -> bytes:
    next_link = (
        f'<div class="pager"><a class="next_page" href="{next_url}">Next</a></div>'
        if next_url
        else ""
    )
    return f"""
    <article class="post post-item post-{post_id}">
      <div class="date_label">16 16America/Puerto_Rico abril 16America/Puerto_Rico 2026</div>
      <div class="post-title"><a href="/notice-{post_id}/">Aviso {post_id}</a></div>
      <div class="post-excerpt">Texto crudo {post_id}</div>
    </article>{next_link}
    """.encode()


def response(content: bytes, *, rowcount: str | None = None) -> pr.SourceResponse:
    headers = {"rowcount": rowcount} if rowcount is not None else {}
    return pr.SourceResponse(
        content=content,
        status_code=200,
        final_url="https://example.test/",
        content_type="text/html",
        content_encoding="",
        redirect_statuses=(),
        headers=headers,
    )


def test_preb_parser_preserves_raw_strings_and_source_local_identity() -> None:
    records = pr.parse_preb_notices(source(), preb_page(85990), "https://example.test/")
    assert len(records) == 1
    record = records[0]
    assert record["source_record_id_raw"] == "85990"
    assert record["title_raw"] == "Aviso 85990"
    assert record["body_raw"] == "Texto crudo 85990"
    assert record["published_at"] == "2026-04-16T04:00:00+00:00"
    assert record["identity_effect"] == "NONE"
    assert record["binding_state"] == "UNRESOLVED"


def test_paginated_capture_closes_and_binds_each_raw_member(tmp_path, monkeypatch) -> None:
    pages = {
        "https://example.test/notices/": response(
            preb_page(1, next_url="https://example.test/notices/page/2/")
        ),
        "https://example.test/notices/page/2/": response(preb_page(2)),
    }
    monkeypatch.setattr(pr, "_fetch", lambda client, url: pages[url])
    records, receipt = pr.capture_source(
        source(),
        source_index=1,
        raw_dir=tmp_path,
        captured_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        client=object(),
    )
    assert receipt["status"] == "SUCCESS_WITH_ROWS"
    assert receipt["pagination_complete"] is True
    assert receipt["pagination_stop_reason"] == "no_next_link"
    assert len(records) == receipt["entries_seen"] == receipt["emitted_items"] == 2
    assert len(receipt["requests"]) == 2
    assert {row["raw_response_path"] for row in records} == {
        request["raw_content_path"] for request in receipt["requests"]
    }


def test_nonempty_required_source_fails_closed_on_zero_parse(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pr, "_fetch", lambda client, url: response(b"<html></html>"))
    records, receipt = pr.capture_source(
        source(),
        source_index=1,
        raw_dir=tmp_path,
        captured_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        client=object(),
    )
    assert records == []
    assert receipt["status"] == "PARSE_ERROR"
    assert "zero rows" in receipt["parser_error"]


def test_cor3_rowcount_drift_is_not_accepted(tmp_path, monkeypatch) -> None:
    first = json.dumps(
        [{"id": 1, "display_date": "2026-09-03T00:00:00Z", "internal_properties": "{}"}]
    ).encode()
    second = json.dumps(
        [{"id": 2, "display_date": "2026-09-02T00:00:00Z", "internal_properties": "{}"}]
    ).encode()
    replies = iter([response(first, rowcount="2"), response(second, rowcount="3")])
    requested_urls: list[str] = []

    def fetch(client, url):
        requested_urls.append(url)
        return next(replies)

    monkeypatch.setattr(pr, "_fetch", fetch)
    records, receipt = pr.capture_source(
        source(
            source_registry_id="CENT-SRC-COR3-PRESS",
            family="COR3",
            manifestation="press_api",
            parser="cor3_press",
            url="https://example.test/api?offset={offset}",
            public_listing_url="https://example.test/press",
            next_selector=None,
        ),
        source_index=1,
        raw_dir=tmp_path,
        captured_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        client=object(),
    )
    assert len(records) == 2
    assert receipt["status"] == "PARSE_ERROR"
    assert "rowcount changed" in receipt["parser_error"]
    assert receipt["pagination_complete"] is False
    assert requested_urls == [
        "https://example.test/api?offset=0",
        "https://example.test/api?offset=1",
    ]


def test_snapshot_verification_detects_raw_tampering(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw = raw_dir / "source.html"
    raw.write_bytes(b"original")
    out = tmp_path / "records.jsonl"
    out.write_text("", encoding="utf-8")
    source_receipt = {
        "emitted_items": 0,
        "requests": [
            {
                "raw_content_path": "source.html",
                "response_content_bytes": 8,
                "response_content_sha256": pr.sha256_bytes(b"original"),
            }
        ],
    }
    receipt = {
        "output": {
            "path": str(out),
            "bytes": 0,
            "sha256": pr.sha256_path(out),
            "records": 0,
        },
        "sources": {"raw_directory": str(raw_dir), "rows": [source_receipt]},
    }
    assert pr.snapshot_errors(receipt) == []
    raw.write_bytes(b"tampered")
    assert pr.snapshot_errors(receipt) == ["raw response does not match receipt: source.html"]


def test_max_request_ceiling_is_explicit_truncation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        pr,
        "_fetch",
        lambda client, url: response(preb_page(1, next_url="https://example.test/page/2/")),
    )
    _, receipt = pr.capture_source(
        source(max_requests=1),
        source_index=1,
        raw_dir=tmp_path,
        captured_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        client=object(),
    )
    assert receipt["status"] == "TRUNCATED"
    assert receipt["pagination_complete"] is False
    assert receipt["pagination_stop_reason"] == "max_requests_reached_with_more_available"
