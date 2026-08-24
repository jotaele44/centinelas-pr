#!/usr/bin/env python3
"""Fail-closed certification checks for the Centinelas shadow water pipeline."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    schema_path = ROOT / "schemas/water-disruption/v0.1/centinelas-water-candidate.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    truth_state = schema["$defs"]["candidate"]["properties"]["truth_state"]
    require(truth_state == {"const": "candidate"}, "schema permits non-candidate truth state")

    producer_path = ROOT / "src/centinelas/water_disruption.py"
    api_path = ROOT / "server/backend/water_disruption_api.py"
    main_path = ROOT / "server/backend/main.py"
    for path in (producer_path, api_path, main_path):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    producer = producer_path.read_text(encoding="utf-8")
    api = api_path.read_text(encoding="utf-8")
    mounted = main_path.read_text(encoding="utf-8")
    require('"truth_state": "candidate"' in producer, "candidate truth-state guard missing")
    require('"notifications_enabled": False' in producer, "producer notifications guard missing")
    require('"production_promotion_enabled": False' in producer, "promotion guard missing")
    require('"X-Shadow-Mode": "true"' in api, "shadow transport header missing")
    require("app.include_router(water_disruption_router)" in mounted, "producer router not mounted")
    require("incomplete_source_accounting" in producer, "100% source-accounting gate missing")
    print("CENTINELAS_WATER_SHADOW_CERTIFICATION=PASS")


if __name__ == "__main__":
    main()
