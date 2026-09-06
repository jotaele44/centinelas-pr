"""Tests for deterministic local classification and the optional hosted adapter."""

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from centinelas.classify import classifier
from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify
from centinelas.models import RawItem

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_items.json").read_text()
)


def _make_raw(item_dict: dict) -> RawItem:
    excluded = {"labels", "confidence", "classifier_reasoning"}
    return RawItem.model_validate({key: value for key, value in item_dict.items() if key not in excluded})


def test_military_aerospace_keywords():
    item = next(i for i in FIXTURES if i["item_id"] == "aero001")
    labels = keyword_classify(f"{item['title']} {item['body_text']}")
    assert DomainLabel.MILITARY_AEROSPACE in labels


def test_environmental_keywords():
    item = next(i for i in FIXTURES if i["item_id"] == "env001")
    labels = keyword_classify(f"{item['title']} {item['body_text']}")
    assert DomainLabel.ENVIRONMENTAL in labels


def test_geo_geology_keywords():
    item = next(i for i in FIXTURES if i["item_id"] == "geo001")
    labels = keyword_classify(f"{item['title']} {item['body_text']}")
    assert DomainLabel.GEO_GEOLOGY in labels


def test_financial_keywords():
    item = next(i for i in FIXTURES if i["item_id"] == "fin001")
    labels = keyword_classify(f"{item['title']} {item['body_text']}")
    assert DomainLabel.FINANCIAL in labels


def test_political_keywords():
    item = next(i for i in FIXTURES if i["item_id"] == "pol001")
    labels = keyword_classify(f"{item['title']} {item['body_text']}")
    assert DomainLabel.POLITICAL in labels


def test_anomalous_keywords():
    item = next(i for i in FIXTURES if i["item_id"] == "uap001")
    labels = keyword_classify(f"{item['title']} {item['body_text']}")
    assert DomainLabel.ANOMALOUS in labels


def test_multi_label_detection():
    item = next(i for i in FIXTURES if i["item_id"] == "multi001")
    labels = keyword_classify(f"{item['title']} {item['body_text']}")
    assert DomainLabel.MILITARY_AEROSPACE in labels
    assert DomainLabel.ENVIRONMENTAL in labels


def test_unclassified_returns_empty_list():
    labels = keyword_classify("Local restaurant reviews and food recommendations")
    assert labels == []


def test_sec_substring_does_not_trigger_financial():
    """The short token `sec` must not match inside unrelated words."""

    for text in (
        "Second pregnancy changes the brain in surprising new ways",
        "Alzheimer's tau protein has a surprising secret role in memory",
        "Heavy marijuana smoking and secondhand marijuana smoke",
        "USS Abraham Lincoln passes 200 consecutive days at sea",
    ):
        assert DomainLabel.FINANCIAL not in keyword_classify(text), text


def test_standalone_short_finance_tokens_still_match():
    assert DomainLabel.FINANCIAL in keyword_classify("The SEC filed charges today")
    assert DomainLabel.FINANCIAL in keyword_classify("Company announces IPO next week")


def test_word_boundary_avoids_political_substring_collision():
    assert DomainLabel.POLITICAL not in keyword_classify("Warehouse fire spreads toward downtown")


def test_plural_keywords_still_match():
    assert DomainLabel.MILITARY_AEROSPACE in keyword_classify("Rockets and missiles launched")
    assert DomainLabel.POLITICAL in keyword_classify("Elections and protests grip the nation")


def test_procurement_award_keywords_route_financial():
    assert DomainLabel.FINANCIAL in keyword_classify("company awarded a construction contract")
    assert DomainLabel.FINANCIAL in keyword_classify("aviso de adjudicacion de subasta")
    assert DomainLabel.FINANCIAL in keyword_classify("licitacion para obras publicas")


def test_default_backend_is_local_and_never_calls_hosted_adapter(monkeypatch):
    item = _make_raw(next(i for i in FIXTURES if i["item_id"] == "fin001"))
    monkeypatch.delenv("CENTINELAS_CLASSIFIER_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("hosted adapter must not run in the default local path")

    monkeypatch.setattr(classifier, "_anthropic_classify", forbidden)
    labels, confidence, reasoning = classifier.classify(item)

    assert labels == [DomainLabel.FINANCIAL]
    assert confidence == 0.60
    assert reasoning == "Single-domain deterministic keyword match."


def test_hosted_backend_is_explicit_and_merges_local_evidence(monkeypatch):
    item = _make_raw(next(i for i in FIXTURES if i["item_id"] == "fin001"))
    monkeypatch.setattr(
        classifier,
        "_anthropic_classify",
        lambda *_args: ([DomainLabel.POLITICAL], 0.91, "hosted fixture"),
    )

    labels, confidence, reasoning = classifier.classify(item, backend="anthropic")

    assert labels == [DomainLabel.POLITICAL, DomainLabel.FINANCIAL]
    assert confidence == 0.91
    assert reasoning == "hosted fixture"


def test_hosted_failure_is_visible_local_fallback(monkeypatch):
    item = _make_raw(next(i for i in FIXTURES if i["item_id"] == "fin001"))

    def fail(*_args):
        raise RuntimeError("adapter unavailable")

    monkeypatch.setattr(classifier, "_anthropic_classify", fail)
    labels, confidence, reasoning = classifier.classify(item, backend="anthropic")

    assert labels == [DomainLabel.FINANCIAL]
    assert confidence == 0.60
    assert "Hosted adapter unavailable: RuntimeError: adapter unavailable" in reasoning


def test_unknown_classifier_backend_fails_closed(monkeypatch):
    monkeypatch.setenv("CENTINELAS_CLASSIFIER_BACKEND", "auto-magic")
    with pytest.raises(ValueError, match="must be one of"):
        classifier.classifier_backend()


def test_anthropic_is_not_a_top_level_import():
    source_path = Path(classifier.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    top_level_imports = {
        alias.name.split(".", 1)[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "anthropic" not in top_level_imports


def test_item_id_is_deterministic():
    url = "https://example.com/article"
    dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
    id1 = RawItem.make_id(url, dt)
    id2 = RawItem.make_id(url, dt)
    assert id1 == id2
    assert len(id1) == 16


def test_item_id_differs_by_date():
    url = "https://example.com/article"
    dt1 = datetime(2026, 7, 1, tzinfo=timezone.utc)
    dt2 = datetime(2026, 7, 2, tzinfo=timezone.utc)
    assert RawItem.make_id(url, dt1) != RawItem.make_id(url, dt2)
