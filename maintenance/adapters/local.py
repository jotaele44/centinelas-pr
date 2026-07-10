"""Centinelas-specific maintenance checks.

- check_signal_ledger_integrity: every line of the seed/live signal ledgers
  must parse as a JSON object and carry the fields the signal schema
  (schemas/signal.schema.json) declares as required.
- check_routing_contracts: every federation routing target (the domain_routing
  repos plus hub_parent) must have a present, parseable contract schema under
  src/centinelas/route/contracts/.

Read-only and audit-first; problems are quarantined, never auto-corrected.
"""
from __future__ import annotations

import json
from pathlib import Path

from prii_maintenance import MaintenanceFinding

LEDGER_KEYS = ("seed_ledger", "live_ledger")
CONTRACTS_DIR = "src/centinelas/route/contracts"


def _required_signal_fields(root: Path, state: dict) -> tuple[str, ...]:
    rel = state["canonical_outputs"].get("signal_schema")
    if not isinstance(rel, str):
        return ()
    path = root / rel
    if not path.exists():
        return ()
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ()
    required = schema.get("required", [])
    return tuple(f for f in required if isinstance(f, str))


def _ledger_paths(root: Path, state: dict) -> list[tuple[str, Path]]:
    outputs = state["canonical_outputs"]
    return [
        (key, root / outputs[key])
        for key in LEDGER_KEYS
        if isinstance(outputs.get(key), str)
    ]


def check_signal_ledger_integrity(repo: str, root: Path, state: dict) -> list[MaintenanceFinding]:
    findings: list[MaintenanceFinding] = []
    required = _required_signal_fields(root, state)
    for key, path in _ledger_paths(root, state):
        if not path.exists():
            continue
        rel = str(path.relative_to(root))
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                findings.append(
                    MaintenanceFinding(
                        finding_id=f"{repo}:schema:{key}_line_{i}",
                        repo=repo,
                        category="schema",
                        severity="error",
                        action="quarantined",
                        message="signal ledger line is not valid JSON",
                        path=rel,
                        detail={"ledger": key, "line": i + 1},
                    )
                )
                continue
            if not isinstance(row, dict):
                findings.append(
                    MaintenanceFinding(
                        finding_id=f"{repo}:schema:{key}_line_{i}",
                        repo=repo,
                        category="schema",
                        severity="error",
                        action="quarantined",
                        message="signal ledger line is not a JSON object",
                        path=rel,
                        detail={"ledger": key, "line": i + 1},
                    )
                )
                continue
            missing = [f for f in required if f not in row]
            if missing:
                rid = row.get("signal_id", i)
                findings.append(
                    MaintenanceFinding(
                        finding_id=f"{repo}:schema:{key}_missing_{rid}",
                        repo=repo,
                        category="schema",
                        severity="error",
                        action="quarantined",
                        message="signal row missing required schema fields",
                        path=rel,
                        detail={"ledger": key, "signal_id": rid, "missing": missing},
                    )
                )
    return findings


def _routing_targets(state: dict) -> list[str]:
    fed = state["federation"]
    targets = {t for t in fed.get("domain_routing", {}).values() if isinstance(t, str)}
    hub = fed.get("hub_parent")
    if isinstance(hub, str):
        targets.add(hub)
    return sorted(targets)


def check_routing_contracts(repo: str, root: Path, state: dict) -> list[MaintenanceFinding]:
    findings: list[MaintenanceFinding] = []
    for target in _routing_targets(state):
        rel = f"{CONTRACTS_DIR}/{target.removesuffix('-pr')}.schema.json"
        path = root / rel
        if not path.exists():
            findings.append(
                MaintenanceFinding(
                    finding_id=f"{repo}:manifest:contract_{target}",
                    repo=repo,
                    category="manifest",
                    severity="error",
                    action="none",
                    message=f"routing contract missing for federation target {target}",
                    path=rel,
                    detail={"target": target},
                )
            )
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                MaintenanceFinding(
                    finding_id=f"{repo}:schema:contract_{target}",
                    repo=repo,
                    category="schema",
                    severity="error",
                    action="quarantined",
                    message=f"routing contract for {target} is not valid JSON: {exc}",
                    path=rel,
                    detail={"target": target},
                )
            )
    return findings


CHECKS = (check_signal_ledger_integrity, check_routing_contracts)


def run_checks(repo: str, root: Path, state: dict) -> list[MaintenanceFinding]:
    findings: list[MaintenanceFinding] = []
    for check in CHECKS:
        findings.extend(check(repo, root, state))
    return findings
