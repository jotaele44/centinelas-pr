"""Contract tests for the Centinelas federation export adapter."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

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
