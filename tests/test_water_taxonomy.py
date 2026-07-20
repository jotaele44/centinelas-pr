"""Tests for the water/utility sub-taxonomy and its dispatch to aguayluz."""

from datetime import datetime, timezone

from centinelas.classify.labels import DomainLabel, HUB_REPO
from centinelas.classify.rules import keyword_classify, water_utility_subtypes
from centinelas.models import ClassifiedItem
from centinelas.route.router import build_payload, route


def _classified(title, body="", labels=None):
    return ClassifiedItem(
        item_id="w1", source_url="https://example.pr/x", source_name="Test",
        title=title, body_text=body,
        published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        captured_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        labels=labels or [DomainLabel.ENVIRONMENTAL], confidence=0.8,
    )


def test_pr_water_keywords_route_environmental():
    # PR water/utility terms classify ENVIRONMENTAL -> aguayluz-pr.
    for text in ["PRASA boil water advisory in Ponce",
                 "acueducto main break floods street",
                 "LUMA power outage across the island",
                 "embalse Carraízo reservoir at critical low from sequia"]:
        assert DomainLabel.ENVIRONMENTAL in keyword_classify(text), text


def test_subtypes_detected_and_ordered():
    tags = water_utility_subtypes("PRASA boil water advisory; reservoir low; sewer overflow")
    assert "potable_water" in tags
    assert "boil_water" in tags
    assert "reservoir_drought" in tags
    assert "wastewater" in tags
    # deterministic order follows _WATER_UTILITY_TAGS insertion
    assert tags == sorted(tags, key=["potable_water", "boil_water", "water_quality",
                                     "wastewater", "reservoir_drought", "flood",
                                     "power_grid"].index)


def test_non_water_text_has_no_subtypes():
    assert water_utility_subtypes("The stock market rallied on earnings") == []


def test_accented_spanish_terms_match():
    # PR source text uses accents; matching folds them so accented forms still hit.
    assert DomainLabel.ENVIRONMENTAL in keyword_classify("Apagón general en la isla")
    assert DomainLabel.ENVIRONMENTAL in keyword_classify("sequía severa afecta el embalse")
    assert water_utility_subtypes("Apagón general") == ["power_grid"]
    assert water_utility_subtypes("contaminación del agua") == ["water_quality"]
    assert water_utility_subtypes("inundación repentina") == ["flood"]
    assert "reservoir_drought" in water_utility_subtypes("sequía prolongada")


def test_domain_tags_on_aguayluz_and_hub_payloads():
    item = _classified("PRASA issues boil water advisory", "reservoir levels low")
    payloads = route(item)
    assert "aguayluz-pr" in payloads
    # "PRASA" -> potable_water, "boil water" -> boil_water, "reservoir" -> reservoir_drought
    assert payloads["aguayluz-pr"]["domain_tags"] == [
        "potable_water", "boil_water", "reservoir_drought"]
    # the Hub (always dispatched) also receives the tags for cross-repo correlation
    assert payloads[HUB_REPO]["domain_tags"] == [
        "potable_water", "boil_water", "reservoir_drought"]


def test_non_water_repos_have_no_domain_tags():
    item = _classified("Congress passes budget bill", labels=[DomainLabel.POLITICAL])
    payload = build_payload(item, "moneysweep-pr")
    assert "domain_tags" not in payload
