"""Regression tests for the shared desktop dependency preflight."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop import setup


class HubSiblingPreflightTests(unittest.TestCase):
    def configure_paths(self, root: Path) -> Path:
        sibling = root / "thehub-pr"
        package = sibling / "packages" / "prii_desktop"
        pyproject = package / "pyproject.toml"
        self.stack.enter_context(mock.patch.object(setup, "HUB_SIBLING", sibling))
        self.stack.enter_context(mock.patch.object(setup, "HUB_DESKTOP_PACKAGE", package))
        self.stack.enter_context(mock.patch.object(setup, "HUB_DESKTOP_PYPROJECT", pyproject))
        return pyproject

    def setUp(self) -> None:
        self.stack = unittest.mock.ExitStack() if hasattr(unittest.mock, "ExitStack") else None
        # ExitStack lives in contextlib; use a patcher list for Python 3.10 compatibility.
        self.patchers = []

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()

    def patch_path(self, name: str, value: Path) -> None:
        patcher = mock.patch.object(setup, name, value)
        patcher.start()
        self.patchers.append(patcher)

    def paths(self, root: Path) -> Path:
        sibling = root / "thehub-pr"
        package = sibling / "packages" / "prii_desktop"
        pyproject = package / "pyproject.toml"
        self.patch_path("HUB_SIBLING", sibling)
        self.patch_path("HUB_DESKTOP_PACKAGE", package)
        self.patch_path("HUB_DESKTOP_PYPROJECT", pyproject)
        return pyproject

    def test_fresh_sibling_is_cloned_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pyproject = self.paths(Path(directory))

            def fake_run(command, cwd=None, env=None):
                self.assertIn("clone", command)
                pyproject.parent.mkdir(parents=True)
                pyproject.write_text("[project]\nname = \"prii-desktop\"\n", encoding="utf-8")

            with mock.patch.object(setup.shutil, "which", return_value="/usr/bin/git"), mock.patch.object(setup, "run", side_effect=fake_run):
                setup.ensure_hub_sibling()

    def test_missing_checkout_without_git_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.paths(Path(directory))
            with mock.patch.object(setup.shutil, "which", return_value=None):
                with self.assertRaisesRegex(SystemExit, "git not found"):
                    setup.ensure_hub_sibling()

    def test_stale_sibling_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pyproject = self.paths(Path(directory))
            pyproject.parents[2].mkdir(parents=True)
            with mock.patch.object(setup, "run") as run:
                with self.assertRaisesRegex(SystemExit, "stale"):
                    setup.ensure_hub_sibling()
                run.assert_not_called()

    def test_valid_sibling_passes_without_git_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pyproject = self.paths(Path(directory))
            pyproject.parent.mkdir(parents=True)
            pyproject.write_text("[project]\nname = \"prii-desktop\"\n", encoding="utf-8")
            with mock.patch.object(setup, "run") as run:
                setup.ensure_hub_sibling()
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
