"""Ledger integrity checks for the P0 non-municipal source universe."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

SOURCE_UNIVERSE = ROOT / "data" / "source_universe" / "non_municipal_source_universe_ledger.yaml"
P0_QUEUE = ROOT / "data" / "source_universe" / "p0_source_queue.yaml"
P0_HEALTH = ROOT / "data" / "source_health" / "p0_source_health_ledger.yaml"
ROUTING_POLICY = ROOT / "data" / "routing" / "routing_policy.yaml"
THEHUB_CONTRACT = ROOT / "data" / "routing" / "thehub_run_logging_contract.yaml"

ALLOWED_HEALTH_STATUSES = {"ACTIVE", "DEGRADED", "BLOCKED", "MANUAL_ONLY", "DEMOTE"}


def _load_yaml(path: Path) -> dict:
    assert path.exists(), f"missing ledger: {path}"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), f"expected mapping in {path}"
    return data


def _queued_ids() -> list[str]:
    queue = _load_yaml(P0_QUEUE)
    ids: list[str] = []
    for batch in queue["p0_source_queue"]:
        ids.extend(batch["source_ids"])
    return ids


def test_yaml_ledgers_parse() -> None:
    for path in [SOURCE_UNIVERSE, P0_QUEUE, P0_HEALTH, ROUTING_POLICY, THEHUB_CONTRACT]:
        _load_yaml(path)


def test_source_count_is_64() -> None:
    universe = _load_yaml(SOURCE_UNIVERSE)
    health = _load_yaml(P0_HEALTH)
    queued = _queued_ids()

    assert universe["source_count"] == 64
    assert health["target_count"] == 64
    assert len(queued) == 64
    assert len(set(queued)) == 64


def test_every_source_routes_to_thehub_by_policy() -> None:
    universe = _load_yaml(SOURCE_UNIVERSE)
    assert "thehub-pr" in universe["routing_defaults"]["required_all_sources"]

    routing = _load_yaml(ROUTING_POLICY)
    assert "thehub-pr" in routing["repo_routes"]


def test_health_status_enum_is_constrained() -> None:
    health = _load_yaml(P0_HEALTH)
    observed = set(health["health_status_counts"])
    assert observed == ALLOWED_HEALTH_STATUSES
    assert sum(health["health_status_counts"].values()) == health["target_count"]
    assert health["health_status_counts"]["ACTIVE"] == 52
    assert health["health_status_counts"]["DEGRADED"] == 11
    assert health["health_status_counts"]["MANUAL_ONLY"] == 1


def test_routing_policy_requires_multilabel() -> None:
    routing = _load_yaml(ROUTING_POLICY)
    assert routing["multi_label_required"] is True


def test_thehub_run_log_contract_has_required_run_fields() -> None:
    contract = _load_yaml(THEHUB_CONTRACT)
    schema = contract["run_log_schema"]
    for field in [
        "run_id",
        "started_at",
        "finished_at",
        "sources_checked",
        "items_captured",
        "items_routed",
        "routes_by_repo",
        "failed_sources",
        "gap_flags",
    ]:
        assert field in schema
