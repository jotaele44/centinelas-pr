"""Writes dispatch payloads to each repo's intake/ folder."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from centinelas.models import ClassifiedItem, DispatchRecord
from centinelas.route.router import route

log = logging.getLogger(__name__)

_REPOS_BASE = Path(os.environ.get("CENTINELAS_REPOS_DIR", str(Path.home() / "Developer")))
_DATA_DIR = Path(os.environ.get("CENTINELAS_DATA_DIR", ".centinelas"))

# Minimum classifier confidence for an item to be routed/exported. Below this the
# item is skipped (not dispatched to any repo) — the gate that keeps low-confidence
# noise out of the downstream MoneySweep/Hub event pipeline. Env-overridable to mirror
# the repo's existing env-var config style (see CENTINELAS_REPOS_DIR above).
_DEFAULT_ROUTE_MIN_CONFIDENCE = 0.55


def _route_min_confidence() -> float:
    """Read the route confidence gate at call time so tests/CI can override via env."""
    try:
        return float(
            os.environ.get("CENTINELAS_ROUTE_MIN_CONFIDENCE", _DEFAULT_ROUTE_MIN_CONFIDENCE)
        )
    except ValueError:
        return _DEFAULT_ROUTE_MIN_CONFIDENCE


def _repo_intake_dir(repo_name: str) -> Path:
    """Directory the item payload is written to for a target repo.

    Default: the sibling checkout's ``intake/`` folder (local dev, repos side by side).
    When ``CENTINELAS_OUTBOUND_DIR`` is set (CI / event-driven mode), payloads are staged
    under ``<outbound>/<repo>/`` instead — no sibling checkout needed — for a downstream
    emitter (scripts/emit_dispatches.py) to POST as GitHub repository_dispatch events.
    """
    outbound = os.environ.get("CENTINELAS_OUTBOUND_DIR")
    if outbound:
        return Path(outbound) / repo_name
    return _REPOS_BASE / repo_name / "intake"


def _dispatched_record_path(item_id: str) -> Path:
    return _DATA_DIR / "dispatched" / f"{item_id}.json"


def _persist_dispatch_record(record: DispatchRecord) -> None:
    """Write the DispatchRecord to local Centinelas bookkeeping — always, even under dry_run.

    This is Centinelas's own local state, not a write into a sibling repo, so it's
    unaffected by dry_run (which only guards cross-repo intake/ writes below).
    """
    path = _dispatched_record_path(record.item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2))


def dispatch(item: ClassifiedItem, dry_run: bool = False) -> DispatchRecord:
    """
    Write item payloads to each target repo's intake/ folder.
    Always writes to thehub-pr. Returns a DispatchRecord.
    """
    threshold = _route_min_confidence()
    if item.confidence < threshold:
        log.info(
            "Skipping %s: confidence %.2f < route minimum %.2f",
            item.item_id,
            item.confidence,
            threshold,
        )
        record = DispatchRecord(
            item_id=item.item_id,
            dispatched_to=[],
            dispatched_at=datetime.now(timezone.utc),
            status="skipped",
            error=f"confidence {item.confidence:.2f} < route minimum {threshold:.2f}",
        )
        _persist_dispatch_record(record)
        return record

    payloads = route(item)
    dispatched_to: list[str] = []
    errors: list[str] = []

    for repo, payload in payloads.items():
        intake_dir = _repo_intake_dir(repo)
        out_path = intake_dir / f"{item.item_id}.json"

        if dry_run:
            log.info("[dry-run] would write %s → %s", item.item_id, out_path)
            dispatched_to.append(repo)
            continue

        try:
            intake_dir.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(payload, f, indent=2)
            dispatched_to.append(repo)
            log.info("Dispatched %s → %s", item.item_id, repo)
        except Exception as exc:
            log.error("Dispatch failed for %s → %s: %s", item.item_id, repo, exc)
            errors.append(f"{repo}: {exc}")

    status: str
    if errors and not dispatched_to:
        status = "failed"
    elif errors:
        status = "failed"
    else:
        status = "ok"

    record = DispatchRecord(
        item_id=item.item_id,
        dispatched_to=dispatched_to,
        dispatched_at=datetime.now(timezone.utc),
        status=status,  # type: ignore[arg-type]
        error="; ".join(errors) if errors else None,
    )
    _persist_dispatch_record(record)
    return record


def dispatch_many(items: list[ClassifiedItem], dry_run: bool = False) -> list[DispatchRecord]:
    return [dispatch(item, dry_run=dry_run) for item in items]
