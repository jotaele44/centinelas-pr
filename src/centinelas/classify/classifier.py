"""Multi-label classifier: keyword fast-path → Claude Haiku for ambiguous cases."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import anthropic

from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify

if TYPE_CHECKING:
    from centinelas.models import ClassifiedItem, RawItem

log = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """You are an online intelligence classifier. Given a news article title and body, classify it into one or more of these domains:

- ENVIRONMENTAL: climate, weather events, pollution, ecosystems, conservation
- FINANCIAL: markets, economics, banking, cryptocurrency, trade, government contracts, procurement, and contract/grant award announcements (including construction/infrastructure awards)
- POLITICAL: elections, legislation, government, diplomacy, geopolitics
- GEO_GEOLOGY: earthquakes, volcanoes, geology, geography, natural terrain
- ANOMALOUS: UFOs/UAPs, paranormal, unexplained phenomena, cryptids
- MILITARY_AEROSPACE: military, defense, weapons, aviation, space launches, aerospace industry

Return a JSON object with:
- "labels": array of matching domain strings (can be multiple, or ["UNCLASSIFIED"] if none match)
- "confidence": float 0.0-1.0 representing classification certainty
- "reasoning": one sentence explaining the classification

Respond ONLY with valid JSON. No prose outside the JSON."""


def _llm_classify(title: str, body: str) -> tuple[list[DomainLabel], float, str]:
    """Call Claude Haiku for multi-label classification. Returns (labels, confidence, reasoning)."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    text = f"Title: {title}\n\nBody (first 800 chars): {body[:800]}"

    response = client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )

    raw = response.content[0].text.strip()
    data = json.loads(raw)

    labels: list[DomainLabel] = []
    for label_str in data.get("labels", []):
        try:
            labels.append(DomainLabel(label_str))
        except ValueError:
            log.warning("Unknown label from LLM: %s", label_str)

    if not labels:
        labels = [DomainLabel.UNCLASSIFIED]

    confidence = float(data.get("confidence", 0.5))
    reasoning = str(data.get("reasoning", ""))
    return labels, confidence, reasoning


def classify(item: "RawItem") -> tuple[list[DomainLabel], float, str]:
    """
    Classify a RawItem into domain labels.

    Fast path: keyword rules. If 2+ strong hits, return immediately.
    Slow path: Claude Haiku for ambiguous/unmatched items.
    Falls back to keyword rules if API call fails.

    Returns (labels, confidence, reasoning).
    """
    text = f"{item.title} {item.body_text}"
    keyword_hits = keyword_classify(text)

    # High-confidence keyword path: multiple distinct labels or single clear hit
    if len(keyword_hits) >= 2:
        return keyword_hits, 0.85, "Multi-domain keyword match — skipped LLM."

    try:
        labels, confidence, reasoning = _llm_classify(item.title, item.body_text)

        # Merge keyword hits not already in LLM result
        for kw_label in keyword_hits:
            if kw_label not in labels and kw_label != DomainLabel.UNCLASSIFIED:
                labels.append(kw_label)

        return labels, confidence, reasoning

    except Exception as exc:
        log.warning("LLM classify failed (%s), falling back to keyword rules.", exc)
        if keyword_hits:
            return keyword_hits, 0.6, f"Keyword fallback (LLM unavailable: {exc})"
        return [DomainLabel.UNCLASSIFIED], 0.3, f"Unclassified — LLM unavailable: {exc}"


def build_classified_item(raw: "RawItem") -> "ClassifiedItem":
    """Classify + enrich a RawItem into a fully-populated ClassifiedItem.

    Single construction site shared by the CLI ``classify`` and ``run`` commands:
    runs domain classification and the deterministic finance/procurement
    enrichment (:mod:`centinelas.classify.enrich`) so the pre-officialization
    fields (estimated_value/agencies/signal_stage/beat) travel with the item to
    the MoneySweep anchor.
    """
    from centinelas.classify import enrich
    from centinelas.models import ClassifiedItem

    labels, confidence, reasoning = classify(raw)
    enrichment = enrich.extract(raw.title, raw.body_text, raw.source_name)
    return ClassifiedItem(
        **raw.model_dump(),
        labels=labels,
        confidence=confidence,
        classifier_reasoning=reasoning,
        **enrichment,
    )
