#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from centinelas.releases.pilot import load_manifest, readiness_certificate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/federal_records_source_enablement.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("pilot-output/pilot-readiness-certificate.json"),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Reserved for an explicitly approved metadata-only pilot.",
    )
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    certificate = readiness_certificate(manifest)
    certificate.update(
        {
            "generated_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "documents_downloaded": 0,
            "baseline_mutated": False,
            "live_collection_executed": False,
        }
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n")
    print(json.dumps(certificate, indent=2, sort_keys=True))
    if args.execute:
        if not certificate["pilot_ready"]:
            raise SystemExit("pilot execution denied: readiness gate is closed")
        raise SystemExit(
            "pilot execution remains intentionally unimplemented until explicit owner approval"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
