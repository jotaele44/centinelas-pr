"""The `source_monitors` export stream (thehub-pr ADR 0013).

One row per source in data/reference/source_registry.csv, with when the source last
succeeded and how that is known: the newest non-synthetic `captured_at` it has in
the signal ledger (OUTPUT_DERIVED), or neither (NOT_RECORDED, null time).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import federation_export as fx  # noqa: E402
import prii_export_utils  # noqa: E402

SOURCES = REPO / "data/reference/source_registry.csv"
LIVE = REPO / "data/signals/live_signals.jsonl"
EXAMPLE = REPO / "data/signals/example_signals.jsonl"
NOW = "2026-11-13T18:00:00Z"


def _ledger(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _registry() -> dict[str, dict[str, str]]:
    return fx._load_source_registry(SOURCES)


def _signal(source_id: str, captured_at: str, *, synthetic: bool = False) -> dict:
    return {"source_id": source_id, "captured_at": captured_at, "is_synthetic": synthetic}


def test_one_row_per_registered_source_on_committed_data():
    rows = fx.build_source_monitors(_ledger(LIVE), _registry(), NOW)
    with SOURCES.open() as fh:
        registered = sorted(r["source_id"] for r in csv.DictReader(fh))
    assert [r["source_ref"] for r in rows] == registered
    assert len({r["monitor_id"] for r in rows}) == len(rows)
    assert all(r["monitor_id"] == prii_export_utils.monitor_id(fx.PRODUCER, r["source_ref"]) for r in rows)
    for row in rows:
        if row["last_success_basis"] == "NOT_RECORDED":
            assert row["last_success_at"] is None
        else:
            assert row["last_success_basis"] == "OUTPUT_DERIVED" and row["last_success_at"]


def test_last_success_is_the_newest_real_capture():
    registry = {"A": {"source_id": "A", "name": "Feed A", "active": "active", "scrape_method": "rss"}}
    signals = [
        _signal("A", "2026-11-12T05:00:00+00:00"),
        _signal("A", "2026-11-13T05:44:48.809124+00:00"),
        _signal("A", "2026-11-14T00:00:00Z", synthetic=True),  # synthetic never counts
        _signal("A", "not a time"),
    ]
    [row] = fx.build_source_monitors(signals, registry, NOW)
    assert (row["last_success_at"], row["last_success_basis"]) == ("2026-11-13T05:44:48.809124+00:00", "OUTPUT_DERIVED")


def test_nothing_is_guessed_without_real_signals():
    rows = fx.build_source_monitors(_ledger(EXAMPLE), _registry(), NOW)  # the seed is all synthetic
    assert {(r["last_success_at"], r["last_success_basis"]) for r in rows} == {(None, "NOT_RECORDED")}


def test_signals_from_unregistered_sources_add_no_rows():
    registry = {"A": {"source_id": "A", "name": "Feed A", "active": "active", "scrape_method": "rss"}}
    rows = fx.build_source_monitors([_signal("UNREGISTERED", "2026-11-13T05:00:00Z")], registry, NOW)
    assert [r["source_ref"] for r in rows] == ["A"]
    assert rows[0]["last_success_basis"] == "NOT_RECORDED"


@pytest.mark.parametrize(("active", "method", "status", "cadence"), [
    ("active", "rss", "active", "unknown"),
    ("manual", "manual", "manual", "manual"),
    ("Yes", "api", "active", "unknown"),
    ("no", "scrape", "inactive", "unknown"),
    ("", "html", "unknown", "unknown"),
])
def test_status_and_cadence_follow_the_hub_registry_reader(active, method, status, cadence):
    registry = {"A": {"source_id": "A", "name": "", "source_family": "", "active": active, "scrape_method": method}}
    [row] = fx.build_source_monitors([], registry, NOW)
    assert (row["declared_status"], row["cadence"], row["name"]) == (status, cadence, "A")
    assert "producer_family" not in row or row["producer_family"] is None


def test_package_lists_the_stream_and_its_manifest_validates(tmp_path):
    streams = fx.build_streams(_ledger(LIVE), _registry(), NOW)
    streams["source_monitors"] = fx.build_source_monitors(_ledger(LIVE), _registry(), NOW)
    manifest_path = fx.write_package(streams, tmp_path, "production", NOW)
    manifest = json.loads(manifest_path.read_text())
    entry = next(f for f in manifest["files"] if f["stream"] == "source_monitors")
    assert entry["schema_id"] == "federation_source_monitor.schema.json"
    assert entry["record_count"] == len(streams["source_monitors"])
    schema = json.loads((REPO / "schemas/federation_export_manifest.schema.json").read_text())
    jsonschema.validate(manifest, schema)


def test_local_helpers_keep_their_ids_and_reach_the_pinned_package():
    # scripts/prii_export_utils.py shadows the pinned package; its own helpers stay
    # as they were (ids depend on them) and other names come from the package.
    assert Path(prii_export_utils.__file__).resolve() == REPO / "scripts" / "prii_export_utils.py"
    import hashlib
    assert prii_export_utils.fid("ent", "a", None) == "ent_" + hashlib.sha256(b"a|").hexdigest()[:32]
    assert prii_export_utils.norm("Río Grande") == "rio_grande"
    assert callable(prii_export_utils.source_monitor_row)
    assert callable(prii_export_utils.resolve_last_success)
    with pytest.raises(AttributeError):
        prii_export_utils.no_such_helper  # noqa: B018


def test_pinned_package_loads_from_an_archive(tmp_path):
    # A frozen build can bundle the pinned package in an archive, where it has no
    # source file on disk, so the shim must import it with the loader its finder
    # returns. A zip on sys.path is the same case: an archive-backed loader.
    import subprocess
    import zipfile

    package = Path(prii_export_utils._pinned_package().__file__).parent
    archive = tmp_path / "pinned.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in sorted(package.glob("*.py")):
            zf.write(path, f"prii_export_utils/{path.name}")
    code = "\n".join([
        "import sys",
        "from pathlib import Path",
        f"sys.path[:0] = [{str(REPO / 'scripts')!r}, {str(archive)!r}]",
        "import prii_export_utils as shim",
        f"assert Path(shim.__file__).resolve() == Path({str(REPO / 'scripts' / 'prii_export_utils.py')!r})",
        "assert shim.norm('Río Grande') == 'rio_grande'",
        "row = shim.source_monitor_row",
        "assert callable(row) and row.__module__ == 'prii_export_utils.source_monitor', row.__module__",
        "assert sys.modules['prii_export_utils'] is shim",
    ])
    # -S: no site-packages, so the zip is the only place the pinned package can come from.
    result = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
