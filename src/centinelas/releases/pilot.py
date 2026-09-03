from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PILOT_SOURCE_ALLOWLIST = {
    "nara_ndc",
    "dia_reading_room",
    "air_force_blue_book",
}


class PilotPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PilotLimits:
    max_pages_per_run: int
    max_records_per_run: int
    daily_request_budget: int


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PilotPolicyError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise PilotPolicyError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("mode") != "metadata_only":
        raise PilotPolicyError("pilot mode must be metadata_only")
    if payload.get("linked_binary_fetch") is not False:
        raise PilotPolicyError("linked binary fetch must remain disabled")
    if payload.get("baseline_mutation_allowed") is not False:
        raise PilotPolicyError("baseline mutation must remain disabled")
    kill_switch = payload.get("emergency_kill_switch") or {}
    if kill_switch.get("available") is not True:
        raise PilotPolicyError("emergency kill switch must be available")
    return payload


def source_readiness(
    manifest: dict[str, Any],
    source_id: str,
    *,
    now: datetime | None = None,
) -> tuple[bool, list[str]]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reasons: list[str] = []
    if source_id not in PILOT_SOURCE_ALLOWLIST:
        reasons.append("SOURCE_NOT_IN_PILOT_ALLOWLIST")
    kill_switch = manifest.get("emergency_kill_switch") or {}
    if kill_switch.get("engaged") is not False:
        reasons.append("EMERGENCY_KILL_SWITCH_ENGAGED")
    source = (manifest.get("sources") or {}).get(source_id)
    if not isinstance(source, dict):
        reasons.append("SOURCE_CONFIGURATION_MISSING")
        return False, reasons
    if source.get("enabled") is not True:
        reasons.append("SOURCE_DISABLED")
    if source.get("approval_status") != "approved":
        reasons.append("APPROVAL_NOT_GRANTED")
    if not str(source.get("approved_by") or "").strip():
        reasons.append("APPROVER_IDENTITY_MISSING")
    if source.get("robots_allowed") is not True:
        reasons.append("ROBOTS_NOT_ALLOWED")
    if source.get("policy_review_status") != "approved":
        reasons.append("POLICY_REVIEW_NOT_APPROVED")
    if source.get("metadata_only") is not True:
        reasons.append("SOURCE_NOT_METADATA_ONLY")
    if source.get("linked_binary_fetch") is not False:
        reasons.append("SOURCE_BINARY_FETCH_NOT_DISABLED")
    try:
        approved_at = _parse_time(str(source.get("approved_at") or ""), "approved_at")
        expires_at = _parse_time(
            str(source.get("approval_expires_at") or ""),
            "approval_expires_at",
        )
        if approved_at >= expires_at:
            reasons.append("APPROVAL_WINDOW_INVALID")
        if now >= expires_at:
            reasons.append("APPROVAL_EXPIRED")
    except PilotPolicyError as exc:
        reasons.append(str(exc))
    for field in ("max_pages_per_run", "max_records_per_run", "daily_request_budget"):
        value = source.get(field)
        if not isinstance(value, int) or value <= 0:
            reasons.append(f"{field.upper()}_INVALID")
    if isinstance(source.get("max_pages_per_run"), int) and source["max_pages_per_run"] > 2:
        reasons.append("MAX_PAGES_EXCEEDS_PILOT_CAP")
    if isinstance(source.get("max_records_per_run"), int) and source["max_records_per_run"] > 250:
        reasons.append("MAX_RECORDS_EXCEEDS_PILOT_CAP")
    if isinstance(source.get("daily_request_budget"), int) and source["daily_request_budget"] > 6:
        reasons.append("DAILY_REQUEST_BUDGET_EXCEEDS_PILOT_CAP")
    return not reasons, reasons


def readiness_certificate(
    manifest: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for source_id in sorted(PILOT_SOURCE_ALLOWLIST):
        ready, reasons = source_readiness(manifest, source_id, now=now)
        results[source_id] = {"ready": ready, "reasons": reasons}
    return {
        "pilot_ready": all(row["ready"] for row in results.values()),
        "mode": manifest.get("mode"),
        "linked_binary_fetch": manifest.get("linked_binary_fetch"),
        "baseline_mutation_allowed": manifest.get("baseline_mutation_allowed"),
        "emergency_kill_switch": manifest.get("emergency_kill_switch"),
        "sources": results,
    }
