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


# --- intake layers and per-source cap ---------------------------------------


def _raw(item_id: str, source_name: str):
    from centinelas.models import RawItem

    now = datetime.now(timezone.utc)
    return RawItem(
        item_id=item_id,
        source_url=f"https://example.org/{item_id}",
        source_name=source_name,
        title=f"item {item_id}",
        body_text="",
        published_at=now,
        captured_at=now,
        evidence_tier="T2",
    )


def test_cap_items_keeps_late_sources_under_a_total_cap():
    import build_signal_ledger as bsl

    # 50 items from a noisy feed polled first, then 3 DRNA permit notices last:
    # the old first-N cut kept none of the DRNA items.
    items = [_raw(f"n{i}", "Noisy Feed") for i in range(50)]
    items += [_raw(f"d{i}", "DRNA Aviso Ambiental") for i in range(3)]
    capped = bsl.cap_items(items, per_source=10, total=12)
    sources = [it.source_name for it in capped]
    assert len(capped) == 12
    assert sources.count("DRNA Aviso Ambiental") == 3
    assert sources.count("Noisy Feed") == 9


def test_cap_items_without_caps_interleaves_sources():
    import build_signal_ledger as bsl

    items = [_raw("a1", "A"), _raw("a2", "A"), _raw("b1", "B")]
    assert [it.item_id for it in bsl.cap_items(items)] == ["a1", "b1", "a2"]


def test_collect_raw_items_merges_all_layers(monkeypatch):
    import build_signal_ledger as bsl

    monkeypatch.setattr(bsl.rss, "poll_all", lambda: [_raw("r1", "RSS"), _raw("dup", "RSS")])
    monkeypatch.setattr(bsl, "poll_federal_register", lambda: [_raw("f1", "Federal Register")])
    monkeypatch.setattr(bsl, "poll_scrape_sources", lambda: [_raw("dup", "OGPe"), _raw("s1", "OGPe")])
    ids = [it.item_id for it in bsl.collect_raw_items()]
    assert ids == ["r1", "dup", "f1", "s1"]
    assert [it.item_id for it in bsl.collect_raw_items(rss_only=True)] == ["r1", "dup"]
