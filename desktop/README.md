# Centinelas desktop

## Install on macOS — no Terminal

1. Open this repository's **Releases** page and download the latest
   `PRII-CENTINELAS-macOS.dmg`.
2. Open the disk image and drag **Centinelas** to **Applications**.
3. Open Centinelas from Applications.

The release contains its own Python runtime, backend, compiled interface, and
baseline resources. Python, Node.js, Git, Homebrew, and Terminal are not
required.

On first launch, the native **Setup & Repair** screen asks for a writable data
location, verifies the packaged interface and icon, checks private loopback
networking, and starts the app. **Setup & Diagnostics** remains available in
the lower-right corner of the app for safe repair; repair never deletes
research data.

Centinelas stores queue, classification, dispatch, and handoff state in the
selected Application Support location. The committed signal ledgers remain
read-only seed/reference material. Live RSS and model-backed collection are
optional operator workflows, not prerequisites for opening the desktop app.

## If macOS blocks the first open

Open **System Settings → Privacy & Security**, find the message naming
Centinelas, and choose **Open Anyway**. This is the complete recovery path; no
quarantine command or helper script is required. Release CI applies an ad-hoc
integrity signature, but public downloads are not Apple-notarized unless a
release is signed with project Developer ID credentials.

The `PRII-CENTINELAS.app` committed in a source checkout is a Finder-only
download helper. The self-contained product is the app inside the release
disk image.

## Release contract

The `desktop-build` workflow builds on clean Linux, macOS, and Windows runners,
then tests both the fresh-machine setup contract and backend health on the
frozen executable. macOS CI verifies the app bundle signature before producing
the `.dmg`.

`desktop/launch.py` and `desktop/config.py` are thin adapters over TheHub's
shared `prii_desktop` runtime. `desktop/setup.py` and command launchers remain
developer conveniences for source checkouts; they are not part of end-user
installation.
