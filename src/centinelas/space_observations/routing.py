"""Route bridge from Centinelas discovery leads to the embedded producer."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def route_to_embedded_producer(lead: dict[str, Any]) -> dict[str, Any]:
    """Return a copy routed to the isolated logical producer.

    This is the migration boundary for leads created under the earlier
    `satellite-observations-pr` route. It never changes case or correlation ownership.
    """
    routed = deepcopy(lead)
    route = dict(routed.get("downstream_route") or {})
    route.update({
        "primary": "centinelas-space-observations",
        "repository": "centinelas-pr",
        "correlation_target": "thehub-pr",
        "case_authority": "ovnis-pr",
        "route_status": "routed",
    })
    routed["downstream_route"] = route
    routed["review_status"] = "routed"
    return routed
