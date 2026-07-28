#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from centinelas.releases.pilot import load_manifest, readiness_certificate
from centinelas.releases.source_endpoints import SOURCE_ENDPOINTS
from run_federal_records_canaries import SourceCanary, canonical_digest, run_source

REMEDIATION_SCOPE = (
    "nsa_releases",
    "nhhc",
    "doe_aec",
    "nara_ndc",
    "dia_reading_room",
    "air_force_blue_book",
)


def _source(adapter_id: str) -> SourceCanary:
    row = SOURCE_ENDPOINTS[adapter_id]
    return SourceCanary(row.adapter_id, row.index_url, row.robots_url, row.policy_url)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("remediation-output"))
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/federal_records_source_enablement.json"),
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    results = []
    for adapter_id in REMEDIATION_SCOPE:
        try:
            result = run_source(
                _source(adapter_id),
                args.out,
                delay=args.delay,
                timeout=args.timeout,
            )
        except Exception as exc:
            result = {
                "adapter_id": adapter_id,
                "deterministic": False,
                "failures": [{"class": type(exc).__name__, "detail": str(exc)}],
                "recommendation": "DISABLE",
                "documents_downloaded": 0,
                "baseline_mutated": False,
            }
        result["remediation_note"] = SOURCE_ENDPOINTS[adapter_id].remediation_note
        results.append(result)

    manifest = load_manifest(args.manifest)
    readiness = readiness_certificate(manifest)
    readiness.update(
        {
            "documents_downloaded": 0,
            "baseline_mutated": False,
            "live_collection_executed": False,
            "owner_approval_granted": False,
        }
    )
    certificate = {
        "scope": list(REMEDIATION_SCOPE),
        "ledger_digest": canonical_digest(results),
        "documents_downloaded": 0,
        "baseline_mutated": False,
        "pilot_ready": readiness["pilot_ready"],
        "all_sources_deterministic": all(row.get("deterministic") for row in results),
    }
    policy_ledger = [
        {
            "adapter_id": row["adapter_id"],
            "policy_runs": row.get("policy_runs", []),
            "recommendation": row.get("recommendation"),
            "remediation_note": row.get("remediation_note"),
        }
        for row in results
    ]
    outputs = {
        "remediation-ledger.json": results,
        "manual-policy-review-ledger.json": policy_ledger,
        "pilot-readiness-certificate.json": readiness,
        "two-run-remediation-certificate.json": certificate,
    }
    for name, payload in outputs.items():
        (args.out / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(certificate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
