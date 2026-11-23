"""The data folder is resolved in one place: centinelas.paths.data_dir."""

import re
from pathlib import Path

from centinelas import paths

ROOT = Path(__file__).resolve().parents[1]


def test_default_when_the_variable_is_unset(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
    assert paths.data_dir(tmp_path / ".centinelas") == tmp_path / ".centinelas"
    assert paths.data_dir(".centinelas") == Path(".centinelas")


def test_the_variable_wins_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "workspace"))
    assert paths.data_dir(".centinelas") == tmp_path / "workspace"


def test_an_empty_variable_behaves_as_before(monkeypatch):
    # Same as os.environ.get(name, default): set-but-empty is kept, and
    # Path("") is the current directory. Unchanged by the move to one place.
    monkeypatch.setenv(paths.DATA_DIR_ENV, "")
    assert paths.data_dir(".centinelas") == Path("")


def test_no_module_reads_the_variable_directly():
    # A new reader should call data_dir() instead of os.environ, so the folder
    # keeps one definition. desktop/config.py only names the variable for the
    # desktop runtime and is allowed to.
    reads = re.compile(r"environ(?:\.get)?\(\s*[\"']CENTINELAS_DATA_DIR|environ\[\s*[\"']CENTINELAS_DATA_DIR")
    offenders = [
        str(path.relative_to(ROOT))
        for top in ("src", "server", "desktop", "scripts")
        for path in (ROOT / top).rglob("*.py")
        if path.name != "paths.py" and reads.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []
