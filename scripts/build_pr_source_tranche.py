#!/usr/bin/env python3
"""Freeze and verify the bounded Puerto Rico pre-official source tranche."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from centinelas.ingest.puerto_rico import (  # noqa: E402
    CONFIG_PATH,
    build_receipt,
    capture_all,
    config_state,
    json_bytes,
    load_config,
    snapshot_errors,
    write_bytes_atomic,
)

SCHEMA_PATH = REPO_ROOT / "schemas" / "puerto_rico_source_record.schema.json"


def git_head() -> str | None:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def validate_records(records: list[dict]) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        errors.extend(
            f"record {index}: {error.message}"
            for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path))
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--reuse-receipt",
        help="reuse exact PASS source rows from a self-verifying earlier snapshot",
    )
    parser.add_argument("--verify", action="store_true", help="verify an existing receipt only")
    args = parser.parse_args(argv)

    receipt_path = Path(args.receipt).resolve()
    if args.verify:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        errors = snapshot_errors(receipt)
        print("PASS - snapshot verifies" if not errors else f"FAIL - {errors}")
        return 0 if not errors else 1
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero")

    out = Path(args.out).resolve()
    raw_dir = Path(args.raw_dir).resolve()
    config_path = Path(args.config).resolve()
    if out.exists() or receipt_path.exists() or raw_dir.exists():
        print("FAIL - snapshot paths already exist; refusing to overwrite mutable evidence")
        return 2

    config_before = config_state(config_path)
    config = load_config(config_path)
    raw_dir.mkdir(parents=True)
    started = datetime.now(timezone.utc)
    reused_records: list[dict] = []
    reused_receipts: list[dict] = []
    reused_source_ids: set[str] = set()
    reuse_parent: dict | None = None
    if args.reuse_receipt:
        prior_path = Path(args.reuse_receipt).resolve()
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_errors = snapshot_errors(prior)
        if prior_errors:
            print(f"FAIL - prior snapshot does not verify: {prior_errors}")
            return 2
        prior_config = {
            row["source_registry_id"]: row
            for row in prior.get("source_config", {}).get("before", {}).get("sources", [])
        }
        current_config = {row["source_registry_id"]: row for row in config["sources"]}
        prior_source_rows = {
            row["source_registry_id"]: row for row in prior.get("sources", {}).get("rows", [])
        }
        prior_records = [
            json.loads(line)
            for line in Path(prior["output"]["path"]).read_text(encoding="utf-8").splitlines()
            if line
        ]
        prior_raw_dir = Path(prior["sources"]["raw_directory"])
        for source_id, current_source in current_config.items():
            prior_source = prior_source_rows.get(source_id)
            if (
                prior_config.get(source_id) != current_source
                or not prior_source
                or prior_source.get("status") not in {"SUCCESS_WITH_ROWS", "SUCCESS_EMPTY"}
                or prior_source.get("pagination_complete") is not True
            ):
                continue
            reused_source_ids.add(source_id)
            reused_records.extend(
                record for record in prior_records if record["source_registry_id"] == source_id
            )
            reused_source = copy.deepcopy(prior_source)
            reused_source["reused_from_snapshot"] = {
                "receipt_path": str(prior_path),
                "receipt_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
            }
            reused_receipts.append(reused_source)
            for request in prior_source["requests"]:
                relative = Path(request["raw_content_path"])
                destination = raw_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(prior_raw_dir / relative, destination)
        reuse_parent = {
            "receipt_path": str(prior_path),
            "receipt_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
            "reused_source_ids": sorted(reused_source_ids),
        }

    capture_ids = {source["source_registry_id"] for source in config["sources"]} - reused_source_ids
    fresh_records, fresh_receipts = capture_all(
        config,
        raw_dir=raw_dir,
        captured_at=started,
        timeout_seconds=args.timeout_seconds,
        selected_source_ids=capture_ids,
    )
    all_records = reused_records + fresh_records
    records = [
        record
        for source in config["sources"]
        for record in all_records
        if record["source_registry_id"] == source["source_registry_id"]
    ]
    receipts_by_source = {
        row["source_registry_id"]: row for row in reused_receipts + fresh_receipts
    }
    source_receipts = [
        receipts_by_source[source["source_registry_id"]] for source in config["sources"]
    ]
    write_bytes_atomic(
        out,
        b"".join(json_bytes(record) for record in records),
    )
    schema_errors = validate_records(records)
    config_after = config_state(config_path)
    completed = datetime.now(timezone.utc)
    receipt = build_receipt(
        config_path=config_path,
        config_before=config_before,
        config_after=config_after,
        out=out,
        raw_dir=raw_dir,
        records=records,
        source_receipts=source_receipts,
        repository_head=git_head(),
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        schema_errors=schema_errors,
    )
    receipt["reuse_parent"] = reuse_parent
    receipt["snapshot_mode"] = "COMPOSITE_REUSE_PASSED_SOURCES" if reuse_parent else "FRESH_CAPTURE"
    write_bytes_atomic(receipt_path, json_bytes(receipt, pretty=True))
    print(
        f"{receipt['classification']} - {len(records)} records from "
        f"{len(source_receipts)} source manifestations; receipt={receipt_path}"
    )
    return 0 if receipt["classification"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
