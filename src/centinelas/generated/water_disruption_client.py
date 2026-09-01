"""Generated-style dependency-free client for the shadow water-disruption API."""
from __future__ import annotations

import json
import urllib.request
from typing import Any


class WaterDisruptionClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Any:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def sources(self) -> Any:
        return self._request("GET", "/water-disruption/sources")

    def candidates(self) -> Any:
        return self._request("GET", "/water-disruption/candidates")

    def dispatch(self, candidate_id: str, key: str) -> Any:
        return self._request("POST", f"/water-disruption/candidates/{candidate_id}/dispatch", {}, key)
