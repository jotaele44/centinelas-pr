"""Desktop-wrapper configuration for this repo.

The desktop/ folder is a shared federation template; only this file differs
between repos.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# User-facing window title of the desktop app.
APP_TITLE = "Centinelas"
APP_ID = "Centinelas"
BRAND_ACCENT = "#df630d"
BRAND_ACCENT_STRONG = "#9f3e00"
ICON_PATH = REPO_ROOT / "assets" / "branding" / "icon-256.png"
SETUP_VERSION = 1
DATA_ENV_VAR = "CENTINELAS_DATA_DIR"
SETUP_ACTION = "desktop.seed:seed"

# Dotted import path of the FastAPI application object.
APP_IMPORT = "server.backend.main:app"

# Directory containing the Vite frontend (with package.json).
FRONTEND_DIR = REPO_ROOT / "frontend"

# Vite build output served by the desktop app.
DIST_DIR = FRONTEND_DIR / "dist"

# Requirement files installed into the private .venv by desktop/setup.py.
REQUIREMENT_FILES = [
    REPO_ROOT / "server" / "backend" / "requirements.txt",
    REPO_ROOT / "requirements-desktop.txt",
]

# Health endpoint used to detect that the backend is up.
HEALTH_PATH = "/health"

# The intake API imports the centinelas package itself; install it (with the
# fastapi/uvicorn server extra) into the private venv.
EXTRA_PIP_SPECS = ["-e", f"{REPO_ROOT}[server]"]


def _paths_module():
    """centinelas.paths, loaded from this checkout.

    The launcher calls this before the app's environment exists, so the
    package may not be importable yet; the module is standard library only and
    is loaded by file path.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_centinelas_paths", REPO_ROOT / "src" / "centinelas" / "paths.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _launchpad_status() -> list[dict[str, str]]:
    """Readiness rows for the Launch Pad. Runs before the backend exists, so it
    counts the pipeline files under the same data directory the backend uses.
    """
    paths = _paths_module()
    try:
        data_dir = paths.data_dir()
    except paths.DataDirNotAllowed as exc:
        return [
            {
                "label": "Data folder",
                "value": "Not allowed",
                "status": "fail",
                "detail": str(exc),
            }
        ]

    def count(stage: str) -> int:
        folder = data_dir / stage
        return sum(1 for _ in folder.glob("*.json")) if folder.is_dir() else 0

    classified, queued = count("classified"), count("queue")
    dispatched, handoffs = count("dispatched"), count("handoffs")
    seeded = (data_dir / ".seeded").is_file()
    return [
        {
            "label": "Classified signals",
            "value": f"{classified:,}" if classified else "Empty",
            "status": "pass" if classified else "info",
            "detail": (
                (
                    "Includes the committed signal ledger replayed on first run."
                    if seeded
                    else "Signals classified by pipeline runs."
                )
                if classified
                else "No signals yet. Setup replays the committed ledger; a pipeline "
                "run adds live ones."
            ),
        },
        {
            "label": "Waiting in queue",
            "value": f"{queued:,}",
            "status": "warn" if queued else "info",
            "detail": "Ingested items not yet classified.",
        },
        {
            "label": "Routed and handed off",
            "value": f"{dispatched:,} routed, {handoffs:,} handoffs",
            "status": "info",
            "detail": f"Pipeline data is kept in {data_dir}.",
        },
    ]


# Pre-launch screen shown by the shared runtime (prii_desktop.launchpad).
#
# Guest mode only ever *adds* a refusal in front of the API. It does not touch
# the write-authorization boundary in server/backend/auth.py, which stays in
# force in both modes: Operator sets no credential and relies on that guard's
# own local-client rule, exactly as the app behaved before the Launch Pad.
LAUNCHPAD = {
    "tagline": "Early signals, routed to the federation",
    "summary": (
        "Centinelas watches public sources (RSS feeds, the Federal Register "
        "and selected web pages), sorts what it finds into six domains, and "
        "routes or hands off the signals to the federation's other producers. "
        "It also runs the water-service disruption watch in shadow mode."
    ),
    "highlights": [
        "Signal monitor",
        "Matters and entities",
        "Pipeline",
        "Water disruptions",
        "Handoff",
    ],
    "status": _launchpad_status,
    # Routes from frontend/src/App.jsx; labels follow the app's own navigation.
    "start_pages": [
        {"route": "/", "label": "Home",
         "description": "The overview page shown on a fresh start."},
        {"route": "/dashboard", "label": "Dashboard",
         "description": "Where work starts: current signals at a glance."},
        {"route": "/monitor", "label": "Monitor"},
        {"route": "/signals", "label": "Signals"},
        {"route": "/matters", "label": "Matters"},
        {"route": "/entidades", "label": "Entities"},
        {"route": "/sources", "label": "Sources"},
        {"route": "/pipeline", "label": "Pipeline",
         "description": "Items at each stage: queued, classified, routed."},
        {"route": "/water-disruption", "label": "Water disruptions",
         "description": "Shadow-mode water-service disruption candidates."},
        {"route": "/handoff", "label": "Handoff",
         "description": "Hand a classified signal to another producer."},
    ],
    "guest": {
        "label": "Guest",
        "description": (
            "Read-only. Browse signals, matters and the pipeline. Handoffs, "
            "pipeline runs and water-disruption actions are refused."
        ),
    },
    "operator": {
        "label": "Operator",
        "description": (
            "Full access from this computer: create handoffs, run the pipeline "
            "and act on water-disruption candidates."
        ),
    },
    # Every POST in server/backend changes state or calls out, so a guest is
    # allowed none of them.
    "guest_guard": {"allow": []},
    "options": [
        {
            "id": "route_min_confidence",
            "label": "Routing confidence threshold",
            "kind": "choice",
            "env": "CENTINELAS_ROUTE_MIN_CONFIDENCE",
            "default": "0.55",
            "choices": [
                ["0.40", "0.40 — route more, lower certainty"],
                ["0.55", "0.55 — default"],
                ["0.70", "0.70 — stricter"],
                ["0.85", "0.85 — only high-confidence signals"],
            ],
            "operator_only": True,
            "help": "Signals classified below this confidence are not routed.",
        },
        {
            "id": "dispatch_token",
            "label": "GitHub dispatch token",
            "kind": "secret",
            "env": "FEDERATION_DISPATCH_TOKEN",
            "operator_only": True,
            "help": (
                "Needed for Handoff to notify the receiving repository on "
                "GitHub. Without it a handoff is recorded locally and the "
                "notification fails."
            ),
        },
        {
            "id": "anthropic_api_key",
            "label": "Anthropic API key",
            "kind": "secret",
            "env": "ANTHROPIC_API_KEY",
            "operator_only": True,
            "help": (
                "Optional. Pipeline runs use it to classify signals with a "
                "language model, which sends signal text to the Anthropic API. "
                "Without it classification uses keyword rules only."
            ),
        },
    ],
}
