#!/usr/bin/env python3
"""Emit GitHub ``repository_dispatch`` events for staged Centinelas intake payloads.

This is the CI half of the event-driven export: ``centinelas run`` (with
``CENTINELAS_OUTBOUND_DIR`` set) stages one JSON payload per routed item under
``<outbound>/<repo>/<item_id>.json``; this script POSTs each as a
``repository_dispatch`` to the corresponding downstream repo, so a workflow there
(e.g. moneysweep-pr ``centinelas-intake.yml``) fires and ingests it.

GitHub caps ``client_payload`` at 10 top-level properties, so the (larger) intake
record is wrapped under a single ``signal`` key alongside ``item_id`` / ``repo``.

Auth: ``FEDERATION_DISPATCH_TOKEN`` (preferred) or ``GITHUB_TOKEN`` — a token with
``contents:write`` (or classic ``repo``) on the downstream repo.

Usage:
  python3 scripts/emit_dispatches.py --outbound .centinelas/outbound
  python3 scripts/emit_dispatches.py --outbound .centinelas/outbound --dry-run
  python3 scripts/emit_dispatches.py --outbound out --owner jotaele44 --event-type centinelas-signal
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_OWNER = "jotaele44"
DEFAULT_EVENT_TYPE = "centinelas-signal"
GITHUB_API = "https://api.github.com"

# GitHub caps repository_dispatch client_payload at 65,535 characters. body_text is
# the only unbounded field (full-article RSS feeds), so trim it — keeping the
# structured fields + source_url intact so MoneySweep can re-fetch the full text if
# needed. Cap the wrapped client_payload with headroom below GitHub's hard limit.
_MAX_BODY_TEXT = 8000
_MAX_CLIENT_PAYLOAD_CHARS = 60000
_TRUNCATION_MARKER = "… [truncated]"


def _bounded_signal(payload: dict) -> dict:
    """Copy the intake record with body_text trimmed to a sane length."""
    signal = dict(payload)
    body = signal.get("body_text")
    if isinstance(body, str) and len(body) > _MAX_BODY_TEXT:
        signal["body_text"] = body[:_MAX_BODY_TEXT] + _TRUNCATION_MARKER
    return signal


def iter_payloads(outbound: Path):
    """Yield (repo_name, item_id, payload) for every staged ``<repo>/<id>.json``."""
    for repo_dir in sorted(p for p in outbound.iterdir() if p.is_dir()):
        for payload_path in sorted(repo_dir.glob("*.json")):
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                print(f"  skip {payload_path}: {exc}", file=sys.stderr)
                continue
            yield repo_dir.name, payload_path.stem, payload


def build_dispatch_body(item_id: str, repo: str, payload: dict, event_type: str) -> dict:
    """Wrap the intake record so client_payload stays within GitHub's key + size limits.

    client_payload is limited to 10 top-level keys (here: item_id/repo/signal) and to
    65,535 characters total. body_text is trimmed up front and then hard-bounded so a
    long signal still delivers (HTTP 422 otherwise) instead of being dropped silently.
    """
    signal = _bounded_signal(payload)
    client_payload = {"item_id": item_id, "repo": repo, "signal": signal}
    # Hard guard: if many structured fields still push over the cap, halve body_text
    # until the serialized payload fits (or drop it entirely as a last resort).
    while len(json.dumps(client_payload)) > _MAX_CLIENT_PAYLOAD_CHARS and signal.get("body_text"):
        trimmed = signal["body_text"][: max(0, len(signal["body_text"]) // 2)]
        signal["body_text"] = "" if len(trimmed) < 100 else trimmed + _TRUNCATION_MARKER
    return {"event_type": event_type, "client_payload": client_payload}


def post_dispatch(owner: str, repo: str, body: dict, token: str) -> int:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/dispatches"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (fixed GitHub API host)
        return resp.status


def run(
    outbound: Path,
    owner: str,
    event_type: str,
    token: str | None,
    dry_run: bool,
    only_repo: str | None = None,
) -> int:
    if not outbound.is_dir():
        print(f"No outbound dir {outbound} — nothing to dispatch.")
        return 0

    emitted = 0
    failed = 0
    for repo, item_id, payload in iter_payloads(outbound):
        # Chain scoping: Centinelas triggers only its direct downstream (MoneySweep);
        # the Hub is triggered later by MoneySweep's own export event, so it receives
        # the fused finance/location result rather than the raw signal.
        if only_repo and repo != only_repo:
            continue
        body = build_dispatch_body(item_id, repo, payload, event_type)
        target = f"{owner}/{repo}"
        if dry_run:
            print(f"[dry-run] {event_type} → {target} (item {item_id})")
            emitted += 1
            continue
        if not token:
            print("  FEDERATION_DISPATCH_TOKEN / GITHUB_TOKEN not set", file=sys.stderr)
            return 2
        try:
            status = post_dispatch(owner, repo, body, token)
            print(f"  dispatched {item_id} → {target} (HTTP {status})")
            emitted += 1
        except urllib.error.HTTPError as exc:
            print(f"  FAILED {item_id} → {target}: HTTP {exc.code} {exc.reason}", file=sys.stderr)
            failed += 1
        except urllib.error.URLError as exc:
            print(f"  FAILED {item_id} → {target}: {exc.reason}", file=sys.stderr)
            failed += 1

    print(f"\nDispatched {emitted} event(s), {failed} failure(s).")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outbound",
        default=os.environ.get("CENTINELAS_OUTBOUND_DIR", ".centinelas/outbound"),
        help="Staged payload dir (<outbound>/<repo>/<item_id>.json)",
    )
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="GitHub owner of downstream repos")
    parser.add_argument(
        "--event-type", default=DEFAULT_EVENT_TYPE, help="repository_dispatch event_type"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print intended dispatches, do not POST"
    )
    parser.add_argument(
        "--only-repo",
        default=None,
        help="Only dispatch payloads staged for this repo (e.g. moneysweep-pr)",
    )
    args = parser.parse_args()

    token = os.environ.get("FEDERATION_DISPATCH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return run(
        Path(args.outbound),
        args.owner,
        args.event_type,
        token,
        args.dry_run,
        only_repo=args.only_repo,
    )


if __name__ == "__main__":
    sys.exit(main())
