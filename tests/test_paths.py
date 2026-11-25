"""Tests for the shared data-directory resolver (centinelas.paths)."""

import os
from pathlib import Path

import pytest

from centinelas import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home folder, so the tests do not depend on the real one."""
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))
    monkeypatch.setenv("USERPROFILE", str(fake))
    return fake


def real(path) -> Path:
    return Path(os.path.realpath(path))


def test_unset_is_the_repository_folder(home):
    assert paths.data_dir({}) == paths.REPO_ROOT / ".centinelas"
    assert paths.data_dir({paths.DATA_ENV_VAR: "  "}) == paths.REPO_ROOT / ".centinelas"


def test_inside_home_is_accepted(home):
    target = home / "centinelas-data"
    assert paths.data_dir({paths.DATA_ENV_VAR: str(target)}) == real(target)


def test_tilde_is_expanded(home):
    assert paths.data_dir({paths.DATA_ENV_VAR: "~/data"}) == real(home / "data")


def test_inside_repository_is_accepted(home):
    target = paths.REPO_ROOT / ".centinelas-test"
    assert paths.data_dir({paths.DATA_ENV_VAR: str(target)}) == real(target)


def test_home_itself_is_accepted(home):
    assert paths.data_dir({paths.DATA_ENV_VAR: str(home)}) == real(home)


def test_outside_every_root_is_refused(home, tmp_path):
    outside = tmp_path / "elsewhere"
    with pytest.raises(paths.DataDirNotAllowed) as caught:
        paths.data_dir({paths.DATA_ENV_VAR: str(outside)})
    assert paths.ROOTS_ENV_VAR in str(caught.value)


def test_sibling_with_shared_prefix_is_refused(home):
    # "<home>-other" starts with the home path as a string but is not inside it.
    sibling = Path(str(home) + "-other") / "data"
    with pytest.raises(paths.DataDirNotAllowed):
        paths.data_dir({paths.DATA_ENV_VAR: str(sibling)})


def test_listed_root_is_accepted(home, tmp_path):
    root = tmp_path / "external"
    target = root / "centinelas"
    env = {
        paths.DATA_ENV_VAR: str(target),
        paths.ROOTS_ENV_VAR: os.pathsep.join(["/nonexistent", str(root)]),
    }
    assert paths.data_dir(env) == real(target)


def test_relative_listed_root_is_ignored(home, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = {paths.DATA_ENV_VAR: str(tmp_path / "rel" / "data"), paths.ROOTS_ENV_VAR: "rel"}
    with pytest.raises(paths.DataDirNotAllowed) as caught:
        paths.data_dir(env)
    assert "Ignored relative entries" in str(caught.value)


def test_symlink_inside_home_to_outside_is_refused(home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = home / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(paths.DataDirNotAllowed):
        paths.data_dir({paths.DATA_ENV_VAR: str(link / "data")})
