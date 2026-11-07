from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))

import el_yunque_access_monitor as monitor  # noqa: E402
from el_yunque_access_monitor import (  # noqa: E402
    compute_transitions,
    envelope,
    listing_links,
    parse_alert,
)

FIXTURES = Path(__file__).parent / "fixtures"
BINDINGS = {
    "la mina trail": {"scope_type": "trail", "scope_name": "La Mina Trail", "asset_key": "elyunque.trail.la_mina"},
    "big tree trail": {"scope_type": "trail", "scope_name": "Big Tree Trail", "asset_key": "elyunque.trail.big_tree"},
    "baño de oro trail": {"scope_type": "trail", "scope_name": "Baño de Oro Trail", "asset_key": "elyunque.trail.bano_de_oro"},
    "el portal rainforest center": {"scope_type": "facility", "scope_name": "El Portal Rainforest Center", "asset_key": "elyunque.facility.el_portal_rainforest_center"},
}
NOW = datetime(2026, 8, 7, 20, 0, tzinfo=timezone.utc)


def _parse(title: str, html: str, url: str = "https://www.fs.usda.gov/r08/elyunque/alerts/test"):
    return parse_alert(title=title, url=url, detail_html=html, observed_at=NOW, bindings=BINDINGS)


def test_listing_fixture_discovers_detail_links():
    html = (FIXTURES / "usfs_el_yunque_alerts.html").read_text()
    links = listing_links(html)
    assert len(links) == 3
    assert all("/alerts/" in url for url, _ in links)


def test_html_drift_does_not_require_site_specific_classes():
    html = '<div class="changed-layout"><section><a class="new-class" href="/r08/elyunque/alerts/example">Example closure</a></section></div>'
    assert listing_links(html) == [("https://www.fs.usda.gov/r08/elyunque/alerts/example", "Example closure")]


def test_active_and_partial_closures_are_scoped_independently():
    html = (FIXTURES / "usfs_el_yunque_trails_detail.html").read_text()
    rows = _parse("Forest Trails Status", html)
    by_key = {row["asset_key"]: row for row in rows}
    assert by_key["elyunque.trail.la_mina"]["status"] == "closed"
    assert by_key["elyunque.trail.big_tree"]["status"] == "closed"
    assert by_key["elyunque.trail.el_yunque.los_picachos_to_peak"]["status"] == "restricted"
    assert all(row["evidence_tier"] == "T1" for row in rows)
    assert all("geometry" not in row for row in rows)


def test_future_closure_is_scheduled():
    rows = _parse(
        "El Portal Rainforest Center Annual Closure",
        "<article><p>El Portal Rainforest Center will be closed beginning September 8, 2026.</p></article>",
    )
    assert rows[0]["status"] == "scheduled"


def test_date_on_one_asset_does_not_schedule_other_asset():
    rows = _parse(
        "Trail status",
        "<article><p>La Mina Trail remains closed.</p><p>Big Tree Trail is closed beginning September 8, 2026.</p></article>",
    )
    by_key = {row["asset_key"]: row for row in rows}
    assert by_key["elyunque.trail.la_mina"]["status"] == "closed"
    assert by_key["elyunque.trail.la_mina"]["effective_start"] is None
    assert by_key["elyunque.trail.big_tree"]["status"] == "scheduled"


def test_explicit_reopening_ends_closure():
    rows = _parse("La Mina Trail update", "<article><p>La Mina Trail is now open to the public.</p></article>")
    assert rows[0]["status"] == "closure_ended"


def test_cosmetic_edit_does_not_change_semantic_hash():
    a = _parse("La Mina Trail", "<article><p>La Mina Trail remains closed.</p></article>")[0]
    b = _parse("La Mina Trail", "<article>\n  <p>La Mina Trail remains closed.</p>\n</article>")[0]
    assert a["semantic_hash"] == b["semantic_hash"]


def test_alert_removal_becomes_unknown_not_open():
    old = _parse("La Mina Trail", "<article><p>La Mina Trail remains closed.</p></article>")[0]
    current, transitions = compute_transitions({old["condition_id"]: old}, [], NOW + timedelta(minutes=15))
    row = current[old["condition_id"]]
    assert row["status"] == "unknown"
    assert row["status_basis"] == "removal_unconfirmed"
    assert transitions


def test_scheduled_condition_activates_when_effective_time_passes():
    old = _parse(
        "El Portal Rainforest Center Annual Closure",
        "<article><p>El Portal Rainforest Center will be closed beginning September 8, 2026.</p></article>",
    )[0]
    activation = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    current, transitions = compute_transitions({old["condition_id"]: old}, [old], activation)
    row = current[old["condition_id"]]
    assert row["status"] == "closed"
    assert row["status_basis"] == "effective_time"
    assert transitions


def test_duplicate_observation_produces_no_transition():
    row = _parse("La Mina Trail", "<article><p>La Mina Trail remains closed.</p></article>")[0]
    _, transitions = compute_transitions({row["condition_id"]: row}, [row], NOW)
    assert transitions == []


def test_idempotency_key_is_stable_when_ack_is_lost():
    row = _parse("La Mina Trail", "<article><p>La Mina Trail remains closed.</p></article>")[0]
    assert envelope(row)["idempotency_key"] == envelope(dict(row))["idempotency_key"]


