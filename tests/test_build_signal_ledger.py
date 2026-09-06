"""Offline tests for the intake-engine -> signal-ledger bridge."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import build_signal_ledger as ledger_builder  # noqa: E402
from build_signal_ledger import feed_source_id, item_to_signal, source_name_to_id  # noqa: E402

from centinelas.classify.rules import keyword_classify  # noqa: E402
from centinelas.models import ClassifiedItem, DomainLabel  # noqa: E402

FIXTURES = json.loads((REPO_ROOT / "tests" / "fixtures" / "sample_items.json").read_text())
SIGNAL_SCHEMA = json.loads((REPO_ROOT / "schemas" / "signal.schema.json").read_text())


def _classified(fixture: dict) -> ClassifiedItem:
    now = datetime.now(timezone.utc)
    labels = keyword_classify(f"{fixture['title']} {fixture.get('body_text', '')}")
    return ClassifiedItem(
        item_id=fixture.get("item_id", "abc123def4567890"),
        source_url=fixture.get("source_url", "https://example.org/item"),
        source_name=fixture.get("source_name", "BBC World"),
        title=fixture["title"],
        body_text=fixture.get("body_text", ""),
        published_at=now,
        captured_at=now,
        evidence_tier=fixture.get("evidence_tier", "T2"),
        labels=labels or [DomainLabel.UNCLASSIFIED],
        confidence=0.85 if labels else 0.3,
        classifier_reasoning="keyword test",
    )


def test_bridged_rows_validate_against_signal_schema():
    jsonschema = pytest.importorskip("jsonschema")
    source_ids = source_name_to_id()
    for fixture in FIXTURES:
        row = item_to_signal(_classified(fixture), source_ids)
        jsonschema.validate(row, SIGNAL_SCHEMA)


def test_bridged_rows_are_never_synthetic():
    source_ids = source_name_to_id()
    for fixture in FIXTURES:
        assert item_to_signal(_classified(fixture), source_ids)["is_synthetic"] is False


def test_signal_ids_and_stage_are_derived():
    row = item_to_signal(_classified(FIXTURES[0]), source_name_to_id())
    assert row["signal_id"].startswith("CENT-SIG-")
    assert row["matter_id"].startswith("CENT-MAT-")
    assert row["signal_stage"] == "raw_observation"
    assert 0 <= row["confidence_score"] <= 100


def test_every_engine_feed_has_a_registry_row():
    with open(REPO_ROOT / "data" / "reference" / "source_registry.csv") as fh:
        registry_ids = {r["source_id"] for r in csv.DictReader(fh)}
    for name, source_id in source_name_to_id().items():
        assert source_id in registry_ids, f"feed {name!r} missing from source_registry.csv"
        assert source_id == feed_source_id(name)


def test_signal_row_carries_classifier_provenance():
    row = item_to_signal(
        _classified(FIXTURES[0]),
        source_name_to_id(),
        classification_method="keyword_fast_path",
    )
    assert row["classification_method"] == "keyword_fast_path"
    assert row["classifier_reasoning"] == "keyword test"


def source_receipt(raw_name: str, content: bytes) -> dict:
    return {
        "source_index": 1,
        "configured_source_id": "CENT-SRC-RSS-FIXTURE",
        "source_registry_id": "CENT-SRC-RSS-FIXTURE",
        "name": "Fixture",
        "url": "https://example.test/feed",
        "tier": "T1",
        "filter_term_count": 0,
        "retrieved_at": "2026-09-05T20:00:00+00:00",
        "status": "SUCCESS_WITH_ROWS",
        "http_status": 200,
        "final_url": "https://example.test/feed",
        "redirect_statuses": [],
        "content_type": "application/rss+xml",
        "content_encoding": "",
        "response_content_byte_scope": "decoded_http_entity_body",
        "response_content_bytes": len(content),
        "response_content_sha256": hashlib.sha256(content).hexdigest(),
        "raw_content_path": raw_name,
        "parser_bozo": False,
        "parser_error": None,
        "entries_seen": 1,
        "entries_filtered": 0,
        "entries_without_link": 0,
        "accepted_entries": 1,
        "duplicates_suppressed": 0,
        "emitted_items": 1,
    }


def test_receipt_pass_requires_closed_provenance_gates(tmp_path, monkeypatch):
    out = tmp_path / "live_signals.jsonl"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    content = b"fixture feed bytes"
    (raw_dir / "fixture.feed").write_bytes(content)
    signal = item_to_signal(
        _classified(FIXTURES[0]),
        source_name_to_id(),
        classification_method="keyword_fast_path",
    )
    out.write_text(json.dumps(signal) + "\n", encoding="utf-8")
    config_state = [{"path": "fixture", "bytes": 1, "sha256": "a" * 64}]

    receipt = ledger_builder.build_receipt(
        out=out,
        raw_dir=raw_dir,
        signals=[signal],
        source_receipts=[source_receipt("fixture.feed", content)],
        polled_item_count=1,
        started_at="2026-09-05T20:00:00+00:00",
        completed_at="2026-09-05T20:01:00+00:00",
        limit=None,
        configured_source_count=1,
        repository_head="a" * 40,
        source_config_before=config_state,
        source_config_after=config_state,
    )

    assert receipt["classification"] == "PASS"
    assert all(receipt["gates"].values())

    receipt = ledger_builder.build_receipt(
        out=out,
        raw_dir=raw_dir,
        signals=[signal],
        source_receipts=[source_receipt("fixture.feed", content)],
        polled_item_count=1,
        started_at="2026-09-05T20:00:00+00:00",
        completed_at="2026-09-05T20:01:00+00:00",
        limit=None,
        configured_source_count=1,
        repository_head="a" * 40,
        source_config_before=config_state,
        source_config_after=config_state,
        source_scope_rows=[
            {
                "source_registry_id": "CENT-SRC-RSS-FIXTURE",
                "active": True,
                "lifecycle_state": "ACTIVE",
            },
            {
                "source_registry_id": None,
                "active": False,
                "lifecycle_state": "RETIRED_NO_PUBLIC_FEED",
                "retired_at": "2026-09-05T22:04:53Z",
                "retirement_reason": "Publisher removed the public feed.",
                "adjudication_ref": "docs/source-adjudication.json",
            },
        ],
    )

    assert receipt["classification"] == "PROVISIONAL"
    assert receipt["gates"]["source_scope_registry_ids_unique"] is False


def test_strict_snapshot_preserves_provisional_receipt_before_failing(
    tmp_path, monkeypatch
):
    out = tmp_path / "live_signals.jsonl"
    receipt_path = tmp_path / "receipt.json"
    raw_dir = tmp_path / "raw"
    content = b"fixture feed bytes"
    signal = item_to_signal(
        _classified(FIXTURES[0]),
        source_name_to_id(),
        classification_method="keyword_fallback",
    )

    def fake_build(limit=None, *, raw_dir=None, timeout_seconds=20.0, sources=None):
        assert raw_dir is not None
        raw_dir.mkdir(parents=True)
        (raw_dir / "fixture.feed").write_bytes(content)
        return [signal], [source_receipt("fixture.feed", content)], 1

    monkeypatch.setattr(ledger_builder, "build_ledger_with_receipts", fake_build)
    monkeypatch.setattr(ledger_builder.rss, "_load_sources", lambda: [{"name": "Fixture"}])
    monkeypatch.setattr(
        ledger_builder,
        "source_config_state",
        lambda: [{"path": "fixture", "bytes": 1, "sha256": "a" * 64}],
    )
    monkeypatch.setattr(ledger_builder, "git_head", lambda: "a" * 40)
    result = ledger_builder.main(
        [
            "--out",
            str(out),
            "--receipt",
            str(receipt_path),
            "--raw-dir",
            str(raw_dir),
            "--require-complete-sources",
        ]
    )

    assert result == 1
    assert out.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["classification"] == "PROVISIONAL"
    assert receipt["gates"]["no_classifier_fallback"] is False


def test_receipt_is_provisional_when_limit_truncates_polled_items(tmp_path):
    out = tmp_path / "live_signals.jsonl"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    content = b"fixture feed bytes"
    (raw_dir / "fixture.feed").write_bytes(content)
    signal = item_to_signal(
        _classified(FIXTURES[0]),
        source_name_to_id(),
        classification_method="keyword_fast_path",
    )
    out.write_text(json.dumps(signal) + "\n", encoding="utf-8")
    config_state = [{"path": "fixture", "bytes": 1, "sha256": "a" * 64}]

    receipt = ledger_builder.build_receipt(
        out=out,
        raw_dir=raw_dir,
        signals=[signal],
        source_receipts=[source_receipt("fixture.feed", content)],
        polled_item_count=2,
        started_at="2026-09-05T20:00:00+00:00",
        completed_at="2026-09-05T20:01:00+00:00",
        limit=1,
        configured_source_count=1,
        repository_head="a" * 40,
        source_config_before=config_state,
        source_config_after=config_state,
    )

    assert receipt["classification"] == "PROVISIONAL"
    assert receipt["gates"]["full_polled_item_retention"] is False


def test_source_scope_preserves_adjudicated_exclusions():
    scope = ledger_builder.build_source_scope(
        [
            {"name": "Active", "url": "https://example.test/active"},
            {
                "name": "Retired",
                "url": "https://example.test/retired",
                "enabled": False,
                "lifecycle_state": "RETIRED_NO_PUBLIC_FEED",
                "retired_at": "2026-09-05T22:04:53Z",
                "retirement_reason": "Publisher removed the public feed.",
                "adjudication_ref": "docs/source-adjudication.json",
            },
        ]
    )

    assert len(scope) == 2
    assert [row["active"] for row in scope] == [True, False]
    assert scope[1]["lifecycle_state"] == "RETIRED_NO_PUBLIC_FEED"
    assert scope[1]["source_registry_id"] == "CENT-SRC-RSS-RETIRED"


def test_snapshot_refuses_to_overwrite_existing_evidence(tmp_path, monkeypatch):
    out = tmp_path / "live_signals.jsonl"
    out.write_text("existing\n", encoding="utf-8")

    def unexpected_build(*args, **kwargs):
        raise AssertionError("polling must not start for an existing snapshot")

    monkeypatch.setattr(ledger_builder, "build_ledger_with_receipts", unexpected_build)
    result = ledger_builder.main(
        [
            "--out",
            str(out),
            "--receipt",
            str(tmp_path / "receipt.json"),
            "--raw-dir",
            str(tmp_path / "raw"),
        ]
    )
    assert result == 2
    assert out.read_text(encoding="utf-8") == "existing\n"
