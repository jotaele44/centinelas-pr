"""Route bridge from Centinelas discovery leads to the embedded producer."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from centinelas.space_discovery import validate_lead as validate_discovery_lead

LEGACY_PRIMARY = "satellite-observations-pr"
EMBEDDED_PRIMARY = "centinelas-space-observations"
CANONICAL_ROUTE_FIELDS = {
    "primary",
    "secondary",
    "correlation_target",
    "route_status",
    "routing_reason",
}
EMBEDDED_ROUTE_FIELDS = CANONICAL_ROUTE_FIELDS | {"repository", "case_authority"}


def _canonical_view(lead: dict[str, Any]) -> dict[str, Any]:
    route = lead.get("downstream_route")
    if not isinstance(route, dict):
        raise ValueError("embedded lead downstream route must be an object")
    if set(route) != EMBEDDED_ROUTE_FIELDS:
        missing = sorted(EMBEDDED_ROUTE_FIELDS - route.keys())
        unexpected = sorted(route.keys() - EMBEDDED_ROUTE_FIELDS)
        raise ValueError(
            "embedded route fields do not match the routing contract: "
            f"missing={missing} unexpected={unexpected}"
        )
    if route.get("primary") != EMBEDDED_PRIMARY:
        raise ValueError("embedded lead has an invalid primary route")
    if route.get("repository") != "centinelas-pr":
        raise ValueError("embedded lead has an invalid repository owner")
    if route.get("case_authority") != "ovnis-pr":
        raise ValueError("embedded lead has an invalid case authority")
    if route.get("correlation_target") != "thehub-pr":
        raise ValueError("embedded lead has an invalid correlation owner")

    canonical = deepcopy(lead)
    canonical["downstream_route"] = {
        key: value for key, value in route.items() if key in CANONICAL_ROUTE_FIELDS
    }
    canonical["downstream_route"]["primary"] = LEGACY_PRIMARY
    return canonical


def _validate_embedded_lead(lead: dict[str, Any]) -> None:
    validate_discovery_lead(_canonical_view(lead))
    if lead.get("review_status") not in {"qualified", "routed"}:
        raise ValueError("embedded intake requires a qualified or routed lead")


def route_to_embedded_producer(lead: dict[str, Any]) -> dict[str, Any]:
    """Return an immutable copy routed to the isolated logical producer.

    Only leads already targeting the legacy standalone producer, or leads already
    routed to the embedded producer, may cross this migration boundary. Unrelated
    routes are rejected rather than silently overwritten.
    """
    original_route = lead.get("downstream_route") or {}
    primary = original_route.get("primary")
    if primary not in {LEGACY_PRIMARY, EMBEDDED_PRIMARY}:
        raise ValueError(f"route bridge cannot upgrade unrelated primary route: {primary!r}")
    if original_route.get("correlation_target") not in {None, "thehub-pr"}:
        raise ValueError("route bridge cannot change correlation ownership")

    if primary == EMBEDDED_PRIMARY:
        _validate_embedded_lead(lead)
        return deepcopy(lead)

    validate_discovery_lead(lead)
    if lead.get("review_status") != "qualified":
        raise ValueError("route bridge only accepts qualified discovery leads")

    routed = deepcopy(lead)
    route = dict(routed.get("downstream_route") or {})
    route.update(
        {
            "primary": EMBEDDED_PRIMARY,
            "repository": "centinelas-pr",
            "correlation_target": "thehub-pr",
            "case_authority": "ovnis-pr",
            "route_status": "queued",
        }
    )
    routed["downstream_route"] = route
    routed["review_status"] = "routed"
    _validate_embedded_lead(routed)
    return routed
