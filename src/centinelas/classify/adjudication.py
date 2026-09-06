"""Deterministic evidence adjudication for frozen signal-ledger snapshots."""

from __future__ import annotations

import hashlib
import html
import math
import re
from typing import Any

from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_evidence

DOMAIN_LABELS = tuple(label for label in DomainLabel if label != DomainLabel.UNCLASSIFIED)

NLI_LABEL_DESCRIPTIONS: dict[DomainLabel, str] = {
    DomainLabel.ENVIRONMENTAL: "the environment",
    DomainLabel.FINANCIAL: "finance and economics",
    DomainLabel.POLITICAL: "politics and government",
    DomainLabel.GEO_GEOLOGY: "geology and geospatial mapping",
    DomainLabel.ANOMALOUS: "UFOs and unexplained anomalous phenomena",
    DomainLabel.MILITARY_AEROSPACE: "the military and aerospace",
    DomainLabel.SAFETY_COMPLIANCE: "workplace safety and regulatory compliance",
    DomainLabel.UNCLASSIFIED: "another unrelated topic",
}

SOURCE_FAMILY_LABELS: dict[str, DomainLabel] = {
    "anomalous_archive": DomainLabel.ANOMALOUS,
    "anomalous_media": DomainLabel.ANOMALOUS,
    "anomalous_org": DomainLabel.ANOMALOUS,
    "contractor_press": DomainLabel.FINANCIAL,
    "drna_permit": DomainLabel.ENVIRONMENTAL,
    "environmental_media": DomainLabel.ENVIRONMENTAL,
    "expert_legal_policy_media": DomainLabel.POLITICAL,
    "financial_media": DomainLabel.FINANCIAL,
    "geo_geology_agency": DomainLabel.GEO_GEOLOGY,
    "geo_geology_media": DomainLabel.GEO_GEOLOGY,
    "military_aerospace_media": DomainLabel.MILITARY_AEROSPACE,
    "osha_enforcement": DomainLabel.SAFETY_COMPLIANCE,
    "political_media": DomainLabel.POLITICAL,
}

OFFICIAL_SCOPED_SOURCE_FAMILIES = frozenset(
    {"drna_permit", "geo_geology_agency", "osha_enforcement"}
)

SOURCE_CORROBORATING_TERMS: dict[DomainLabel, tuple[str, ...]] = {
    DomainLabel.ENVIRONMENTAL: (
        "clean water", "environmental", "fishing", "pipeline", "spilled fuel",
    ),
    DomainLabel.FINANCIAL: (
        "bank", "business", "company", "economic", "investment", "market",
    ),
    DomainLabel.POLITICAL: (
        "allies", "brics", "china", "denmark", "falklands", "international law",
        "iran", "prabowo", "russia", "somaliland", "strongman", "sudan",
        "territory", "trump", "united states", "venezuela", "washington",
        "weapons embargo",
    ),
    DomainLabel.GEO_GEOLOGY: (
        "atmospheric circulation", "critical zone", "mars", "melting model",
        "rocks", "solar storm", "trace element", "water budget",
    ),
    DomainLabel.ANOMALOUS: (
        "3i/atlas", "comet", "hall of mirrors", "scientists vanish", "von daniken",
        "von däniken",
    ),
    DomainLabel.MILITARY_AEROSPACE: (
        "a320", "abrams", "antenna", "b-52", "body armor", "bomber", "defense",
        "drone", "earth observation", "f-15", "fighter", "fighting vehicle",
        "hydraulic", "marine corps", "mq-9", "nasa", "on-orbit", "propulsion",
        "reaper", "signals intelligence", "smallsat", "space", "usaf", "uss",
        "satellite", "spacecraft", "weapon",
    ),
    DomainLabel.SAFETY_COMPLIANCE: (
        "29 cfr", "aerial lifts", "asbestos", "enforcement guidance", "fall protection",
        "hazard", "hearing loss", "inspection", "protection program", "standard",
    ),
}

# These terms are useful discovery signals but routinely occur outside their
# routed domain.  They need source-family or semantic corroboration.
WEAK_KEYWORDS: dict[DomainLabel, frozenset[str]] = {
    DomainLabel.ANOMALOUS: frozenset({"unidentified"}),
    DomainLabel.FINANCIAL: frozenset({"acquisition", "award", "awarded", "contract", "contractor"}),
    DomainLabel.POLITICAL: frozenset({"president", "regulation", "war"}),
}

MUTABLE_CLASSIFICATION_FIELDS = frozenset(
    {
        "beat",
        "classification_method",
        "classifier_reasoning",
        "confidence_score",
        "labels",
        "signal_type",
    }
)


def signal_text(row: dict[str, Any]) -> str:
    """Return normalized inference text without mutating preserved raw fields."""
    raw = f"{row.get('title') or ''}. {row.get('summary') or ''}"
    without_markup = re.sub(r"<[^>]+>", " ", html.unescape(raw))
    return re.sub(r"\s+", " ", without_markup).strip()


