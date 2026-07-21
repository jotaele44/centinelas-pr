"""Tests for the SAFETY_COMPLIANCE (OSHA / workplace-safety) domain.

Covers the keyword fast-path classification, the label→repo routing to
aguayluz-pr (its INDUSTRIAL alert module), and life-safety urgency flagging
for workplace fatalities.
"""

from datetime import datetime, timezone

from centinelas.classify.labels import DomainLabel, LABEL_TO_REPO
from centinelas.classify.rules import is_critical_signal, keyword_classify
from centinelas.models import ClassifiedItem
from centinelas.route.router import resolve_targets


def test_osha_keywords_classify_safety_compliance():
    text = "OSHA cites Puerto Rico manufacturer; willful violation after workplace fatality"
    assert DomainLabel.SAFETY_COMPLIANCE in keyword_classify(text)


def test_spanish_occupational_safety_classifies():
    text = "Seguridad ocupacional: inspeccion tras accidente laboral en planta de Bayamon"
    assert DomainLabel.SAFETY_COMPLIANCE in keyword_classify(text)


def test_safety_compliance_routes_to_aguayluz():
    assert LABEL_TO_REPO[DomainLabel.SAFETY_COMPLIANCE] == "aguayluz-pr"
    item = ClassifiedItem(
        item_id="osha001",
        source_url="https://www.osha.gov/news/newsreleases/example",
        source_name="OSHA News Releases",
        title="OSHA opens inspection after amputation at PR facility",
        body_text="",
        published_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
        labels=[DomainLabel.SAFETY_COMPLIANCE],
        confidence=0.9,
        classifier_reasoning="test",
    )
    assert "aguayluz-pr" in resolve_targets(item)


def test_workplace_fatality_is_critical():
    assert is_critical_signal("Worker death prompts OSHA imminent danger order") is True


def test_routine_directive_not_critical():
    assert is_critical_signal("OSHA issues new directive on standard interpretations") is False
