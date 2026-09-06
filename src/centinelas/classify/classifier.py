"""Deterministic local classification with an explicit optional hosted adapter.

The certified-core candidate never imports or calls a hosted model.  Operators may
opt into Anthropic with ``CENTINELAS_CLASSIFIER_MODE=anthropic`` after installing
the ``hosted-classifier`` extra.  Hosted output is therefore an optional profile,
not a secret or service requirement of the local pipeline.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from typing import TYPE_CHECKING, Any

from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify

if TYPE_CHECKING:
    from centinelas.models import ClassifiedItem, RawItem

log = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_LOCAL_MODE = "local"
_HOSTED_MODE = "anthropic"
_ALLOWED_MODES = frozenset({_LOCAL_MODE, _HOSTED_MODE})
_ALLOWED_HOSTED_FAILURE_POLICIES = frozenset({"local_fallback", "fail_closed"})

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


class HostedClassifierUnavailable(RuntimeError):
    """Raised when the explicitly requested hosted adapter cannot run."""


def classifier_mode() -> str:
    """Return the explicit classifier mode; unknown values fail closed."""

    mode = os.environ.get("CENTINELAS_CLASSIFIER_MODE", _LOCAL_MODE).strip().lower()
    if mode not in _ALLOWED_MODES:
        raise ValueError(
            "CENTINELAS_CLASSIFIER_MODE must be one of "
            f"{sorted(_ALLOWED_MODES)}, got {mode!r}"
        )
    return mode


def _hosted_failure_policy() -> str:
    policy = os.environ.get(
        "CENTINELAS_HOSTED_CLASSIFIER_FAILURE_POLICY", "local_fallback"
    ).strip().lower()
    if policy not in _ALLOWED_HOSTED_FAILURE_POLICIES:
        raise ValueError(
            "CENTINELAS_HOSTED_CLASSIFIER_FAILURE_POLICY must be one of "
            f"{sorted(_ALLOWED_HOSTED_FAILURE_POLICIES)}, got {policy!r}"
        )
    return policy


def _local_classify(item: RawItem) -> tuple[list[DomainLabel], float, str]:
    """Classify from tracked local rules only, with no network or secret access."""

    hits = keyword_classify(f"{item.title} {item.body_text}")
    if len(hits) >= 2:
        return hits, 0.85, "LOCAL_RULES: multi-domain keyword match."
    if len(hits) == 1:
        return hits, 0.70, "LOCAL_RULES: single-domain keyword match."
    return [DomainLabel.UNCLASSIFIED], 0.30, "LOCAL_RULES: no domain rule matched."


def _response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if not isinstance(content, list) or not content:
        raise HostedClassifierUnavailable("hosted response has no content blocks")
    text = getattr(content[0], "text", None)
    if not isinstance(text, str) or not text.strip():
        raise HostedClassifierUnavailable("hosted response has no text block")
    return text.strip()


def _validate_hosted_result(value: object) -> tuple[list[DomainLabel], float, str]:
    if not isinstance(value, dict):
        raise HostedClassifierUnavailable("hosted result must be a JSON object")

    raw_labels = value.get("labels")
    if not isinstance(raw_labels, list) or not all(
        isinstance(label, str) for label in raw_labels
    ):
        raise HostedClassifierUnavailable("hosted labels must be an array of strings")

    labels: list[DomainLabel] = []
    for raw_label in raw_labels:
        try:
            label = DomainLabel(raw_label)
        except ValueError:
            log.warning("Ignoring unknown hosted classifier label: %s", raw_label)
            continue
        if label not in labels:
            labels.append(label)
    if not labels:
        labels = [DomainLabel.UNCLASSIFIED]

    raw_confidence = value.get("confidence")
    if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
        raise HostedClassifierUnavailable("hosted confidence must be numeric")
    confidence = float(raw_confidence)
    if not 0.0 <= confidence <= 1.0:
        raise HostedClassifierUnavailable("hosted confidence must be in [0, 1]")

    reasoning = value.get("reasoning")
    if not isinstance(reasoning, str):
        raise HostedClassifierUnavailable("hosted reasoning must be a string")
    return labels, confidence, reasoning.strip()


def _llm_classify(title: str, body: str) -> tuple[list[DomainLabel], float, str]:
    """Run the explicit Anthropic adapter using a lazy optional import."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HostedClassifierUnavailable("ANTHROPIC_API_KEY is not configured")
    try:
        anthropic = importlib.import_module("anthropic")
    except ImportError as exc:
        raise HostedClassifierUnavailable(
            "install centinelas[hosted-classifier] to use Anthropic"
        ) from exc

    client_type = getattr(anthropic, "Anthropic", None)
    if client_type is None:
        raise HostedClassifierUnavailable("anthropic package has no Anthropic client")
    client = client_type(api_key=api_key)
    text = f"Title: {title}\n\nBody (first 800 chars): {body[:800]}"
    response = client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    try:
        decoded = json.loads(_response_text(response))
    except json.JSONDecodeError as exc:
        raise HostedClassifierUnavailable("hosted response is not valid JSON") from exc
    return _validate_hosted_result(decoded)


def classify(item: RawItem) -> tuple[list[DomainLabel], float, str]:
    """Classify one item under the selected, explicit dependency profile.

    ``local`` is the default and authoritative service-independent path.
    ``anthropic`` is opt-in.  When its default failure policy is
    ``local_fallback``, an unavailable hosted service cannot suppress the local
    result; the reasoning records the displaced hosted attempt without embedding
    provider exception text or credentials.
    """

    local_labels, local_confidence, local_reasoning = _local_classify(item)
    if classifier_mode() == _LOCAL_MODE:
        return local_labels, local_confidence, local_reasoning

    try:
        hosted_labels, hosted_confidence, hosted_reasoning = _llm_classify(
            item.title, item.body_text
        )
    except Exception as exc:
        if _hosted_failure_policy() == "fail_closed":
            raise HostedClassifierUnavailable(
                f"hosted classifier failed: {type(exc).__name__}"
            ) from exc
        log.warning(
            "Optional hosted classifier failed (%s); retaining local authority.",
            type(exc).__name__,
        )
        return (
            local_labels,
            local_confidence,
            f"{local_reasoning} HOSTED_OPTIONAL_UNAVAILABLE:{type(exc).__name__}.",
        )

    merged = [label for label in hosted_labels if label != DomainLabel.UNCLASSIFIED]
    for local_label in local_labels:
        if local_label != DomainLabel.UNCLASSIFIED and local_label not in merged:
            merged.append(local_label)
    if not merged:
        merged = [DomainLabel.UNCLASSIFIED]
    return (
        merged,
        max(local_confidence, hosted_confidence),
        f"HOSTED_OPTIONAL:anthropic: {hosted_reasoning or 'no reasoning supplied'}",
    )


def build_classified_item(raw: RawItem) -> ClassifiedItem:
    """Classify and deterministically enrich a RawItem."""

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
