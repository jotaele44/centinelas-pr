from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts import build_signal_ledger as ledger_builder
from scripts.federation_export import _production_input_errors, _production_receipt_errors

NOW = datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)


def test_production_rejects_empty_live_ledger() -> None:
    assert _production_input_errors([], now=NOW, max_age_hours=168.0) == [
        "production export rejects an empty live signal ledger"
    ]


def test_production_rejects_stale_live_ledger() -> None:
    errors = _production_input_errors(
        [{"captured_at": "2026-07-12T23:04:32+00:00"}],
        now=NOW,
        max_age_hours=168.0,
    )
    assert len(errors) == 1
    assert "ledger is stale" in errors[0]


def test_production_accepts_fresh_live_ledger() -> None:
    signals = [{"captured_at": "2026-08-09T14:30:00Z"}]
    assert _production_input_errors(signals, now=NOW, max_age_hours=168.0) == []


def test_production_rejects_missing_invalid_or_future_capture_time() -> None:
    for value in (None, "", "not-a-date"):
        errors = _production_input_errors(
            [{"captured_at": value}], now=NOW, max_age_hours=168.0
        )
        assert "missing or invalid captured_at" in errors[0]

    future = _production_input_errors(
        [{"captured_at": "2026-08-09T18:00:00Z"}],
        now=NOW,
        max_age_hours=168.0,
    )
    assert "in the future" in future[0]


def test_production_rejects_nonpositive_max_age() -> None:
    signals = [{"captured_at": "2026-08-09T14:30:00Z"}]
    assert _production_input_errors(signals, now=NOW, max_age_hours=0) == [
        "--max-age-hours must be greater than zero in production mode"
    ]


def _write_ledger(path: Path) -> list[dict]:
    signals = [
        {
            "signal_id": "CENT-SIG-1",
            "captured_at": "2026-09-05T20:00:00Z",
            "is_synthetic": False,
            "classification_method": "keyword_fast_path",
            "classifier_reasoning": "multi-domain keyword evidence",
        }
    ]
    path.write_text(json.dumps(signals[0]) + "\n", encoding="utf-8")
    return signals


def _receipt(path: Path, signals: list[dict]) -> dict:
    raw_dir = path.parent / "raw"
    raw_dir.mkdir(exist_ok=True)
    content = b"fixture feed bytes"
    raw_name = "fixture.feed"
    (raw_dir / raw_name).write_bytes(content)
    config_state = [{"path": "fixture", "bytes": 1, "sha256": "a" * 64}]
    return ledger_builder.build_receipt(
        out=path,
        raw_dir=raw_dir,
        signals=signals,
        source_receipts=[
            {
                "name": "Fixture",
                "url": "https://example.test/feed",
                "source_registry_id": "CENT-SRC-RSS-FIXTURE",
                "status": "SUCCESS_WITH_ROWS",
                "http_status": 200,
                "response_content_sha256": hashlib.sha256(content).hexdigest(),
                "response_content_bytes": len(content),
                "raw_content_path": raw_name,
                "entries_seen": 1,
                "entries_filtered": 0,
                "entries_without_link": 0,
                "accepted_entries": 1,
                "duplicates_suppressed": 0,
                "emitted_items": 1,
            }
        ],
        polled_item_count=1,
        started_at="2026-09-05T20:00:00+00:00",
        completed_at="2026-09-05T20:01:00+00:00",
        limit=None,
        configured_source_count=1,
        repository_head="a" * 40,
        source_config_before=config_state,
        source_config_after=config_state,
    )


def test_production_receipt_accepts_exact_pass_binding(tmp_path) -> None:
    ledger = tmp_path / "signals.jsonl"
    signals = _write_ledger(ledger)
    assert _production_receipt_errors(
        _receipt(ledger, signals), ledger_path=ledger, signals=signals
    ) == []


def test_production_receipt_rejects_missing_provisional_and_tampered(tmp_path) -> None:
    ledger = tmp_path / "signals.jsonl"
    signals = _write_ledger(ledger)
    assert "requires --receipt" in _production_receipt_errors(
        None, ledger_path=ledger, signals=signals
    )[0]

    receipt = _receipt(ledger, signals)
    receipt["classification"] = "PROVISIONAL"
    receipt["gates"] = {"no_source_failures": False}
    errors = _production_receipt_errors(receipt, ledger_path=ledger, signals=signals)
    assert any("not PASS" in error for error in errors)
    assert any("no_source_failures" in error for error in errors)

    receipt = _receipt(ledger, signals)
    ledger.write_text(json.dumps({"signal_id": "tampered"}) + "\n", encoding="utf-8")
    errors = _production_receipt_errors(receipt, ledger_path=ledger, signals=signals)
    assert any("SHA256" in error for error in errors)


def test_production_receipt_rejects_unadjudicated_excluded_source(tmp_path) -> None:
    ledger = tmp_path / "signals.jsonl"
    signals = _write_ledger(ledger)
    receipt = _receipt(ledger, signals)
    receipt["source_scope"]["inventory"] = 2
    receipt["source_scope"]["excluded"] = 1
    receipt["source_scope"]["rows"].append(
        {
            "source_registry_id": "CENT-SRC-RSS-UNRESOLVED",
            "name": "Unresolved",
            "url": "https://example.test/unresolved",
            "active": False,
            "lifecycle_state": "UNRESOLVED",
            "retired_at": None,
            "retirement_reason": None,
            "adjudication_ref": None,
        }
    )
    receipt["gates"]["excluded_sources_adjudicated"] = True
    receipt["gates"]["source_scope_conservation"] = True
    receipt["gates"]["source_scope_registry_ids_unique"] = True

    errors = _production_receipt_errors(receipt, ledger_path=ledger, signals=signals)
    assert any("excluded source scope is not fully adjudicated" in error for error in errors)
