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


def _bound_file(path: Path, *, name: str | None = None) -> dict:
    content = path.read_bytes()
    result = {
        "path": str(path),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    if name is not None:
        result["name"] = name
    return result


def _overlay_fixture(tmp_path: Path) -> tuple[Path, list[dict], dict]:
    base_ledger = tmp_path / "base.jsonl"
    base_signals = _write_ledger(base_ledger)
    base_receipt = tmp_path / "base-receipt.json"
    base_receipt.write_text("{}\n", encoding="utf-8")
    source_registry = tmp_path / "source-registry.csv"
    source_registry.write_text("source_id,source_family\nCENT-SRC-1,news_wire\n")
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"frozen model fixture")

    ledger = tmp_path / "derived.jsonl"
    signal = {
        **base_signals[0],
        "labels": ["UNCLASSIFIED"],
        "beat": "unclassified",
        "signal_type": "unclassified_signal",
        "confidence_score": 70.0,
        "classification_method": "model_assisted_adjudication",
        "classifier_reasoning": "No sufficiently supported domain label.",
    }
    ledger.write_text(json.dumps(signal, sort_keys=True) + "\n", encoding="utf-8")
    signals = [signal]

    decisions = tmp_path / "decisions.jsonl"
    final = {
        field: signal.get(field)
        for field in (
            "beat", "classification_method", "classifier_reasoning",
            "confidence_score", "labels", "signal_type",
        )
    }
    decision = {
        "signal_id": signal["signal_id"],
        "state": "TERMINAL",
        "nli_scores": {
            label: 0.125
            for label in (
                "ENVIRONMENTAL", "FINANCIAL", "POLITICAL", "GEO_GEOLOGY",
                "ANOMALOUS", "MILITARY_AEROSPACE", "SAFETY_COMPLIANCE",
                "UNCLASSIFIED",
            )
        },
        "final": final,
    }
    decisions.write_text(json.dumps(decision, sort_keys=True) + "\n", encoding="utf-8")

    receipt = _receipt(ledger, signals)
    receipt["schema_version"] = "1.1.0"
    receipt["classification_repository_head"] = "b" * 40
    receipt["ledger"]["classification_method_counts"] = {
        "model_assisted_adjudication": 1
    }
    overlay_gates = {
        "exact_base_ledger_binding", "exact_base_receipt_binding", "model_files_bound",
        "complete_decision_coverage", "unique_decision_ids",
        "two_pass_score_determinism", "row_conservation",
        "immutable_fields_preserved", "terminal_decisions", "zero_unresolved_decisions",
        "review_ledger_bound", "review_exact_target_coverage",
    }
    receipt["gates"].update({gate: True for gate in overlay_gates})
    algorithm = {"name": "fixture", "acceptance_support_total": 3}
    algorithm_hash = hashlib.sha256(
        json.dumps(algorithm, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    score_hash = "c" * 64
    receipt["classification_overlay"] = {
        "base_ledger": {**_bound_file(base_ledger), "rows": 1},
        "base_receipt": _bound_file(base_receipt),
        "source_registry": _bound_file(source_registry),
        "model": {
            "repository": "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
            "revision": "0a71e92a985b6e1ad1828cf67ce9c459639c1dca",
            "files": [_bound_file(model_file, name="model.onnx")],
        },
        "algorithm": {**algorithm, "sha256": algorithm_hash},
        "decisions": {
            **_bound_file(decisions),
            "rows": 1,
            "state_counts": {"TERMINAL": 1},
            "unresolved": 0,
        },
        "two_pass_score_vectors_sha256": [score_hash, score_hash],
        "original_to_derived_label_equivalence": {
            "intersection": 0,
            "a_only": 0,
            "b_only": 1,
            "union": 1,
            "symmetric_difference": 1,
        },
    }
    return ledger, signals, receipt


def test_production_receipt_accepts_verified_classification_overlay(tmp_path) -> None:
    ledger, signals, receipt = _overlay_fixture(tmp_path)
    assert _production_receipt_errors(
        receipt, ledger_path=ledger, signals=signals
    ) == []


def test_production_receipt_rejects_tampered_or_unresolved_overlay(tmp_path) -> None:
    ledger, signals, receipt = _overlay_fixture(tmp_path)
    receipt["classification_overlay"]["model"]["revision"] = "main"
    receipt["gates"]["zero_unresolved_decisions"] = False

    errors = _production_receipt_errors(receipt, ledger_path=ledger, signals=signals)

    assert any("model revision is not frozen" in error for error in errors)
    assert any("zero_unresolved_decisions" in error for error in errors)
