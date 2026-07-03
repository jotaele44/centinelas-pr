"""Tests for the router — label→repo mapping and thehub guarantee."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
