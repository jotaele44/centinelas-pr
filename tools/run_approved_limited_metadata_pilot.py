#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from centinelas.releases.parsers import PARSER_REGISTRY
from centinelas.releases.pilot import load_manifest, readiness_certificate
from centinelas.releases.source_endpoints import SOURCE_ENDPOINTS

PILOT_SOURCES = ("nara_ndc", "dia_reading_room", "air_force_blue_book")
USER_AGENT = "centinelas-pr-limited-metadata-pilot/1.0"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fetch_index(url: str, timeout: float) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(response.status), response.geturl(), response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    approval = json.loads(args.approval.read_text())
    now = datetime.now(timezone.utc)
    readiness = readiness_certificate(manifest, now=now)
    if not readiness["pilot_ready"]:
        raise SystemExit(f"pilot readiness denied: {readiness}")
    if approval.get("approval_status") != "approved":
        raise SystemExit("approval status is not approved")
    if tuple(approval["scope"]["sources"]) != PILOT_SOURCES:
        raise SystemExit("approval source scope mismatch")
    enabled = tuple(
        source_id
        for source_id, row in manifest["sources"].items()
        if row.get("enabled") is True
    )
    if enabled != PILOT_SOURCES:
        raise SystemExit(f"enabled source scope mismatch: {enabled}")

    args.out.mkdir(parents=True, exist_ok=True)
    run_ledger: list[dict[str, Any]] = []
    request_budget: dict[str, int] = {source_id: 0 for source_id in PILOT_SOURCES}
    source_certificates: dict[str, Any] = {}

    for source_id in PILOT_SOURCES:
        source_config = manifest["sources"][source_id]
        endpoint = SOURCE_ENDPOINTS[source_id]
        runs: list[dict[str, Any]] = []
        for run_number in (1, 2):
            if run_number > 1:
                time.sleep(args.delay)
            status, final_url, body = fetch_index(endpoint.index_url, args.timeout)
            request_budget[source_id] += 1
            if request_budget[source_id] > source_config["daily_request_budget"]:
                raise SystemExit(f"daily request budget exceeded for {source_id}")
            records, has_next = PARSER_REGISTRY[source_id](body)
            normalized = sorted(records, key=lambda row: row["source_key"])
            if len(normalized) > source_config["max_records_per_run"]:
                raise SystemExit(f"record cap exceeded for {source_id}")
            row = {
                "source_id": source_id,
                "run": run_number,
                "status": status,
                "final_url": final_url,
                "request_count": 1,
                "pages_requested": 1,
                "record_count": len(normalized),
                "has_next_observed": bool(has_next),
                "raw_response_sha256": hashlib.sha256(body).hexdigest(),
                "inventory_digest": digest([record["source_key"] for record in normalized]),
                "parser_digest": digest(normalized),
                "documents_downloaded": 0,
                "baseline_mutated": False,
            }
            run_ledger.append(row)
            runs.append(row)
            run_dir = args.out / source_id / f"run-{run_number}"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "index.raw").write_bytes(body)
            (run_dir / "records.json").write_text(
                json.dumps(normalized, indent=2, sort_keys=True) + "\n"
            )
        deterministic = (
            runs[0]["inventory_digest"] == runs[1]["inventory_digest"]
            and runs[0]["parser_digest"] == runs[1]["parser_digest"]
        )
        source_certificates[source_id] = {
            "deterministic": deterministic,
            "inventory_digest": runs[0]["inventory_digest"],
            "parser_digest": runs[0]["parser_digest"],
            "records_per_run": [runs[0]["record_count"], runs[1]["record_count"]],
            "requests_used": request_budget[source_id],
            "request_budget": source_config["daily_request_budget"],
        }
        if not deterministic:
            raise SystemExit(f"two-run digest mismatch for {source_id}")

    certificate = {
        "approval_id": approval["approval_id"],
        "approved_by": approval["approved_by"],
        "sources": source_certificates,
        "all_sources_deterministic": all(
            row["deterministic"] for row in source_certificates.values()
        ),
        "documents_downloaded": 0,
        "baseline_mutated": False,
        "linked_binary_fetch": False,
        "automatic_attribution": False,
        "pilot_executed": True,
    }
    outputs = {
        "limited-pilot-run-ledger.json": run_ledger,
        "two-run-reproducibility-certificate.json": certificate,
        "request-budget-ledger.json": request_budget,
    }
    for name, payload in outputs.items():
        (args.out / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(certificate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