def immutable_projection(row: dict[str, Any]) -> dict[str, Any]:
    """Select fields that an overlay is forbidden to alter."""
    return {key: value for key, value in row.items() if key not in MUTABLE_CLASSIFICATION_FIELDS}


def source_corroboration(text: str, label: DomainLabel) -> list[str]:
    """Return label-specific terms used only to corroborate a source prior."""
    folded = text.casefold()
    return [
        term
        for term in SOURCE_CORROBORATING_TERMS.get(label, ())
        if re.search(rf"\b{re.escape(term.casefold())}s?\b", folded)
    ]


def _nli_support(
    label: DomainLabel,
    scores: dict[DomainLabel, float],
) -> tuple[int, str | None]:
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
    rank = next(index for index, item in enumerate(ranked, start=1) if item[0] == label)
    probability = scores[label]
    margin = probability - ranked[1][1] if rank == 1 else 0.0
    if rank == 1 and probability >= 0.55 and margin >= 0.25:
        return 3, "strong"
    if rank == 1 and probability >= 0.35 and margin >= 0.10:
        return 2, "moderate"
    if rank <= 2 and probability >= 0.15:
        return 1, "weak"
    return 0, None


def adjudicate_signal(
    row: dict[str, Any],
    *,
    source_family: str,
    nli_scores: dict[DomainLabel, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Adjudicate one row and return the derived row plus full decision record."""
    if set(nli_scores) != set(NLI_LABEL_DESCRIPTIONS):
        raise ValueError("NLI score vector does not cover the exact label taxonomy")
    if any(score < 0.0 or score > 1.0 for score in nli_scores.values()):
        raise ValueError("NLI scores must be within [0, 1]")
    if not math.isclose(sum(nli_scores.values()), 1.0, abs_tol=1e-6):
        raise ValueError("NLI score vector must sum to 1")

    text = signal_text(row)
    keyword_matches = keyword_evidence(text)
    source_label = SOURCE_FAMILY_LABELS.get(source_family)
    supports: dict[DomainLabel, list[dict[str, Any]]] = {label: [] for label in DOMAIN_LABELS}

    for label, terms in keyword_matches.items():
        weak = WEAK_KEYWORDS.get(label, frozenset())
        strong_terms = [term for term in terms if term not in weak]
        weak_terms = [term for term in terms if term in weak]
        if strong_terms:
            supports[label].append({"kind": "keyword_strong", "weight": 3, "values": strong_terms})
        if weak_terms:
            supports[label].append({"kind": "keyword_weak", "weight": 1, "values": weak_terms})

    source_terms: list[str] = []
    if source_label is not None:
        source_weight = 3 if source_family in OFFICIAL_SCOPED_SOURCE_FAMILIES else 2
        supports[source_label].append(
            {
                "kind": (
                    "official_scoped_source"
                    if source_weight == 3
                    else "source_family"
                ),
                "weight": source_weight,
                "value": source_family,
            }
        )
        source_terms = source_corroboration(text, source_label)
        if source_terms:
            supports[source_label].append(
                {"kind": "source_content", "weight": 1, "values": source_terms}
            )

    for label in DOMAIN_LABELS:
        weight, strength = _nli_support(label, nli_scores)
        if weight:
            supports[label].append(
                {
                    "kind": "nli",
                    "weight": weight,
                    "strength": strength,
                    "score": nli_scores[label],
                }
            )

    support_totals = {
        label: sum(int(item["weight"]) for item in evidence) for label, evidence in supports.items()
    }
    accepted: list[DomainLabel] = [
        label
        for label in DOMAIN_LABELS
        if support_totals[label] >= 3
        and any(item["kind"] != "nli" for item in supports[label])
    ]
    review_candidates: list[DomainLabel] = [
        label
        for label in DOMAIN_LABELS
        if support_totals[label] == 2
        and any(item["kind"] != "nli" for item in supports[label])
    ]
    ranked_nli = sorted(nli_scores.items(), key=lambda item: (-item[1], item[0].value))

    if accepted:
        final_labels = accepted
        state = "TERMINAL"
        method = "model_assisted_adjudication"
    elif (
        source_family not in OFFICIAL_SCOPED_SOURCE_FAMILIES
        and not keyword_matches
        and not source_terms
        and ranked_nli[0][0] == DomainLabel.UNCLASSIFIED
        and ranked_nli[0][1] >= 0.35
        and ranked_nli[0][1] - ranked_nli[1][1] >= 0.10
    ):
        final_labels = [DomainLabel.UNCLASSIFIED]
        state = "TERMINAL"
        method = "model_assisted_adjudication"
    elif review_candidates:
        final_labels = [DomainLabel.UNCLASSIFIED]
        state = "UNRESOLVED"
        method = "model_assisted_unresolved"
    elif (
        ranked_nli[0][0] == DomainLabel.UNCLASSIFIED
        and ranked_nli[0][1] >= 0.35
        and ranked_nli[0][1] - ranked_nli[1][1] >= 0.10
    ) or (source_label is None and not keyword_matches):
        final_labels = [DomainLabel.UNCLASSIFIED]
        state = "TERMINAL"
        method = "model_assisted_adjudication"
    else:
        final_labels = [DomainLabel.UNCLASSIFIED]
        state = "UNRESOLVED"
        method = "model_assisted_unresolved"

    if state == "TERMINAL" and final_labels != [DomainLabel.UNCLASSIFIED]:
        primary_support = max(support_totals[label] for label in final_labels)
        confidence = min(0.99, 0.55 + 0.08 * primary_support)
        summaries = []
        for label in final_labels:
            kinds = ", ".join(item["kind"] for item in supports[label])
            summaries.append(f"{label.value}={support_totals[label]} via {kinds}")
        reasoning = "Evidence adjudication accepted " + "; ".join(summaries) + "."
    elif state == "TERMINAL":
        confidence = max(0.55, nli_scores[DomainLabel.UNCLASSIFIED])
        reasoning = "Evidence adjudication found no sufficiently supported domain label."
    else:
        confidence = 0.0
        candidates = ", ".join(label.value for label in review_candidates) or "none"
        reasoning = (
            f"UNRESOLVED: evidence did not reach the acceptance threshold; candidates={candidates}."
        )

    derived = dict(row)
    derived.update(
        {
            "labels": [label.value for label in final_labels],
            "confidence_score": round(confidence * 100, 1),
            "classification_method": method,
            "classifier_reasoning": reasoning,
            "beat": final_labels[0].value.lower(),
            "signal_type": f"{final_labels[0].value.lower()}_signal",
        }
    )
    decision = {
        "signal_id": row.get("signal_id"),
        "state": state,
        "source_family": source_family,
        "source_family_label": source_label.value if source_label else None,
        "original": {
            "labels": row.get("labels"),
            "classification_method": row.get("classification_method"),
            "confidence_score": row.get("confidence_score"),
        },
        "keyword_evidence": {label.value: terms for label, terms in keyword_matches.items()},
        "nli_scores": {label.value: nli_scores[label] for label in NLI_LABEL_DESCRIPTIONS},
        "support": {
            label.value: {
                "total": support_totals[label],
                "evidence": supports[label],
            }
            for label in DOMAIN_LABELS
        },
        "final": {
            "labels": derived["labels"],
            "classification_method": method,
            "confidence_score": derived["confidence_score"],
            "beat": derived["beat"],
            "signal_type": derived["signal_type"],
            "classifier_reasoning": reasoning,
        },
    }
    return derived, decision


def apply_review_adjudication(
    row: dict[str, Any],
    derived: dict[str, Any],
    decision: dict[str, Any],
    review: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply an exact, provenance-bound review decision to an unresolved row."""
    if decision.get("state") != "UNRESOLVED":
        raise ValueError("review decisions may only target unresolved rows")
    if review.get("signal_id") != row.get("signal_id"):
        raise ValueError("review signal ID does not match the source row")
    if review.get("source_id") != row.get("source_id"):
        raise ValueError("review source ID does not match the source row")
    title = str(row.get("title") or "")
    if review.get("title_sha256") != hashlib.sha256(title.encode("utf-8")).hexdigest():
        raise ValueError("review title hash does not match the source row")
    if review.get("classification_basis") != "INFERENCE":
        raise ValueError("review classification_basis must be INFERENCE")
    rationale = review.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("review rationale is required")
    raw_labels = review.get("labels")
    if not isinstance(raw_labels, list) or not raw_labels:
        raise ValueError("review labels must be a nonempty array")
    try:
        labels = [DomainLabel(value) for value in raw_labels]
    except ValueError as exc:
        raise ValueError("review contains an unknown label") from exc
    if len(labels) != len(set(labels)):
        raise ValueError("review labels contain duplicates")
    if DomainLabel.UNCLASSIFIED in labels and labels != [DomainLabel.UNCLASSIFIED]:
        raise ValueError("UNCLASSIFIED cannot be combined with a domain label")
    canonical_labels = [label for label in DomainLabel if label in labels]
    if labels != canonical_labels:
        raise ValueError("review labels are not in canonical taxonomy order")
    confidence = review.get("confidence_score")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0.0 <= float(confidence) <= 100.0
    ):
        raise ValueError("review confidence_score must be within [0, 100]")

    updated = dict(derived)
    updated.update(
        {
            "labels": [label.value for label in labels],
            "confidence_score": float(confidence),
            "classification_method": "review_adjudication",
            "classifier_reasoning": f"AI review inference: {rationale.strip()}",
            "beat": labels[0].value.lower(),
            "signal_type": f"{labels[0].value.lower()}_signal",
        }
    )
    reviewed_decision = dict(decision)
    reviewed_decision["state"] = "TERMINAL"
    reviewed_decision["review_adjudication"] = review
    reviewed_decision["final"] = {
        field: updated[field]
        for field in MUTABLE_CLASSIFICATION_FIELDS
    }
    return updated, reviewed_decision
