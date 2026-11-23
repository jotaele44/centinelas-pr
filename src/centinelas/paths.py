"""Where Centinelas keeps its local pipeline state.

Every module that needs the data folder asks here, so the variable that
chooses it is read in one place. Standard library only: the desktop setup
action imports this before anything else is set up.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Environment variable naming the data folder (queue, classified, dispatched,
#: handoffs, water-disruption state). The desktop runtime sets it to the
#: workspace the user chose.
DATA_DIR_ENV = "CENTINELAS_DATA_DIR"


def data_dir(default: str | os.PathLike[str]) -> Path:
    """The data folder: ``CENTINELAS_DATA_DIR`` when set, else ``default``.

    Callers pass their own default because they differ today: the backend and
    the desktop seed use ``<repo>/.centinelas``, the dispatcher and the
    water-disruption API ``.centinelas`` relative to the working directory.
    Like ``os.environ.get(name, default)``, a variable that is set but empty
    is kept as is, which ``Path`` reads as the current directory.
    """
    return Path(os.environ.get(DATA_DIR_ENV, os.fspath(default)))
