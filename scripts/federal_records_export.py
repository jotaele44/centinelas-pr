#!/usr/bin/env python3
"""Export adjudicated federal-record data without touching the signal exporter."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prii_export_utils import sha256

STREAM_SCHEMA = {
    "federal_documents": "federation_federal_document.schema.json",
    "federal_document_releases": "federation_federal_document_release.schema.json",
    "document_findings": "federation_document_finding.schema.json",
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def export_package(input_dir: Path, out_dir: Path, mode: str, now: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    for stream, schema in STREAM_SCHEMA.items():
        rows = load_jsonl(input_dir / f"{stream}.jsonl")
        if not rows:
            continue
        if mode == "production" and any(row.get("synthetic") for row in rows):
            raise ValueError(f"synthetic rows are forbidden in production stream {stream}")
        target = out_dir / f"{stream}.jsonl"
        target.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        files.append({
            "filename": target.name,
            "stream": stream,
            "record_count": len(rows),
            "sha256": sha256(target),
            "schema_id": schema,
        })
    if not files:
        raise ValueError("no federal-record rows found")
    digest_input = "|".join(f"{entry['filename']}:{entry['sha256']}" for entry in files)
    package_id = "pkg_" + hashlib.sha256(f"{digest_input}|{mode}".encode()).hexdigest()[:32]
    manifest = {
        "package_id": package_id,
        "producer": "centinelas-pr",
        "export_contract_version": "1.1.0",
        "mode": mode,
        "created_at": now,
        "extracted_at": now,
        "federation": {
            "producer_repo": "centinelas-pr",
            "hub_parent": "thehub-pr",
            "contract": "federal-records-v1",
        },
        "files": files,
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/releases/adjudicated")
    parser.add_argument("--out", default="exports/federal-records")
    parser.add_argument("--mode", choices=["test", "production"], default="test")
    args = parser.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    print(export_package(Path(args.input), Path(args.out), args.mode, now))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
