"""Where Centinelas keeps its local pipeline data.

Every module that reads or writes ``.centinelas/`` resolves the folder here, so
they all agree on it and all apply the same check.

``CENTINELAS_DATA_DIR`` chooses the folder. It is accepted only inside one of
the allowed roots: the user's home folder, this repository, or any absolute
folder listed in ``CENTINELAS_DATA_ROOTS`` (separated by ``os.pathsep``, so
``:`` on macOS and Linux and ``;`` on Windows). Symlinks are resolved before the
check, so a link inside home that points elsewhere is judged by its target.

Unset, the folder is ``<repository>/.centinelas`` whatever the current
directory is.

Standard library only: the desktop launcher imports this before the
application's own environment exists.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

DATA_ENV_VAR = "CENTINELAS_DATA_DIR"
ROOTS_ENV_VAR = "CENTINELAS_DATA_ROOTS"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / ".centinelas"


class DataDirNotAllowed(ValueError):
    """CENTINELAS_DATA_DIR points outside every allowed root."""


def _real(path: str) -> str:
    return os.path.normpath(os.path.realpath(os.path.expanduser(path)))


def allowed_roots(env: Mapping[str, str] | None = None) -> list[str]:
    """The folders a data directory may sit in, resolved."""
    env = os.environ if env is None else env
    roots = [_real("~"), _real(str(REPO_ROOT))]
    for entry in (env.get(ROOTS_ENV_VAR) or "").split(os.pathsep):
        entry = entry.strip()
        if entry and os.path.isabs(os.path.expanduser(entry)):
            roots.append(_real(entry))
    return list(dict.fromkeys(roots))


def data_dir(env: Mapping[str, str] | None = None) -> Path:
    """The data directory, after checking it against the allowed roots.

    Raises DataDirNotAllowed when CENTINELAS_DATA_DIR is outside all of them.
    """
    env = os.environ if env is None else env
    value = (env.get(DATA_ENV_VAR) or "").strip()
    if not value:
        return DEFAULT_DATA_DIR
    # Normalise, then test the normalised value itself with startswith: that
    # shape is what static analysers (CodeQL py/path-injection) recognise as a
    # containment check. The character after the root must end the path or be a
    # separator, so "/home/a-other" is not inside "/home/a".
    candidate = os.path.normpath(os.path.realpath(os.path.expanduser(value)))
    roots = allowed_roots(env)
    for root in roots:
        base = root.rstrip(os.sep)
        if candidate.startswith(base) and candidate[len(base) : len(base) + 1] in ("", os.sep):
            return Path(candidate)
    ignored = [
        e.strip()
        for e in (env.get(ROOTS_ENV_VAR) or "").split(os.pathsep)
        if e.strip() and not os.path.isabs(os.path.expanduser(e.strip()))
    ]
    raise DataDirNotAllowed(
        f"{DATA_ENV_VAR}={value!r} resolves to {candidate}, which is outside the allowed "
        f"folders: {', '.join(roots)}. Move the data folder under one of them, or add its "
        f"parent folder to {ROOTS_ENV_VAR} (absolute paths, separated by {os.pathsep!r})."
        + (
            f" Ignored relative entries in {ROOTS_ENV_VAR}: {', '.join(ignored)}."
            if ignored
            else ""
        )
    )
