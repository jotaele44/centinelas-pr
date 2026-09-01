# Run Centinelas as a desktop app

Double-click the launcher for your system in the repo root:

| System | File |
|---|---|
| macOS | `PRII-CENTINELAS.command` or `PRII-CENTINELAS.app` |
| Windows | `PRII-CENTINELAS.bat` |
| Linux | `PRII-CENTINELAS.sh` |

The **first run** needs an internet connection once: it creates a private
`.venv`, installs the Python dependencies, and builds the frontend (requires
[Python 3.10+](https://www.python.org/downloads/) and
[Node.js](https://nodejs.org) to be installed). Every later run starts
instantly and **works offline** — the app serves the data committed in this
repository from a local server and shows it in a native window.

## How it works

- `desktop/config.py` — the only per-repo file (title, paths, requirements).
- `desktop/setup.py` — idempotent one-time setup (`--force` to redo): creates
  the `.venv`, installs the backend + desktop requirements, and builds the
  frontend for same-origin serving.
- `desktop/seed.py` — before the setup-completeness check runs, this replays
  the committed signal ledgers (`data/signals/*.jsonl`) into
  `.centinelas/classified/*.json` so the app opens with real signal data
  instead of an empty pipeline. It only writes when the classified directory
  is empty, so it never overwrites a live `ingest`/`classify`/`dispatch` run —
  this is a deliberate first-run convenience, not a bug.
- `desktop/launch.py` — a thin shim; the actual launcher runtime (uvicorn +
  native window + single-instance lock + `--smoke` CI mode) lives in the
  shared `prii_desktop` package (`thehub-pr/packages/prii_desktop`), pinned to
  an immutable git commit so this repo installs independently. Flags:
  `--no-window`, `--browser`, `--smoke`.

## Command line

```bash
python desktop/setup.py          # one-time setup
.venv/bin/python desktop/launch.py            # native window
.venv/bin/python desktop/launch.py --browser  # browser tab instead
.venv/bin/python desktop/launch.py --no-window  # server only
```

## macOS app icon

`PRII-CENTINELAS.app` is a double-click macOS app (Apple-silicon and Intel).
Double-click it in Finder and the app opens in its own window — no Terminal.
The first launch runs the one-time setup (needs internet once, plus Node.js
for the frontend build); after that it starts straight away and works
offline.

Because the app is a small self-locating wrapper around `desktop/launch.py`,
it must stay at the repo root (it finds the repo from its own location). If
macOS blocks the first open, see **If macOS blocks the first open** below.

## If macOS blocks the first open

The app is safe — it's an open-source launcher script you can read in
`Contents/MacOS/`. macOS blocks it only because it isn't signed with a paid
Apple Developer ID or notarized by Apple, so the first open may show *"cannot
be opened because Apple cannot check it for malicious software"* or an
*"unidentified developer"* notice. That's macOS quarantining files downloaded
from the internet (it happens especially with GitHub's **Download ZIP**). Any
one of the following clears it — you only do this once per download:

- **Easiest — run the helper.** Double-click **`Fix-Gatekeeper.command`** in
  the repo root, then open the app normally. If the helper is itself blocked,
  right-click it → **Open** to run it once.
- **Terminal (always works).** Paste this into Terminal (pasting a command is
  never blocked), then press Return:
  ```bash
  xattr -dr com.apple.quarantine "/path/to/centinelas-pr/PRII-CENTINELAS.app"
  ```
  Tip: type `xattr -dr com.apple.quarantine ` (with a trailing space) and drag
  the app onto the Terminal window to fill in its path.
- **System Settings.** Double-click the app, let macOS block it, then open
  **System Settings → Privacy & Security**, scroll to the message naming the
  app, and click **Open Anyway**. On macOS Sequoia 15 and later this replaces
  the old right-click → **Open** trick.
