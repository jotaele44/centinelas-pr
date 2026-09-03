"""Inert API contract for a future operator-only email review surface.

This module deliberately registers no FastAPI routes. A later activation PR must
bind authentication, private persistence, and authorization before exposing it.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EmailReviewQueueItem(BaseModel):
    alert_result_id: str
    received_at: str
    title: str
    source_domain: str | None = None
    municipality_candidates: list[str] = Field(default_factory=list)
    agency_candidates: list[str] = Field(default_factory=list)
    duplicate_status: Literal["distinct", "exact", "url", "content", "probable", "related_update"] = "distinct"
    parser_confidence: float = Field(ge=0.0, le=1.0)
    privacy_export_allowed: Literal[False] = False


class EmailReviewDecision(BaseModel):
    alert_result_id: str
    action: Literal["accept_as_lead", "duplicate", "irrelevant", "reject", "acquire_source"]
    operator_note: str = ""
    promote_to_verified_signal: Literal[False] = False


DIAGNOSTIC_ROUTES = (
    "/admin/email-sources",
    "/admin/email-runs",
    "/admin/email-messages",
    "/admin/email-review",
    "/admin/email-parser-health",
)


def activation_status() -> dict[str, object]:
    return {
        "enabled": False,
        "routes_registered": False,
        "authentication_required_before_activation": True,
        "federation_export_allowed": False,
        "auto_promotion_allowed": False,
        "diagnostic_routes": DIAGNOSTIC_ROUTES,
    }
