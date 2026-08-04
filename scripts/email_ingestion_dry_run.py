#!/usr/bin/env python3
"""Parse a local RFC822 fixture without network access or mailbox writes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from centinelas.ingest.email import normalize_rfc822, parse_google_alert_results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--account-alias", default="offline_fixture")
    parser.add_argument("--source-profile", default="google_alerts_primary")
    args = parser.parse_args()
    raw = args.fixture.read_bytes()
    record = normalize_rfc822(
        raw,
        account_alias=args.account_alias,
        source_profile_id=args.source_profile,
        run_id="dry-run",
        provider_message_id=f"fixture:{args.fixture.name}",
        fetched_at=datetime.now(timezone.utc),
    )
    results = parse_google_alert_results(record)
    output = {
        "mode": "dry_run",
        "network_accessed": False,
        "mailbox_modified": False,
        "federation_export_allowed": False,
        "message": record.model_dump(mode="json", exclude={"text_plain", "text_html", "sanitized_text", "recipients_to", "recipients_cc"}),
        "results": [item.model_dump(mode="json") for item in results],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
