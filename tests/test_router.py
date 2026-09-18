"""Tests for label routing, target payloads, and replay-stable identity inputs."""

import json
from datetime import datetime, timezone
from pathlib import Path

from centinelas.classify.labels import HUB_REPO, DomainLabel
from centinelas.models import ClassifiedItem
from centinelas.route.router import build_payload, resolve_targets, route

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_items.json").read_text()
)


def _make_classified(item_dict: dict) -> ClassifiedItem:
    return ClassifiedItem.model_validate(item_dict)


def test_military_aerospace_routes_to_skywatcher():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "aero001"))
    assert "skywatcher-pr" in resolve_targets(item)


def test_environmental_routes_to_aguayluz():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "env001"))
    assert "aguayluz-pr" in resolve_targets(item)


def test_geo_routes_to_spiderweb():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "geo001"))
    assert "spiderweb-pr" in resolve_targets(item)


def test_financial_routes_to_moneysweep():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "fin001"))
    assert "moneysweep-pr" in resolve_targets(item)


def test_political_routes_to_moneysweep():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "pol001"))
    assert "moneysweep-pr" in resolve_targets(item)


def test_anomalous_routes_to_ovnis():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "uap001"))
    assert "ovnis-pr" in resolve_targets(item)


def test_multi_label_routes_to_multiple_repos():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "multi001"))
    targets = resolve_targets(item)
    assert "skywatcher-pr" in targets
    assert "aguayluz-pr" in targets


def test_thehub_always_receives_every_item():
    for fixture in FIXTURES:
        item = _make_classified(fixture)
        assert HUB_REPO in route(item), f"thehub missing for item {fixture['item_id']}"


def test_unclassified_only_routes_to_thehub():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "unc001"))
    assert list(route(item)) == [HUB_REPO]


def test_payload_contains_required_fields():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "aero001"))
    for repo, payload in route(item).items():
        for field in (
            "item_id",
            "source_url",
            "title",
            "labels",
            "captured_at",
            "routed_to",
            "routed_at",
        ):
            assert field in payload, f"Missing field {field!r} in payload for {repo}"


def test_payload_is_byte_stable_across_replays():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "fin001"))
    first = json.dumps(route(item), sort_keys=True, separators=(",", ":"))
    second = json.dumps(route(item), sort_keys=True, separators=(",", ":"))
    assert first == second


def test_routed_at_binds_to_capture_observation_in_utc():
    item = ClassifiedItem(
        item_id="time001",
        source_url="https://example.com/time001",
        source_name="Test",
        title="Financial filing",
        body_text="The SEC filed charges.",
        published_at=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc),
        captured_at=datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc),
        labels=[DomainLabel.FINANCIAL],
        confidence=0.9,
        classifier_reasoning="fixture",
    )
    payload = build_payload(item, "moneysweep-pr")
    assert payload["routed_at"] == "2026-01-02T09:30:00+00:00"


def test_moneysweep_payload_carries_finance_enrichment():
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
    moneysweep = payloads["moneysweep-pr"]
    assert moneysweep["municipalities"] == ["Ponce"]
    assert moneysweep["recipients"] == ["Acme Construction Corp"]
    assert moneysweep["agencies"] == ["Autoridad de Acueductos y Alcantarillados"]
    assert moneysweep["estimated_value"] == 1500000.0
    assert moneysweep["signal_stage"] == "rfp_open"
    assert moneysweep["beat"] == "contracts"
    assert "estimated_value" not in payloads[HUB_REPO]
    assert "recipients" not in payloads[HUB_REPO]
    assert "estimated_value" not in payloads["spiderweb-pr"]


def test_finance_enrichment_defaults_empty_when_absent():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "fin001"))
    moneysweep = route(item)["moneysweep-pr"]
    assert moneysweep["municipalities"] == []
    assert moneysweep["recipients"] == []
    assert moneysweep["agencies"] == []
    assert moneysweep["estimated_value"] is None


def test_ovnis_payload_carries_municipalities():
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
    assert "municipalities" not in payloads[HUB_REPO]


def test_ovnis_municipalities_defaults_empty_when_absent():
    item = _make_classified(next(i for i in FIXTURES if i["item_id"] == "uap001"))
    assert route(item)["ovnis-pr"]["municipalities"] == []


def test_no_duplicate_repos_in_targets():
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
    assert resolve_targets(item).count("moneysweep-pr") == 1
