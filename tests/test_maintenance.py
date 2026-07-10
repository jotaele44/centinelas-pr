"""Shared-package wiring smoke test for centinelas-pr's maintenance shim.

Generic detection/runner behavior lives in thehub-pr's shared
`prii_maintenance` package (thehub-pr/packages/prii_maintenance/tests/); this
just proves scripts/run_maintenance.py's dependency-injection wiring
(`prii_maintenance.run_maintenance(..., local_checks=local.run_checks)`)
actually reaches this repo's adapter.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from prii_maintenance import run_maintenance

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from maintenance.adapters import local  # noqa: E402

TARGETS = ("aguayluz", "moneysweep", "spiderweb", "ovnis", "skywatcher", "thehub")

GOOD_ROW = {
    "signal_id": "CENT-SIG-test", "matter_id": "CENT-MAT-test",
    "signal_type": "unclassified_signal", "title": "test signal",
    "source_id": "CENT-SRC-TEST", "captured_at": "2026-07-01T00:00:00Z",
    "signal_stage": "raw_observation", "beat": "unclassified",
    "confidence_score": 30.0, "evidence_tier": "T1", "is_synthetic": True,
}


def _seed_repo(tmp_path, ledger_lines):
    contracts = tmp_path / "src/centinelas/route/contracts"
    contracts.mkdir(parents=True)
    for target in TARGETS:
        (contracts / f"{target}.schema.json").write_text(
            json.dumps({"type": "object"}), encoding="utf-8"
        )
    schema = json.loads((REPO_ROOT / "schemas/signal.schema.json").read_text(encoding="utf-8"))
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas/signal.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    fed = {
        "program_id": "centinelas-pr",
        "hub_parent": "thehub-pr",
        "domain_routing": {
            "ENVIRONMENTAL": "aguayluz-pr",
            "FINANCIAL": "moneysweep-pr",
            "GEO_GEOLOGY": "spiderweb-pr",
            "ANOMALOUS": "ovnis-pr",
            "MILITARY_AEROSPACE": "skywatcher-pr",
        },
        "canonical_outputs": {
            "signal_schema": "schemas/signal.schema.json",
            "live_ledger": "data/signals/live_signals.jsonl",
        },
    }
    (tmp_path / "federation.json").write_text(json.dumps(fed), encoding="utf-8")
    ledger = tmp_path / "data/signals/live_signals.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("".join(line + "\n" for line in ledger_lines), encoding="utf-8")


def _run(tmp_path):
    return run_maintenance(
        root=tmp_path,
        mode="audit",
        write=False,
        program_id="centinelas-pr",
        local_checks=local.run_checks,
    )


def test_clean_repo_reports_clean(tmp_path):
    _seed_repo(tmp_path, [json.dumps(GOOD_ROW)])
    report = _run(tmp_path)
    assert report.findings == []
    assert report.promotion_blocked is False


def test_corrupt_ledger_line_fires_local_finding(tmp_path):
    _seed_repo(tmp_path, [json.dumps(GOOD_ROW), '{"signal_id": "CENT-SIG-broken",'])
    report = _run(tmp_path)
    assert any(
        f.category == "schema" and f.severity == "error" and f.action == "quarantined"
        for f in report.findings
    )


def test_missing_required_field_fires_local_finding(tmp_path):
    row = {k: v for k, v in GOOD_ROW.items() if k != "matter_id"}
    _seed_repo(tmp_path, [json.dumps(row)])
    report = _run(tmp_path)
    assert any(
        f.category == "schema" and (f.detail or {}).get("missing") == ["matter_id"]
        for f in report.findings
    )


def test_missing_routing_contract_fires_local_finding(tmp_path):
    _seed_repo(tmp_path, [json.dumps(GOOD_ROW)])
    (tmp_path / "src/centinelas/route/contracts/thehub.schema.json").unlink()
    report = _run(tmp_path)
    assert any(
        f.category == "manifest" and (f.detail or {}).get("target") == "thehub-pr"
        for f in report.findings
    )
