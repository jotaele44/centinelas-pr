"""Tests for the router — label→repo mapping and thehub guarantee."""

import json
from datetime import datetime, timezone
from pathlib import Path


from centinelas.classify.labels import DomainLabel, HUB_REPO
from centinelas.models import ClassifiedItem
from centinelas.route.router import resolve_targets, route


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_items.json").read_text()
)


def _make_classified(item_dict: dict) -> ClassifiedItem:
    return ClassifiedItem.model_validate(item_dict)


def test_military_aerospace_routes_to_skywatcher():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "aero001"))
    targets = resolve_targets(item)
    assert "skywatcher-pr" in targets


def test_environmental_routes_to_aguayluz():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "env001"))
    targets = resolve_targets(item)
    assert "aguayluz-pr" in targets


def test_geo_routes_to_spiderweb():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "geo001"))
    targets = resolve_targets(item)
    assert "spiderweb-pr" in targets


def test_financial_routes_to_moneysweep():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "fin001"))
    targets = resolve_targets(item)
    assert "moneysweep-pr" in targets


def test_political_routes_to_moneysweep():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "pol001"))
    targets = resolve_targets(item)
    assert "moneysweep-pr" in targets


def test_anomalous_routes_to_ovnis():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "uap001")
    )
    targets = resolve_targets(item)
    assert "ovnis-pr" in targets


def test_multi_label_routes_to_multiple_repos():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "multi001"))
    targets = resolve_targets(item)
    assert "skywatcher-pr" in targets
    assert "aguayluz-pr" in targets


def test_thehub_always_receives_every_item():
    for fixture in FIXTURES:
        item = _make_classified(fixture)
        payloads = route(item)
        assert HUB_REPO in payloads, f"thehub missing for item {fixture['item_id']}"


def test_unclassified_only_routes_to_thehub():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "unc001"))
    payloads = route(item)
    repos = list(payloads.keys())
    assert repos == [HUB_REPO]


def test_payload_contains_required_fields():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "aero001"))
    payloads = route(item)
    for repo, payload in payloads.items():
        for field in ("item_id", "source_url", "title", "labels", "captured_at", "routed_to"):
            assert field in payload, f"Missing field '{field}' in payload for {repo}"


def test_moneysweep_payload_carries_finance_enrichment():
    # A FINANCIAL item with pre-official finance/location enrichment must
    # forward those fields to the MoneySweep anchor (and the Hub), while the
    # lean base payload keeps them off other targets.
    item = ClassifiedItem(
        item_id="finenrich001",
        source_url="https://example.com/rfp",
        source_name="Test",
        title="AAA procurement RFP in Ponce",
        body_text="Autoridad de Acueductos y Alcantarillados opens RFP",
        published_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
        labels=[DomainLabel.FINANCIAL, DomainLabel.GEO_GEOLOGY],
        confidence=0.9,
        classifier_reasoning="test",
        municipalities=["Ponce"],
        recipients=["Acme Construction Corp"],
        agencies=["Autoridad de Acueductos y Alcantarillados"],
        estimated_value=1500000.0,
        signal_stage="rfp_open",
        beat="contracts",
    )
    payloads = route(item)
    ms = payloads["moneysweep-pr"]
    assert ms["municipalities"] == ["Ponce"]
    assert ms["recipients"] == ["Acme Construction Corp"]
    assert ms["agencies"] == ["Autoridad de Acueductos y Alcantarillados"]
    assert ms["estimated_value"] == 1500000.0
    assert ms["signal_stage"] == "rfp_open"
    assert ms["beat"] == "contracts"
    # Only the MoneySweep anchor carries the enrichment; every other target —
    # including the Hub — stays on the base contract shape.
    assert "estimated_value" not in payloads[HUB_REPO]
    assert "recipients" not in payloads[HUB_REPO]
    assert "estimated_value" not in payloads["spiderweb-pr"]


def test_finance_enrichment_defaults_empty_when_absent():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "fin001"))
    payloads = route(item)
    ms = payloads["moneysweep-pr"]
    assert ms["municipalities"] == []
    assert ms["recipients"] == []
    assert ms["agencies"] == []
    assert ms["estimated_value"] is None


def test_ovnis_payload_carries_municipalities():
    # An ANOMALOUS item with resolved municipalities must forward them to the
    # OVNIS anchor so its intake can set a case location_name. The Hub and other
    # targets stay on the base payload shape (no municipalities key).
    item = ClassifiedItem(
        item_id="uapenrich001",
        source_url="https://example.com/uap",
        source_name="Test",
        title="Unidentified craft filmed over Cabo Rojo",
        body_text="Multiple witnesses reported a silent disc off the coast",
        published_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
        labels=[DomainLabel.ANOMALOUS],
        confidence=0.9,
        classifier_reasoning="test",
        municipalities=["Cabo Rojo"],
    )
    payloads = route(item)
    assert payloads["ovnis-pr"]["municipalities"] == ["Cabo Rojo"]
    # The Hub (and any other target) stays on the base contract — no municipalities.
    assert "municipalities" not in payloads[HUB_REPO]


def test_ovnis_municipalities_defaults_empty_when_absent():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "uap001"))
    payloads = route(item)
    assert payloads["ovnis-pr"]["municipalities"] == []


def test_no_duplicate_repos_in_targets():
    # FINANCIAL and POLITICAL both map to moneysweep — should only appear once
    item = ClassifiedItem(
        item_id="dedup001",
        source_url="https://example.com/test",
        source_name="Test",
        title="Test",
        body_text="",
        published_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
        labels=[DomainLabel.FINANCIAL, DomainLabel.POLITICAL],
        confidence=0.9,
        classifier_reasoning="test",
    )
    targets = resolve_targets(item)
    assert targets.count("moneysweep-pr") == 1
