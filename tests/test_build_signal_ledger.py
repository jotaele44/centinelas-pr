"""Offline tests for the intake-engine -> signal-ledger bridge."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
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


# --- enrichment, Puerto Rico relevance and publication-age window ------------


def _dated(item_id: str, source_name: str, title: str, published_at: datetime, body: str = ""):
    from centinelas.models import RawItem

    return RawItem(
        item_id=item_id,
        source_url=f"https://example.org/{item_id}",
        source_name=source_name,
        title=title,
        body_text=body,
        published_at=published_at,
        captured_at=datetime.now(timezone.utc),
        evidence_tier="T2",
    )


def test_enrichment_reaches_the_ledger_row(monkeypatch):
    from centinelas.classify import classifier

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    raw = _dated(
        "award1",
        "Del Valle Group",
        "Del Valle Group announces the award of a $12.5 million contract",
        datetime.now(timezone.utc),
        body="The contract was awarded by PRASA for aqueduct rehabilitation in Puerto Rico.",
    )
    row = item_to_signal(classifier.build_classified_item(raw), source_name_to_id())
    assert row["agencies"] == ["PRASA"]
    assert row["entities"] == ["Del Valle Group"]
    assert row["estimated_value"] == 12_500_000
    # An announced award is not an official record: pending, never finalized.
    assert row["signal_stage"] == "officialization_pending"
    pytest.importorskip("jsonschema").validate(row, SIGNAL_SCHEMA)


def test_open_solicitation_maps_to_rfp_open():
    item = _classified({"title": "x", "body_text": ""}).model_copy(
        update={"signal_stage": "rfp_open"}
    )
    assert item_to_signal(item, {})["signal_stage"] == "rfp_open"


def test_unknown_enrichment_stage_falls_back_to_raw_observation():
    item = _classified({"title": "x", "body_text": ""}).model_copy(
        update={"signal_stage": "not_in_schema"}
    )
    assert item_to_signal(item, {})["signal_stage"] == "raw_observation"


def test_global_feeds_are_marked_and_pr_sources_are_not():
    import build_signal_ledger as bsl

    global_sources = bsl.global_source_names()
    assert {"BBC World", "Financial Times", "OSHA News Releases"} <= global_sources
    assert not [name for name in global_sources if name.startswith(("DRNA", "Del Valle"))]


def test_relevance_filter_only_applies_to_global_feeds():
    import build_signal_ledger as bsl

    now = datetime.now(timezone.utc)
    items = [
        _dated("g1", "BBC World", "Markets rally in Asia", now),
        _dated("g2", "BBC World", "Huracán amenaza a los puertorriqueños", now),
        _dated("g3", "BBC World", "Storm season", now, body="Landfall near Vieques expected."),
        # A Puerto Rico source never has to name the island to be kept.
        _dated("p1", "DRNA — Avisos", "Aviso de vista pública", now),
    ]
    kept, dropped = bsl.filter_items(items, global_sources={"BBC World"}, max_age_days=None)
    assert [it.item_id for it in kept] == ["g2", "g3", "p1"]
    assert dropped == {"not_pr_relevant": 1, "older_than_window": 0}


def test_age_window_drops_old_items_but_keeps_future_dated_ones():
    import build_signal_ledger as bsl

    now = datetime(2026, 11, 14, tzinfo=timezone.utc)
    items = [
        _dated("old", "DRNA — Reglamentos", "Reglamento", now - timedelta(days=91)),
        _dated("edge", "DRNA — Avisos", "Aviso", now - timedelta(days=90)),
        # ASG dates a listing by its bid opening: a pending event, not a bad date.
        _dated("bid", "ASG — Licitaciones (Subastas)", "Subasta Formal", now + timedelta(days=45)),
    ]
    kept, dropped = bsl.filter_items(items, max_age_days=90, now=now)
    assert [it.item_id for it in kept] == ["edge", "bid"]
    assert dropped == {"not_pr_relevant": 0, "older_than_window": 1}
    assert len(bsl.filter_items(items, max_age_days=0, now=now)[0]) == 3


def test_build_ledger_filters_before_capping_and_refuses_an_empty_result(monkeypatch, capsys):
    import build_signal_ledger as bsl

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    now = datetime.now(timezone.utc)
    noise = [_dated(f"n{i}", "BBC World", "World news", now) for i in range(5)]
    stale = _dated("s1", "DRNA — Avisos", "Aviso viejo", now - timedelta(days=400))
    fresh = _dated("f1", "DRNA — Avisos", "Aviso de vista pública", now)
    monkeypatch.setattr(bsl, "collect_raw_items", lambda rss_only=False: [*noise, stale, fresh])
    # With a total cap of 1 the single slot must go to the surviving DRNA item,
    # not to a filtered-out item polled earlier.
    rows = bsl.build_ledger(limit=1, per_source=10)
    assert [row["signal_id"] for row in rows] == ["CENT-SIG-f1"]
    assert "dropped_not_pr_relevant=5 dropped_older_than_window=1" in capsys.readouterr().out

    monkeypatch.setattr(bsl, "collect_raw_items", lambda rss_only=False: noise)
    with pytest.raises(SystemExit, match="filtered out"):
        bsl.build_ledger()
