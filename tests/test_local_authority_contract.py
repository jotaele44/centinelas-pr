from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_SHA = "2a8b662262130fc9013a7bc5016a6c74117e8c4a"
WORKFLOWS = (
    ".github/workflows/dispatch-signals.yml",
    ".github/workflows/dispatch-signals-ovnis.yml",
    ".github/workflows/dispatch-signals-aguayluz.yml",
)
DYNAMIC_GATES = {
    "CLEAN_CACHE_INSTALL",
    "NETWORK_DENY_STARTUP",
    "ALLOWLIST_ONLY_CONNECTOR_RUN",
    "NO_SECRET_STARTUP",
    "PACKAGED_RELEASE_EGRESS_CAPTURE",
    "POSTINSTALL_BINARY_CAPTURE",
    "OFFLINE_CORE_BROWSE_ANALYZE_EXPORT",
    "OFFLINE_REBUILD_FROM_LOCAL_DEPENDENCY_BYTES",
}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _top_level_import_roots(path: str) -> set[str]:
    tree = ast.parse(_read(path), filename=path)
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_anthropic_is_optional_not_core() -> None:
    text = _read("pyproject.toml")
    project = text.split("[project]", 1)[1].split("[tool.uv.sources]", 1)[0]
    dependencies = project.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert "anthropic" not in dependencies.lower()
    hosted = text.split("hosted-classifier = [", 1)[1].split("]", 1)[0]
    assert re.search(r"anthropic\s*>=", hosted)


def test_shared_transport_is_pinned_to_exact_policy_child() -> None:
    pyproject = _read("pyproject.toml")
    desktop = _read("requirements-desktop.txt")
    expected = f"thehub-pr/archive/{IMPLEMENTATION_SHA}.zip"
    assert expected in pyproject
    assert expected in desktop
    assert "prii-export-utils" in pyproject
    assert "prii-export-utils" in desktop
    assert "@main" not in pyproject
    assert "@main" not in desktop


def test_application_dispatch_has_no_hosted_network_client() -> None:
    path = "src/centinelas/route/dispatch.py"
    source = _read(path)
    assert _top_level_import_roots(path).isdisjoint({"urllib", "requests", "httpx"})
    assert "repository_dispatch" not in source
    assert "FEDERATION_DISPATCH_TOKEN" not in source
    assert "CENTINELAS_GITHUB_TOKEN" not in source
    assert "emit_message" in source


def test_hosted_emitter_is_exact_mirror_not_payload_rewriter() -> None:
    source = _read("scripts/emit_dispatches.py")
    assert "build_mirror_payload" in source
    assert "verify_mirror_payload" in source
    assert "centinelas-artifact-mirror" in source
    assert "_bounded_signal" not in source
    assert "_TRUNCATION_MARKER" not in source
    assert "truncated" not in source.lower()


def test_dispatch_workflows_default_to_local_and_stage_before_mirror() -> None:
    for path in WORKFLOWS:
        source = _read(path)
        assert 'default: "local"' in source, path
        assert "CENTINELAS_EXCHANGE_ROOT" in source, path
        assert "CENTINELAS_OUTBOUND_DIR" not in source, path
        assert "commit local outbox authority" in source, path
        assert "optional" in source.lower(), path
        assert "--exchange-root" in source, path
        assert 'CLASSIFIER_BACKEND" == "anthropic"' in source, path


def test_validation_workflow_is_read_only_and_lock_drift_fails_closed() -> None:
    source = _read(".github/workflows/validate.yml")
    assert "permissions:\n  contents: read" in source
    assert "contents: write" not in source
    assert "git push" not in source
    assert "uv lock" in source
    assert "git diff --exit-code -- uv.lock" in source


def test_manifest_preserves_provisional_eight_gate_ceiling() -> None:
    manifest = json.loads(_read("federation.json"))
    gate = manifest["federation_freedom_gate"]
    assert gate["policy_pr"] == "Jotaele44/thehub-pr#246"
    assert gate["implementation_pr"] == "Jotaele44/thehub-pr#260"
    assert gate["implementation_sha"] == IMPLEMENTATION_SHA
    assert gate["certified"] is False
    assert gate["certification_state"] == "PROVISIONAL"
    assert set(gate["dynamic_gates"]) == DYNAMIC_GATES
    assert set(gate["dynamic_gates"].values()) == {"OPEN"}
    assert manifest["federation_readiness_gate"]["ready_for_hub_live_execution"] is False
