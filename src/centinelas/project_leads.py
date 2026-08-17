"""Deterministic, conservative project-lead extraction for Centinelas signals.

A project lead is a discovery artifact, never an identity assertion.  It gives
MoneySweep and SpiderWeb a shared immutable investigation key while preserving
the original Centinelas item as source provenance.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from centinelas.classify.labels import DomainLabel
from centinelas.models import ClassifiedItem

PROJECT_LEAD_SCHEMA_VERSION = "1.0"
PROJECT_LEAD_PREFIX = "prjlead_"

# Explicit procurement/project lifecycle stages are strong enough to open a lead
# when the signal is finance-anchored.  Unknown stages fall back to conservative
# lexical detection below.
_PROJECT_STAGES = {
    "announced",
    "planned",
    "rfp_open",
    "bid_open",
    "award_pending",
    "awarded",
    "contracted",
    "under_construction",
}

_PROJECT_TERMS = re.compile(
    r"\b(project|proyecto|construction|construcci[oó]n|reconstruction|reconstrucci[oó]n|"
    r"rehabilitation|rehabilitaci[oó]n|repair|repairs|reparaci[oó]n|mejoras|improvements|"
    r"renovation|renovaci[oó]n|recovery|recuperaci[oó]n)\b",
    re.IGNORECASE,
)
_PROCUREMENT_TERMS = re.compile(
    r"\b(contract|contrato|award|adjudicaci[oó]n|rfp|bid|subasta|procurement|licitaci[oó]n|"
    r"funding|fondos|investment|inversi[oó]n|fema|public works|pw\s*\d+)\b",
    re.IGNORECASE,
)


def _normalized_stage(item: ClassifiedItem) -> str:
    raw = getattr(item, "signal_stage", None)
    return str(raw or "").strip().lower()


def qualifies_project_lead(item: ClassifiedItem) -> bool:
    """Return True only for a finance-anchored signal with project evidence.

    This gate intentionally prefers false negatives over turning ordinary news
    into project identities.  The result opens an investigation only; downstream
    producers must independently bind their own records.
    """
    labels = {getattr(label, "value", str(label)) for label in item.labels}
    if DomainLabel.FINANCIAL.value not in labels:
        return False

    if _normalized_stage(item) in _PROJECT_STAGES:
        return True

    text = f"{item.title} {item.body_text or ''}"
    return bool(_PROJECT_TERMS.search(text) and _PROCUREMENT_TERMS.search(text))


def project_lead_id(item: ClassifiedItem) -> str:
    """Stable lead id derived from the immutable Centinelas item identifier."""
    seed = f"centinelas-project-lead-v1|{item.item_id}".encode("utf-8")
    return PROJECT_LEAD_PREFIX + hashlib.sha256(seed).hexdigest()[:32]


def build_project_lead(item: ClassifiedItem) -> dict[str, Any] | None:
    """Build the shared discovery envelope or return None for normal signals."""
    if not qualifies_project_lead(item):
        return None
    return {
        "schema_version": PROJECT_LEAD_SCHEMA_VERSION,
        "lead_id": project_lead_id(item),
        "origin_item_id": item.item_id,
        "origin_producer": "centinelas-pr",
        "source_url": str(item.source_url),
        "source_title_raw": item.title,
        "published_at": item.published_at.isoformat(),
        "captured_at": item.captured_at.isoformat(),
        "municipality_candidates": list(getattr(item, "municipalities", []) or []),
        "agency_candidates": list(getattr(item, "agencies", []) or []),
        "recipient_candidates": list(getattr(item, "recipients", []) or []),
        "estimated_value_claim": getattr(item, "estimated_value", None),
        "signal_stage_claim": getattr(item, "signal_stage", None),
        "beat": getattr(item, "beat", None),
        "identity_effect": "NONE",
        "discovery_state": "DETECTED",
    }


__all__ = [
    "PROJECT_LEAD_SCHEMA_VERSION",
    "build_project_lead",
    "project_lead_id",
    "qualifies_project_lead",
]
