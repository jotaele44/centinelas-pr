"""Tests for the keyword classifier (no API calls required)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
