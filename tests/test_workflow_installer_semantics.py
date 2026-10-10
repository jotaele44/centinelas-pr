from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_workflow_installer_semantics.py"
SPEC = importlib.util.spec_from_file_location("installer_semantics", MODULE_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_repository_root_has_uv_sources():
    assert mod.uv_sources(mod.ROOT)


def test_satim_nested_packages_are_negative_controls():
    assert not mod.uv_sources(mod.ROOT / "tools" / "satim_engine")
    assert not mod.uv_sources(mod.ROOT / "tools" / "satim_route_findings")


def test_current_workflows_have_no_installer_semantic_violation():
    assert mod.main() == 0
