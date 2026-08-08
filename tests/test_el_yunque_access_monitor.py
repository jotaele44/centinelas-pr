from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from centinelas.ingest.usfs_el_yunque import listing_links, parse_alert
from scripts.monitor_el_yunque_access import compute_transitions

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
