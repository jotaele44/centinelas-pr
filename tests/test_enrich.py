"""Tests for deterministic finance/procurement enrichment (no API calls)."""

from datetime import datetime, timezone

import pytest

from centinelas.classify import enrich
from centinelas.classify.classifier import build_classified_item
from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify
from centinelas.models import RawItem
from centinelas.route.router import resolve_targets, route

# The real award announcement this feature targets.
CAMP_SANTIAGO_TITLE = "Del Valle Group announces the award of a project of $299.7 millions"
CAMP_SANTIAGO_BODY = (
    "4Contractors JV, a joint venture of Del Valle Group, RB Construction and DDD "
    "Group, was awarded a $299.7 million contract by the Puerto Rico National Guard "
    "to build the Joint Training Center at Camp Santiago in Salinas."
)


# ── Amount extraction ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text, expected",
    [
        ("a project of $299.7 million", 299_700_000.0),
        ("award of a project of $299.7 millions", 299_700_000.0),   # plural form
        ("proyecto de 299.7 millones", 299_700_000.0),              # PR Spanish
        ("un contrato de 1.2 mil millones", 1_200_000_000.0),       # Spanish billion
        ("a $1.2 billion deal", 1_200_000_000.0),
        ("valorado en $299,700,000", 299_700_000.0),                # plain currency
        ("$299700000 total", 299_700_000.0),                        # bare digits
    ],
)
def test_extract_estimated_value(text, expected):
    assert enrich.extract_estimated_value(text) == expected


def test_extract_estimated_value_picks_headline_max():
    text = "a $2.5 million subcontract inside the $299.7 million award"
    assert enrich.extract_estimated_value(text) == 299_700_000.0


def test_extract_estimated_value_none_without_amount():
    assert enrich.extract_estimated_value("millions of people attended the parade") is None
    assert enrich.extract_estimated_value("no money mentioned here") is None


# ── Agencies / stage / beat ───────────────────────────────────────────────────
def test_extract_agencies_national_guard():
    assert "Puerto Rico National Guard" in enrich.extract_agencies(CAMP_SANTIAGO_BODY)


def test_extract_agencies_spanish_and_empty():
    assert "Puerto Rico National Guard" in enrich.extract_agencies("la Guardia Nacional adjudico")
    assert enrich.extract_agencies("a story with no agency") == []


def test_signal_stage_award_vs_rfp_vs_none():
    assert enrich.extract_signal_stage(CAMP_SANTIAGO_BODY) == "award_announced"
    assert enrich.extract_signal_stage("adjudicacion del contrato") == "award_announced"
    assert enrich.extract_signal_stage("licitacion abierta / request for proposal") == "rfp_open"
    assert enrich.extract_signal_stage("a weather story") is None


def test_beat_procurement():
    assert enrich.extract_beat(CAMP_SANTIAGO_BODY) == "procurement"
    assert enrich.extract_beat("a hurricane update") is None


def test_extract_bundle_shape():
    out = enrich.extract(CAMP_SANTIAGO_TITLE, CAMP_SANTIAGO_BODY)
    assert out == {
        "municipalities": [],
        "agencies": ["Puerto Rico National Guard"],
        "estimated_value": 299_700_000.0,
        "signal_stage": "award_announced",
        "beat": "procurement",
    }


# ── Classification routing ────────────────────────────────────────────────────
def test_award_announcement_classifies_financial():
    labels = keyword_classify(f"{CAMP_SANTIAGO_TITLE} {CAMP_SANTIAGO_BODY}")
    assert DomainLabel.FINANCIAL in labels


def test_award_announcement_routes_to_moneysweep(monkeypatch):
    # Pin classification to the deterministic keyword result so the test never
    # touches the LLM path (the single FINANCIAL keyword hit would otherwise fall
    # through to Claude). Enrichment + routing are what we're asserting here.
    monkeypatch.setattr(
        "centinelas.classify.classifier.classify",
        lambda raw: ([DomainLabel.FINANCIAL], 0.9, "keyword"),
    )
    item = build_classified_item(
        RawItem(
            item_id="campsantiago001",
            source_url="https://delvallegroup.net/del-valle-group-announces-the-award-of-a-project-of-299-7-millions/",
            source_name="Del Valle Group",
            title=CAMP_SANTIAGO_TITLE,
            body_text=CAMP_SANTIAGO_BODY,
            published_at=datetime.now(timezone.utc),
            captured_at=datetime.now(timezone.utc),
            evidence_tier="T2",
        )
    )
    # Keyword fast-path yields FINANCIAL deterministically (no LLM needed).
    assert DomainLabel.FINANCIAL in item.labels
    assert item.estimated_value == 299_700_000.0
    assert item.agencies == ["Puerto Rico National Guard"]

    targets = resolve_targets(item)
    assert "moneysweep-pr" in targets

    ms = route(item)["moneysweep-pr"]
    assert ms["estimated_value"] == 299_700_000.0
    assert ms["agencies"] == ["Puerto Rico National Guard"]
    assert ms["signal_stage"] == "award_announced"
