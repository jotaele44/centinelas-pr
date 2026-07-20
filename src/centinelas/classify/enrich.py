"""Deterministic pre-officialization enrichment for finance/procurement signals.

The classifier assigns *domain labels*; this module extracts the structured
*finance/location* fields that travel to the MoneySweep anchor so it can build a
**located pre-official finance candidate** without re-parsing free text:

    estimated_value  — headline dollar amount (the one field MoneySweep cannot
                       re-derive; it reads ``payload["estimated_value"]`` and
                       degrades to 0.0 when absent)
    agencies         — awarding / implicated PR/federal agencies
    signal_stage     — where in the award lifecycle the signal sits
    beat             — editorial beat ("procurement" for award/contract items)

Everything is rules-based (no LLM, no API cost) and mirrors ``classify/rules.py``:
accent-folded, word-boundary matching so PR Spanish ("adjudicación", "millones")
and English match interchangeably. All fields degrade gracefully to empty —
MoneySweep re-derives the municipality from title/body via ``attribute_geo``, so
this module intentionally does not duplicate the municipality reference.
"""

from __future__ import annotations

import re

from centinelas.classify.rules import _fold

# ── Monetary amount ───────────────────────────────────────────────────────────
# Scale words → multiplier. Longest phrases first so "mil millones" (Spanish
# "billion") wins over "millones", and the alternation is built length-desc.
_SCALE: dict[str, float] = {
    "mil millones": 1e9,
    "billions": 1e9,
    "billion": 1e9,
    "millones": 1e6,
    "millions": 1e6,
    "million": 1e6,
    "millon": 1e6,
}
_SCALE_ALT = "|".join(sorted((re.escape(k) for k in _SCALE), key=len, reverse=True))

# "$299.7 million", "299.7 millones", "$1.2 billion", "1 mil millones".
_SCALED_RE = re.compile(rf"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*({_SCALE_ALT})\b")
# Plain currency with a thousands group or 4+ bare digits: "$299,700,000".
_PLAIN_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)")


def _to_float(number: str) -> float | None:
    """Parse a captured numeric string, treating ',' as a thousands separator."""
    try:
        return float(number.replace(",", ""))
    except ValueError:
        return None


def extract_estimated_value(text: str) -> float | None:
    """Return the largest USD amount mentioned (headline award value), or None.

    Handles scaled forms ("$299.7 million", "299.7 millones", "$1.2 billion",
    "mil millones") and plain currency ("$299,700,000"). Picking the max keeps
    the headline figure when a body also cites smaller line items.
    """
    folded = _fold(text)
    values: list[float] = []

    for number, scale in _SCALED_RE.findall(folded):
        magnitude = _to_float(number)
        if magnitude is not None:
            values.append(magnitude * _SCALE[scale])

    for number in _PLAIN_RE.findall(folded):
        magnitude = _to_float(number)
        if magnitude is not None:
            values.append(magnitude)

    return max(values) if values else None


# ── Agencies ──────────────────────────────────────────────────────────────────
# Canonical agency name → accent-folded keyword variants. Short/ambiguous bare
# acronyms ("act", "aaa") are deliberately excluded to avoid spurious hits;
# multi-word forms are safe under word-boundary matching.
_AGENCIES: dict[str, list[str]] = {
    "Puerto Rico National Guard": ["national guard", "guardia nacional"],
    "USACE": ["usace", "army corps of engineers", "cuerpo de ingenieros"],
    "FEMA": ["fema"],
    "PRASA": ["prasa", "acueductos y alcantarillados"],
    "PREPA": ["prepa", "autoridad de energia electrica"],
    "COR3": ["cor3", "central office for recovery"],
    "Autoridad de Carreteras y Transportacion": [
        "autoridad de carreteras", "carreteras y transportacion",
    ],
    "Department of Transportation": [
        "department of transportation", "departamento de transportacion", "dtop",
    ],
}


def extract_agencies(text: str) -> list[str]:
    """Return canonical names of agencies referenced in the text (order-stable)."""
    folded = _fold(text)
    padded = f" {folded} "
    found: list[str] = []
    for canonical, variants in _AGENCIES.items():
        if any(re.search(rf"\b{re.escape(v)}\b", padded) for v in variants):
            found.append(canonical)
    return found


# ── Signal stage & beat ───────────────────────────────────────────────────────
_AWARD_TERMS = [
    "awarded", "award of", "adjudicacion", "adjudico", "adjudicada",
    "aviso de adjudicacion", "won the contract", "wins contract",
]
_SOLICITATION_TERMS = [
    "rfp", "request for proposal", "request for proposals",
    "subasta", "licitacion", "solicitation", "bid opening",
]
_PROCUREMENT_TERMS = _AWARD_TERMS + _SOLICITATION_TERMS + [
    "contract", "contrato", "procurement", "obra publica", "obras publicas",
]


def _matches_any(folded: str, terms: list[str]) -> bool:
    padded = f" {folded} "
    return any(re.search(rf"\b{re.escape(t)}\b", padded) for t in terms)


def extract_signal_stage(text: str) -> str | None:
    """Classify the pre-officialization lifecycle stage of the signal.

    ``award_announced`` when the item announces an awarded/adjudicated contract,
    ``rfp_open`` for an open solicitation/bid, else ``None`` (no procurement
    lifecycle detected). Returning None keeps non-finance items from carrying a
    spurious stage and lets MoneySweep fall back to its ``pre_official`` marker.
    """
    folded = _fold(text)
    if _matches_any(folded, _AWARD_TERMS):
        return "award_announced"
    if _matches_any(folded, _SOLICITATION_TERMS):
        return "rfp_open"
    return None


def extract_beat(text: str) -> str | None:
    """Return ``"procurement"`` when the item carries award/contract vocabulary."""
    return "procurement" if _matches_any(_fold(text), _PROCUREMENT_TERMS) else None


def extract(title: str, body_text: str) -> dict:
    """Extract all enrichment fields from a signal's title + body.

    Returns a dict keyed to match ``ClassifiedItem``'s enrichment fields, so a
    caller can splat it straight into the model. ``municipalities`` is left empty
    on purpose — MoneySweep re-derives it from title/body via its canonical PR
    municipality reference (``attribute_geo``).
    """
    text = f"{title} {body_text}"
    return {
        "municipalities": [],
        "agencies": extract_agencies(text),
        "estimated_value": extract_estimated_value(text),
        "signal_stage": extract_signal_stage(text),
        "beat": extract_beat(text),
    }
