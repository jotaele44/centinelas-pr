"""Failed-target-only retry selection for satellite observation intake."""

from __future__ import annotations

from typing import Any

from .producer import IntakeEngine, IntakeResult, _read_jsonl


def retry_failed(
    engine: IntakeEngine,
    leads: list[dict[str, Any]],
    *,
    failed_run_id: str,
    retry_run_id: str,
) -> list[IntakeResult]:
    """Retry only retryable lead IDs recorded as failed in a prior run.

    The caller supplies the original lead envelopes; the persistent failure ledger
    supplies the authoritative retry selection. Rejected/non-retryable rows and
    unrelated leads are never replayed.
    """
    failure_path = engine.root / "data" / "space_observations" / "ledgers" / "failures.jsonl"
    retryable_ids = {
        row.get("lead_id")
        for row in _read_jsonl(failure_path)
        if row.get("run_id") == failed_run_id
        and row.get("retryable") is True
        and row.get("lead_id")
    }
    selected = [lead for lead in leads if lead.get("lead_id") in retryable_ids]
    return engine.process_many(selected, run_id=retry_run_id)
