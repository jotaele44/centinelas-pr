#!/usr/bin/env python3
"""Optionally mirror canonical Centinelas outbox envelopes through GitHub.

The local envelope file is authoritative. This script never constructs a new
application payload, truncates body text, or mints message identity. It wraps the
exact committed bytes with `prii.artifact-mirror.v1` and POSTs that wrapper only
when an operator explicitly enables the hosted bridge.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

from prii_export_utils import (
    InvalidMirrorError,
    build_mirror_payload,
    read_canonical_envelope,
    verify_mirror_payload,
)

DEFAULT_OWNER = "jotaele44"
DEFAULT_EVENT_TYPE = "centinelas-artifact-mirror"
GITHUB_API = "https://api.github.com"
SOURCE_REPOSITORY = "centinelas-pr"
_MAX_CLIENT_PAYLOAD_CHARS = 60_000


class MirrorDispatchError(RuntimeError):
    """Raised when a selected outbox cannot be mirrored without drift."""


def _outbox(exchange_root: Path) -> Path:
    return exchange_root / "outbox"


def iter_envelopes(
    exchange_root: Path,
) -> Iterator[tuple[str, Path, dict]]:
    """Yield validated whole envelopes in deterministic target/file order."""

    outbox = _outbox(exchange_root)
    if not outbox.exists():
        return
    if outbox.is_symlink() or not outbox.is_dir():
        raise MirrorDispatchError(f"outbox is not a regular directory: {outbox}")

    for target_dir in sorted(outbox.iterdir(), key=lambda path: path.name):
        if target_dir.is_symlink() or not target_dir.is_dir():
            raise MirrorDispatchError(
                f"unexpected non-directory outbox member: {target_dir}"
            )
        for path in sorted(target_dir.iterdir(), key=lambda member: member.name):
            if path.suffix != ".json":
                raise MirrorDispatchError(f"unexpected outbox member: {path}")
            envelope, _data = read_canonical_envelope(path)
            if envelope["source"] != SOURCE_REPOSITORY:
                raise MirrorDispatchError(
                    f"source mismatch in {path}: {envelope['source']!r}"
                )
            if envelope["target"] != target_dir.name:
                raise MirrorDispatchError(
                    f"target directory mismatch in {path}: "
                    f"{target_dir.name!r} != {envelope['target']!r}"
                )
            if path.name != f"{envelope['message_id']}.json":
                raise MirrorDispatchError(
                    f"filename does not match message_id in {path}"
                )
            yield target_dir.name, path, envelope


def build_dispatch_body(path: Path, event_type: str) -> dict:
    """Build one hosted request around the exact local envelope bytes."""

    mirror = build_mirror_payload(path)
    verify_mirror_payload(mirror)
    serialized = json.dumps(
        mirror,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(serialized) > _MAX_CLIENT_PAYLOAD_CHARS:
        raise MirrorDispatchError(
            f"mirror payload is {len(serialized)} characters; "
            f"hosted limit is {_MAX_CLIENT_PAYLOAD_CHARS}. "
            "The local envelope remains authoritative and was not modified."
        )
    return {"event_type": event_type, "client_payload": mirror}


def post_dispatch(owner: str, repo: str, body: dict, token: str) -> int:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/dispatches"
    data = json.dumps(
        body,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        return response.status


def run(
    exchange_root: Path,
    owner: str,
    event_type: str,
    token: str | None,
    dry_run: bool,
    only_repo: str | None = None,
) -> int:
    outbox = _outbox(exchange_root)
    if not outbox.exists():
        print(f"No local outbox {outbox} - nothing to mirror.")
        return 0
    if not dry_run and not token:
        print(
            "FEDERATION_DISPATCH_TOKEN / GITHUB_TOKEN not set; "
            "local outbox remains authoritative.",
            file=sys.stderr,
        )
        return 2

    mirrored = 0
    failed = 0
    try:
        selected = iter_envelopes(exchange_root)
        for repo, path, envelope in selected:
            if only_repo and repo != only_repo:
                continue
            target = f"{owner}/{repo}"
            try:
                body = build_dispatch_body(path, event_type)
                if dry_run:
                    print(
                        f"[dry-run] {event_type} -> {target} "
                        f"(message {envelope['message_id']})"
                    )
                    mirrored += 1
                    continue
                assert token is not None
                status = post_dispatch(owner, repo, body, token)
                print(
                    f"mirrored {envelope['message_id']} -> {target} "
                    f"(HTTP {status})"
                )
                mirrored += 1
            except (InvalidMirrorError, MirrorDispatchError, OSError, ValueError) as exc:
                print(
                    f"FAILED {envelope['message_id']} -> {target}: {exc}",
                    file=sys.stderr,
                )
                failed += 1
            except urllib.error.HTTPError as exc:
                print(
                    f"FAILED {envelope['message_id']} -> {target}: "
                    f"HTTP {exc.code} {exc.reason}",
                    file=sys.stderr,
                )
                failed += 1
            except urllib.error.URLError as exc:
                print(
                    f"FAILED {envelope['message_id']} -> {target}: {exc.reason}",
                    file=sys.stderr,
                )
                failed += 1
    except (InvalidMirrorError, MirrorDispatchError, OSError, ValueError) as exc:
        print(f"OUTBOX INVALID: {exc}", file=sys.stderr)
        return 1

    print(f"\nMirrored {mirrored} envelope(s), {failed} failure(s).")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exchange-root",
        default=os.environ.get(
            "CENTINELAS_EXCHANGE_ROOT", ".centinelas/exchange"
        ),
        help="Canonical local exchange root containing outbox/<target>/*.json",
    )
    parser.add_argument(
        "--owner", default=DEFAULT_OWNER, help="GitHub owner of downstream repos"
    )
    parser.add_argument(
        "--event-type",
        default=DEFAULT_EVENT_TYPE,
        help="repository_dispatch event_type for the optional mirror",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and report; do not POST"
    )
    parser.add_argument(
        "--only-repo",
        default=None,
        help="Only mirror envelopes addressed to this repository",
    )
    args = parser.parse_args()

    token = os.environ.get("FEDERATION_DISPATCH_TOKEN") or os.environ.get(
        "GITHUB_TOKEN"
    )
    return run(
        Path(args.exchange_root),
        args.owner,
        args.event_type,
        token,
        args.dry_run,
        only_repo=args.only_repo,
    )


if __name__ == "__main__":
    sys.exit(main())
