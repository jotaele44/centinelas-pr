"""Tests for the keyword classifier (no API calls required)."""

import json
from datetime import datetime, timezone
from pathlib import Path


from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify
from centinelas.models import RawItem


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_items.json").read_text()
)


def _make_raw(item_dict: dict) -> RawItem:
    d = {k: v for k, v in item_dict.items() if k not in ("labels", "confidence", "classifier_reasoning")}
    return RawItem.model_validate(d)


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
    # Should detect at least military+aerospace and environmental
    assert DomainLabel.MILITARY_AEROSPACE in labels
    assert DomainLabel.ENVIRONMENTAL in labels


def test_unclassified_returns_empty_list():
    labels = keyword_classify("Local restaurant reviews and food recommendations")
    assert labels == []


def test_sec_substring_does_not_trigger_financial():
    """Regression: 'sec' inside 'Second'/'secret'/'consecutive' must NOT match FINANCIAL.

    The keyword tier matches on word boundaries, so the short finance token
    'sec' fires only as a standalone word, never as a substring of an unrelated
    word — otherwise health/science articles pollute the MoneySweep stream.
    """
    for text in (
        "Second pregnancy changes the brain in surprising new ways",
        "Alzheimer's tau protein has a surprising secret role in memory",
        "Heavy marijuana smoking and secondhand marijuana smoke",
        "USS Abraham Lincoln passes 200 consecutive days at sea",
    ):
        assert DomainLabel.FINANCIAL not in keyword_classify(text), text


def test_standalone_short_finance_tokens_still_match():
    """Genuine standalone finance tokens must still classify FINANCIAL."""
    assert DomainLabel.FINANCIAL in keyword_classify("The SEC filed charges today")
    assert DomainLabel.FINANCIAL in keyword_classify("Company announces IPO next week")


def test_word_boundary_avoids_political_substring_collision():
    """'war' must not match inside 'warehouse'/'toward'."""
    assert DomainLabel.POLITICAL not in keyword_classify("Warehouse fire spreads toward downtown")


def test_plural_keywords_still_match():
    """Word-boundary matching tolerates a trailing plural 's' for genuine hits."""
    assert DomainLabel.MILITARY_AEROSPACE in keyword_classify("Rockets and missiles launched")
    assert DomainLabel.POLITICAL in keyword_classify("Elections and protests grip the nation")


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
