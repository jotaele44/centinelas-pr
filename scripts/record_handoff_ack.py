#!/usr/bin/env python3
"""Persist an idempotent downstream handoff acknowledgment."""
import hashlib
import json
import os
from pathlib import Path

ack = json.loads(os.environ["CENTINELAS_ACK"])
required = {"item_id", "target", "idempotency_key", "status", "duplicate"}
missing = required - ack.keys()
if missing:
    raise SystemExit(f"ack missing fields: {sorted(missing)}")
key_hash = hashlib.sha256(ack["idempotency_key"].encode()).hexdigest()
path = Path("data/handoff_receipts") / f"{key_hash}.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(ack, indent=2, sort_keys=True) + "\n", encoding="utf-8")
