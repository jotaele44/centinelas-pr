#!/usr/bin/env python3
"""Export validated space-data leads as Hub-compatible observations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from centinelas.space_discovery import (  # noqa: E402
    enrich_federation_attributes,
    sha256_bytes,
    validate_lead,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    leads = [
        json.loads(line)
        for line in Path(args.ledger).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for lead in leads:
        validate_lead(lead)
        rows.append({
            "observation_id": "obs_" + lead["content_fingerprint"][:32],
            "entity_id": "ent_" + sha256_bytes(lead["lead_id"].encode())[:32],
            "source_id": "src_" + sha256_bytes(lead["source_id"].encode())[:32],
            "observation_type": "space_data_discovery",
            "observed_at": lead["discovered_at"],
            "attributes": {
                "signal_id": lead["lead_id"],
                "title": lead["title"],
                "source_url": lead["source_url"],
                **enrich_federation_attributes(lead),
            },
            "confidence": lead["confidence_score"] / 100.0,
            "lineage": {
                "producer_script": "scripts/federation_export_space.py",
                "producer_phase": "SPACE_DATA_DISCOVERY",
                "source_inputs": [args.ledger],
                "extraction_method": "validated_space_lead_projection",
            },
            "synthetic": False,
            "created_at": lead["discovered_at"],
            "extracted_at": lead["last_verified_at"],
        })
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    (out / "observations.jsonl").write_text(payload, encoding="utf-8")
    manifest = {
        "producer": "centinelas-pr",
        "mode": "production",
        "record_count": len(rows),
        "sha256": sha256_bytes(payload.encode()),
        "space_contract_version": "1.0.0",
    }
    (out / "space_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
