#!/usr/bin/env python3
"""Emit only project-lead SpiderWeb handoffs from Centinelas outbound staging.

This deliberately does not activate generic SpiderWeb dispatch.  Existing
non-project discovery routing remains unchanged while qualifying finance project
leads gain the second investigative lane requested by the federation design.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from emit_dispatches import build_dispatch_body, post_dispatch

TARGET_REPO = "spiderweb-pr"
EVENT_TYPE = "centinelas-signal"
DEFAULT_OWNER = "jotaele44"


def run(outbound: Path, owner: str, token: str | None, dry_run: bool) -> int:
    repo_dir = outbound / TARGET_REPO
    if not repo_dir.is_dir():
        print("No SpiderWeb outbound directory — no project leads to fan out.")
        return 0

    emitted = 0
    failed = 0
    for path in sorted(repo_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
            failed += 1
            continue
        lead = payload.get("project_lead")
        if not isinstance(lead, dict) or not lead.get("lead_id"):
            continue
        item_id = str(payload.get("item_id") or path.stem)
        body = build_dispatch_body(item_id, TARGET_REPO, payload, EVENT_TYPE)
        if dry_run:
            print(f"[dry-run] project lead {lead['lead_id']} -> {owner}/{TARGET_REPO}")
            emitted += 1
            continue
        if not token:
            print("FEDERATION_DISPATCH_TOKEN / GITHUB_TOKEN not set", file=sys.stderr)
            return 2
        try:
            status = post_dispatch(owner, TARGET_REPO, body, token)
            print(f"dispatched project lead {lead['lead_id']} -> {TARGET_REPO} (HTTP {status})")
            emitted += 1
        except Exception as exc:  # network boundary: report and fail closed
            print(f"FAILED {item_id} -> {TARGET_REPO}: {exc}", file=sys.stderr)
            failed += 1

    print(f"Project-lead SpiderWeb dispatches: {emitted}; failures: {failed}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outbound", default=os.environ.get("CENTINELAS_OUTBOUND_DIR", ".centinelas/outbound"))
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("FEDERATION_DISPATCH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return run(Path(args.outbound), args.owner, token, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
