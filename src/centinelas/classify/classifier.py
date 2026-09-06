"""Deterministic local classifier with an explicit optional hosted adapter."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify

if TYPE_CHECKING:
    from centinelas.models import ClassifiedItem, RawItem

log = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_BACKEND = "local"
_ALLOWED_BACKENDS = frozenset({"local", "anthropic"})

_SYSTEM_PROMPT = """You are an online intelligence classifier. Given a news article title and body, classify it into one or more of these domains:

- ENVIRONMENTAL: climate, weather events, pollution, ecosystems, conservation
- FINANCIAL: markets, economics, banking, cryptocurrency, trade, government contracts, procurement, and contract/grant award announcements (including construction/infrastructure awards)
- POLITICAL: elections, legislation, government, diplomacy, geopolitics
- GEO_GEOLOGY: earthquakes, volcanoes, geology, geography, natural terrain
- ANOMALOUS: UFOs/UAPs, paranormal, unexplained phenomena, cryptids
- MILITARY_AEROSPACE: military, defense, weapons, aviation, space launches, aerospace industry
- SAFETY_COMPLIANCE: workplace safety & health, OSHA/DOL enforcement, inspections, citations, workplace fatalities/amputations, occupational hazards

Return a JSON object with:
- "labels": array of matching domain strings (can be multiple, or ["UNCLASSIFIED"] if none match)
- "confidence": float 0.0-1.0 representing classification certainty
- "reasoning": one sentence explaining the classification

Respond ONLY with valid JSON. No prose outside the JSON."""


def classifier_backend(explicit: str | None = None) -> str:
    """Return the selected backend; unknown values fail rather than drift."""

    raw = explicit if explicit is not None else os.environ.get(
        "CENTINELAS_CLASSIFIER_BACKEND", _DEFAULT_BACKEND
    )
    backend = raw.strip().lower()
    if backend not in _ALLOWED_BACKENDS:
        raise ValueError(
            "CENTINELAS_CLASSIFIER_BACKEND must be one of "
            f"{sorted(_ALLOWED_BACKENDS)}; got {raw!r}"
        )
    return backend


def _local_classify(
    keyword_hits: list[DomainLabel],
) -> tuple[list[DomainLabel], float, str]:
    """Classify without credentials, accounts, network access, or model calls."""

    if len(keyword_hits) >= 2:
        return keyword_hits, 0.85, "Multi-domain deterministic keyword match."
    if keyword_hits:
        return keyword_hits, 0.60, "Single-domain deterministic keyword match."
    return [DomainLabel.UNCLASSIFIED], 0.30, "No deterministic keyword match."


def _anthropic_classify(
    title: str, body: str
) -> tuple[list[DomainLabel], float, str]:
    """Call the optional Anthropic adapter after explicit backend selection."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for backend=anthropic")
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic adapter is not installed; install the hosted-classifier extra"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    text = f"Title: {title}\n\nBody (first 800 chars): {body[:800]}"
    response = client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )

    block = response.content[0]
    raw_text = getattr(block, "text", None)
    if not isinstance(raw_text, str):
        raise ValueError("hosted classifier response did not contain a text block")
    data = json.loads(raw_text.strip())
    if not isinstance(data, dict):
        raise ValueError("hosted classifier response was not a JSON object")

    labels: list[DomainLabel] = []
    raw_labels = data.get("labels", [])
    if not isinstance(raw_labels, list):
        raise ValueError("hosted classifier labels must be an array")
    for label_str in raw_labels:
        try:
            labels.append(DomainLabel(label_str))
        except (TypeError, ValueError):
            log.warning("Unknown label from hosted classifier: %r", label_str)
    if not labels:
        labels = [DomainLabel.UNCLASSIFIED]

    confidence = float(data.get("confidence", 0.5))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("hosted classifier confidence must be in [0, 1]")
    reasoning = str(data.get("reasoning", ""))
    return labels, confidence, reasoning


def classify(
    item: RawItem,
    *,
    backend: str | None = None,
) -> tuple[list[DomainLabel], float, str]:
    """Classify one item with local authority and optional hosted augmentation.

    `local` is the default and never imports a hosted SDK or reads a credential.
    `anthropic` must be selected explicitly. If that optional adapter is absent or
    fails, the result visibly falls back to the deterministic local classification;
    hosted failure is never represented as hosted success.
    """

    text = f"{item.title} {item.body_text}"
    keyword_hits = keyword_classify(text)
    selected = classifier_backend(backend)
    local_labels, local_confidence, local_reasoning = _local_classify(keyword_hits)
    if selected == "local":
        return local_labels, local_confidence, local_reasoning

    try:
        labels, confidence, reasoning = _anthropic_classify(item.title, item.body_text)
    except Exception as exc:
        log.warning("Optional hosted classify failed; using local result: %s", exc)
        return (
            local_labels,
            local_confidence,
            f"{local_reasoning} Hosted adapter unavailable: {type(exc).__name__}: {exc}",
        )

    for keyword_label in keyword_hits:
        if keyword_label not in labels and keyword_label != DomainLabel.UNCLASSIFIED:
            labels.append(keyword_label)
    return labels, confidence, reasoning


def build_classified_item(
    raw: RawItem,
    *,
    backend: str | None = None,
) -> ClassifiedItem:
    """Classify and deterministically enrich a RawItem."""

    from centinelas.classify import enrich
    from centinelas.models import ClassifiedItem

    if backend is None:
        labels, confidence, reasoning = classify(raw)
    else:
        labels, confidence, reasoning = classify(raw, backend=backend)
    enrichment = enrich.extract(raw.title, raw.body_text, raw.source_name)
    return ClassifiedItem(
        **raw.model_dump(),
        labels=labels,
        confidence=confidence,
        classifier_reasoning=reasoning,
        **enrichment,
    )
