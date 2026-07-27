"""Route bridge from Centinelas discovery leads to the embedded producer."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

LEGACY_PRIMARY = "satellite-observations-pr"
EMBEDDED_PRIMARY = "centinelas-space-observations"


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

    routed = deepcopy(lead)
    route = dict(routed.get("downstream_route") or {})
    route.update({
        "primary": EMBEDDED_PRIMARY,
        "repository": "centinelas-pr",
        "correlation_target": "thehub-pr",
        "case_authority": "ovnis-pr",
        "route_status": "routed",
    })
    routed["downstream_route"] = route
    routed["review_status"] = "routed"
    return routed
