#!/usr/bin/env python3
"""Fail when a workflow installs a uv-source package root with plain pip editable install."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

WORKING_DIR_RE = re.compile(r'''^\\s*working-directory:\\s*["']?([^"'#]+)''', re.MULTILINE)
EDITABLE_RE = re.compile(r'''(?:python\\s+-m\\s+)?pip\\s+install\\b[^\\n]*\\s-e\\s+(["']?)([^\\s"']+)\\1''')
UV_EDITABLE_RE = re.compile(r"uv\s+pip\s+install\b[^\n]*\s-e\s+")


def uv_sources(package_root: Path) -> bool:
    pyproject = package_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return bool(data.get("tool", {}).get("uv", {}).get("sources", {}))


def candidate_roots(text: str) -> set[Path]:
    roots: set[Path] = set()
    default_dirs = [m.group(1).strip() for m in WORKING_DIR_RE.finditer(text)]
    for match in EDITABLE_RE.finditer(text):
        if UV_EDITABLE_RE.search(match.group(0)):
            continue
        target = match.group(2)
        if not target.startswith("."):
            continue
        roots.add(ROOT)
        for rel in default_dirs:
            root = (ROOT / rel).resolve()
            try:
                root.relative_to(ROOT.resolve())
            except ValueError:
                continue
            roots.add(root)
    return roots


def main() -> int:
    failures: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        text = workflow.read_text(encoding="utf-8")
        if not EDITABLE_RE.search(text):
            continue
        for package_root in sorted(candidate_roots(text)):
            if uv_sources(package_root):
                rel = package_root.relative_to(ROOT)
                label = "." if str(rel) == "." else rel.as_posix()
                failures.append(
                    f"{workflow.relative_to(ROOT)}: plain pip editable install may bypass "
                    f"[tool.uv.sources] for PACKAGE_ROOT={label}"
                )
    if failures:
        print("DEPENDENCY_RESOLUTION installer-semantic violations:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("installer-semantic gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
