"""Centinelas's Launch Pad declaration (desktop/config.py).

The screen itself lives in the shared prii_desktop runtime; these tests keep the
declaration true to this repository. They skip when the installed runtime
predates the Launch Pad.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

launchpad = pytest.importorskip("prii_desktop.launchpad")

from prii_desktop import DesktopConfig  # noqa: E402

from desktop import config  # noqa: E402

ROOT = Path(config.REPO_ROOT)


def _spec():
    return launchpad.launchpad_spec(DesktopConfig.from_module(config))


def test_declaration_is_valid_and_leaves_the_write_guard_alone():
    spec = _spec()
    assert spec is not None and spec.has_modes
    # Operator must not set or replace CENTINELAS_WRITE_TOKEN: the frontend
    # sends no credential, and write authorization is not a user toggle.
    assert spec.operator.token_env is None
    assert "CENTINELAS_WRITE_TOKEN" not in {option.env for option in spec.options}


def test_start_pages_are_real_routes():
    routes = (ROOT / "frontend/src/App.jsx").read_text()
    for page in _spec().start_pages:
        assert f'path="{page.route}"' in routes, page.route


def test_a_guest_is_allowed_no_post_because_every_post_writes():
    spec = _spec()
    assert spec.guest_allow == ()
    sources = "\n".join(
        (ROOT / "server/backend" / name).read_text()
        for name in ("main.py", "water_disruption_api.py")
    )
    writes = re.findall(r"@(?:app|router)\.(post|put|patch|delete)\(", sources)
    # A new non-GET route must be classified: a read-only one needs an allow
    # entry, otherwise this count is simply updated.
    assert writes == ["post"] * 6, writes


def test_options_bind_variables_the_code_reads():
    code = "\n".join(
        (ROOT / "src/centinelas" / name).read_text()
        for name in ("route/dispatch.py", "classify/classifier.py")
    )
    for option in _spec().options:
        assert f'"{option.env}"' in code, option.env


def test_status_counts_the_selected_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(config.DATA_ENV_VAR, str(tmp_path))
    empty = {row["label"]: row for row in config._launchpad_status()}
    assert empty["Classified signals"]["value"] == "Empty"
    assert list(tmp_path.iterdir()) == []  # a readiness check creates nothing

    for stage, names in {"classified": ("a", "b"), "queue": ("c",), "handoffs": ("h",)}.items():
        (tmp_path / stage).mkdir()
        for name in names:
            (tmp_path / stage / f"{name}.json").write_text("{}")
    (tmp_path / ".seeded").write_text("")
    rows = {row["label"]: row for row in config._launchpad_status()}
    assert rows["Classified signals"]["value"] == "2"
    assert "committed signal ledger" in rows["Classified signals"]["detail"]
    assert rows["Waiting in queue"]["status"] == "warn"
    assert rows["Routed and handed off"]["value"] == "0 routed, 1 handoffs"
