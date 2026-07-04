"""Offline tests for the intake-engine -> signal-ledger bridge."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

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
