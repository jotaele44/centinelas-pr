from __future__ import annotations

from centinelas.classify.adjudication import adjudicate_signal, immutable_projection
from centinelas.classify.labels import DomainLabel


def _scores(**overrides: float) -> dict[DomainLabel, float]:
    explicit = {DomainLabel(name): value for name, value in overrides.items()}
    explicit.setdefault(DomainLabel.UNCLASSIFIED, 0.30)
    remaining = [label for label in DomainLabel if label not in explicit]
    remainder = 1.0 - sum(explicit.values())
    assert remainder >= 0
    fill = remainder / len(remaining) if remaining else 0.0
    return {label: explicit.get(label, fill) for label in DomainLabel}


def _row(title: str, *, labels: list[str] | None = None) -> dict:
    return {
        "signal_id": "CENT-SIG-test",
        "matter_id": "CENT-MAT-test",
        "title": title,
        "summary": "",
        "source_id": "CENT-SRC-test",
        "captured_at": "2026-09-05T20:00:00+00:00",
        "is_synthetic": False,
        "labels": labels or ["UNCLASSIFIED"],
        "beat": "unclassified",
        "signal_type": "unclassified_signal",
        "confidence_score": 30.0,
        "classification_method": "unclassified_fallback",
        "classifier_reasoning": "fallback",
    }


def test_domain_source_and_content_evidence_resolve_explicit_drone():
    row = _row("China's WZ-X stealth aircraft confirms a new wing design")
    derived, decision = adjudicate_signal(
        row,
        source_family="military_aerospace_media",
        nli_scores=_scores(ENVIRONMENTAL=0.40, MILITARY_AEROSPACE=0.10),
    )

    assert decision["state"] == "TERMINAL"
    assert derived["labels"] == ["MILITARY_AEROSPACE"]
    assert decision["support"]["MILITARY_AEROSPACE"]["total"] >= 5
    assert immutable_projection(derived) == immutable_projection(row)


def test_weak_award_keyword_does_not_override_environmental_evidence():
    row = _row("The Best Environmental Photography Award of the Year")
    derived, decision = adjudicate_signal(
        row,
        source_family="environmental_media",
        nli_scores=_scores(ENVIRONMENTAL=0.74, FINANCIAL=0.06, UNCLASSIFIED=0.08),
    )

    assert decision["state"] == "TERMINAL"
    assert derived["labels"] == ["ENVIRONMENTAL"]
    assert decision["support"]["FINANCIAL"]["total"] == 1


def test_corporate_president_does_not_create_political_label():
    row = _row("Airline appoints a senior vice-president to lead its aircraft unit")
    derived, decision = adjudicate_signal(
        row,
        source_family="military_aerospace_media",
        nli_scores=_scores(UNCLASSIFIED=0.60, POLITICAL=0.02),
    )

    assert decision["state"] == "TERMINAL"
    assert derived["labels"] == ["MILITARY_AEROSPACE"]
    assert decision["support"]["POLITICAL"]["total"] == 1


def test_territorial_acquisition_routes_to_policy_not_finance():
    row = _row("Can the Trump administration make a territorial acquisition?")
    derived, decision = adjudicate_signal(
        row,
        source_family="expert_legal_policy_media",
        nli_scores=_scores(UNCLASSIFIED=0.30, POLITICAL=0.12, FINANCIAL=0.08),
    )

    assert decision["state"] == "TERMINAL"
    assert derived["labels"] == ["POLITICAL"]
    assert decision["support"]["FINANCIAL"]["total"] == 1


def test_source_only_candidate_fails_closed_for_review():
    row = _row("A short item with no topical evidence")
    derived, decision = adjudicate_signal(
        row,
        source_family="environmental_media",
        nli_scores=_scores(UNCLASSIFIED=0.30),
    )

    assert decision["state"] == "UNRESOLVED"
    assert derived["classification_method"] == "model_assisted_unresolved"
    assert derived["confidence_score"] == 0.0


def test_generic_source_with_strong_unclassified_score_is_terminal():
    row = _row("Local restaurant publishes its weekend menu")
    derived, decision = adjudicate_signal(
        row,
        source_family="news_wire",
        nli_scores=_scores(UNCLASSIFIED=0.70, ENVIRONMENTAL=0.10),
    )

    assert decision["state"] == "TERMINAL"
    assert derived["labels"] == ["UNCLASSIFIED"]
    assert derived["classification_method"] == "model_assisted_adjudication"
