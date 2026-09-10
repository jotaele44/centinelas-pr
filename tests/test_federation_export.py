"""Contract tests for the Centinelas federation export adapter."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_signal_ledger as ledger_builder  # noqa: E402
import federation_export as fx  # noqa: E402

LEDGER = REPO_ROOT / "data/signals/example_signals.jsonl"
SIGNAL_SCHEMA = REPO_ROOT / "schemas/signal.schema.json"
SOURCES = REPO_ROOT / "data/reference/source_registry.csv"

CANONICAL_REQUIRED = {
    "sources": {"source_id", "source_type", "source_name", "confidence", "lineage",
                "synthetic", "created_at", "extracted_at"},
    "entities": {"entity_id", "source_id", "name", "normalized_name", "entity_type",
                 "jurisdiction", "confidence", "lineage", "synthetic", "created_at", "extracted_at"},
    "relationships": {"relationship_id", "source_id", "source_entity_id", "target_entity_id",
                      "relationship_type", "evidence_source_id", "confidence", "lineage",
                      "synthetic", "created_at", "extracted_at"},
    "observations": {"observation_id", "source_id", "observation_type", "observed_at",
                     "confidence", "lineage", "synthetic", "created_at", "extracted_at"},
}


def _signals():
    return [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()]


def _streams():
    registry = fx._load_source_registry(SOURCES)
    return fx.build_streams(_signals(), registry, "2026-07-02T00:00:00Z")


def test_seed_ledger_matches_signal_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SIGNAL_SCHEMA.read_text())
    for row in _signals():
        jsonschema.validate(row, schema)


def test_streams_carry_required_canonical_keys():
    streams = _streams()
    for stream, required in CANONICAL_REQUIRED.items():
        assert streams[stream], f"{stream} stream is empty"
        for row in streams[stream]:
            missing = required - set(row)
            assert not missing, f"{stream} row missing {missing}"


def test_observation_preserves_classifier_provenance():
    signals = _signals()
    signals[0] = {
        **signals[0],
        "classification_method": "keyword_fallback",
        "classifier_reasoning": "LLM unavailable; keyword evidence retained verbatim",
    }
    streams = fx.build_streams(
        signals,
        fx._load_source_registry(SOURCES),
        "2026-07-02T00:00:00Z",
    )
    observation = next(
        row
        for row in streams["observations"]
        if row["attributes"]["signal_id"] == signals[0]["signal_id"]
    )
    assert observation["attributes"]["classification_method"] == "keyword_fallback"
    assert observation["attributes"]["classifier_reasoning"] == (
        "LLM unavailable; keyword evidence retained verbatim"
    )


def test_seed_is_entirely_synthetic():
    for row in _signals():
        assert row.get("is_synthetic") is True


def test_production_mode_rejects_synthetic_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["federation_export.py", "--mode", "production", "--out", str(tmp_path)])
    assert fx.main() == 1  # all seed rows are synthetic -> production is refused


def test_test_mode_writes_conformant_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["federation_export.py", "--mode", "test", "--out", str(tmp_path)])
    assert fx.main() == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert re.fullmatch(r"pkg_[a-f0-9]{32}", manifest["package_id"])
    assert manifest["producer"] == "centinelas-pr"
    assert manifest["federation"]["hub_parent"] == "thehub-pr"
    assert manifest["files"], "manifest must list exported files"
    valid_streams = {"sources", "entities", "relationships", "observations"}
    for entry in manifest["files"]:
        assert entry["stream"] in valid_streams
        assert re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])


def test_production_mode_binds_exact_pass_receipt(tmp_path, monkeypatch):
    signal = {
        **_signals()[0],
        "is_synthetic": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "classification_method": "keyword_fast_path",
        "classifier_reasoning": "multi-domain keyword evidence",
    }
    ledger = tmp_path / "live_signals.jsonl"
    ledger.write_text(json.dumps(signal) + "\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_content = b"fixture feed bytes"
    raw_name = "fixture.feed"
    (raw_dir / raw_name).write_bytes(raw_content)
    config_state = [{"path": "fixture", "bytes": 1, "sha256": "a" * 64}]
    receipt_data = ledger_builder.build_receipt(
        out=ledger,
        raw_dir=raw_dir,
        signals=[signal],
        source_receipts=[
            {
                "name": "Fixture",
                "url": "https://example.test/feed",
                "source_registry_id": signal["source_id"],
                "status": "SUCCESS_WITH_ROWS",
                "http_status": 200,
                "response_content_sha256": fx._sha256(raw_dir / raw_name),
                "response_content_bytes": len(raw_content),
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
    receipt.write_text(
        json.dumps(receipt_data),
        encoding="utf-8",
    )
    out = tmp_path / "export"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "federation_export.py",
            "--ledger",
            str(ledger),
            "--receipt",
            str(receipt),
            "--mode",
            "production",
            "--out",
            str(out),
        ],
    )

    assert fx.main() == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_provenance"]["ledger_sha256"] == fx._sha256(ledger)
    assert manifest["input_provenance"]["receipt_sha256"] == fx._sha256(receipt)
    for stream in ("sources", "entities", "relationships", "observations"):
        rows = [json.loads(line) for line in (out / f"{stream}.jsonl").read_text().splitlines()]
        assert all(str(receipt) in row["lineage"]["source_inputs"] for row in rows)