def test_detail_fetch_failure_carries_forward_previous_state(monkeypatch):
    url = "https://www.fs.usda.gov/r08/elyunque/alerts/forest-trails-status"
    old = _parse("La Mina Trail", "<article><p>La Mina Trail remains closed.</p></article>", url=url)[0]
    listing = f'<a href="{url}">Forest Trails Status</a>'

    def fake_fetch(target: str) -> str:
        if target == monitor.LISTING_URL:
            return listing
        raise RuntimeError("403")

    monkeypatch.setattr(monitor, "fetch_html", fake_fetch)
    observed = monitor.poll(NOW, {old["condition_id"]: old})
    assert observed == [old]
    current, transitions = compute_transitions({old["condition_id"]: old}, observed, NOW)
    assert current[old["condition_id"]]["status"] == "closed"
    assert transitions == []


def test_listing_failure_raises_before_state_replacement(monkeypatch):
    monkeypatch.setattr(monitor, "fetch_html", lambda _url: (_ for _ in ()).throw(RuntimeError("network down")))
    with pytest.raises(RuntimeError, match="network down"):
        monitor.poll(NOW, {})


# --- Removal-state idempotency (regression: transitions.jsonl outgrew 100 MB) ---------------
#
# removed_unknown() used to re-append the removal marker on every poll. Each run then changed
# restriction_text and semantic_hash for every alert absent from the listing, which logged and
# handed off a spurious transition every 15 minutes until the log exceeded GitHub's file limit.


def _closed_la_mina() -> dict:
    return _parse("La Mina Trail", "<article><p>La Mina Trail remains closed.</p></article>")[0]


def test_repeated_absence_transitions_exactly_once():
    old = _closed_la_mina()
    state = {old["condition_id"]: old}
    emitted = []
    for run in range(1, 25):
        state, transitions = compute_transitions(state, [], NOW + timedelta(minutes=15 * run))
        emitted.extend(transitions)
    assert len(emitted) == 1
    row = state[old["condition_id"]]
    assert row["restriction_text"].count(monitor.REMOVAL_MARKER) == 1
    assert row["restriction_text"] == old["restriction_text"] + monitor.REMOVAL_MARKER
    # The first observation of absence is preserved; later polls do not rewrite it.
    assert row["observed_at"] == (NOW + timedelta(minutes=15)).isoformat()


def test_removed_unknown_is_a_fixed_point():
    old = _closed_la_mina()
    once = monitor.removed_unknown(old, NOW)
    assert monitor.removed_unknown(once, NOW + timedelta(hours=1)) is once


def test_reappearing_alert_transitions_back_from_unknown():
    old = _closed_la_mina()
    state, _ = compute_transitions({old["condition_id"]: old}, [], NOW + timedelta(minutes=15))
    state, transitions = compute_transitions(state, [old], NOW + timedelta(minutes=30))
    assert len(transitions) == 1
    assert transitions[0]["previous"]["status"] == "unknown"
    assert state[old["condition_id"]]["status"] == "closed"


def test_normalize_state_collapses_stacked_markers_with_receipt():
    old = _closed_la_mina()
    stacked = dict(old)
    stacked.update({
        "status": "unknown",
        "status_basis": "removal_unconfirmed",
        "restriction_text": old["restriction_text"] + monitor.REMOVAL_MARKER * 5,
    })
    stacked["semantic_hash"] = monitor.semantic_hash(stacked)
    repaired, receipts = monitor.normalize_state({old["condition_id"]: stacked}, NOW)
    row = repaired[old["condition_id"]]
    assert row["restriction_text"] == old["restriction_text"] + monitor.REMOVAL_MARKER
    assert row["semantic_hash"] == monitor.semantic_hash(row)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["markers_before"] == 5 and receipt["markers_after"] == 1
    assert receipt["semantic_hash_before"] == stacked["semantic_hash"]
    assert receipt["semantic_hash_after"] == row["semantic_hash"]
    # Repair is idempotent and the repaired state is already a removal fixed point.
    assert monitor.normalize_state(repaired, NOW)[1] == []
    _, transitions = compute_transitions(repaired, [], NOW + timedelta(minutes=15))
    assert transitions == []


def test_normalize_state_leaves_clean_rows_untouched():
    old = _closed_la_mina()
    single = monitor.removed_unknown(old, NOW)
    state = {old["condition_id"]: old, "other": single}
    repaired, receipts = monitor.normalize_state(state, NOW)
    assert receipts == []
    assert repaired["other"] is single and repaired[old["condition_id"]] is old


def test_transitions_are_segmented_by_utc_month():
    segment = monitor.transitions_segment(datetime(2026, 11, 30, 23, 59, tzinfo=timezone.utc))
    assert segment == monitor.TRANSITIONS_DIR / "2026-11.jsonl"
    assert monitor.transitions_segment(datetime(2026, 12, 1, tzinfo=timezone.utc)).name == "2026-12.jsonl"


def test_segment_capacity_fails_closed(tmp_path):
    segment = tmp_path / "2026-11.jsonl"
    segment.write_bytes(b"x" * 90)
    monitor.ensure_segment_capacity(segment, ["y" * 10], limit=100)
    with pytest.raises(RuntimeError, match="refusing to persist"):
        monitor.ensure_segment_capacity(segment, ["y" * 11], limit=100)
