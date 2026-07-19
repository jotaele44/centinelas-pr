"""Gate: the shared PR natural-features resolver slice resolves signal place names.

centinelas consumes the name-only resolver slice (no geometry) of the canonical
gazetteer owned by spiderweb-pr, so routed signals reference the same canonical_id
the federation joins on.
"""

import json
from pathlib import Path

from centinelas.natural_features import RESOLVER_PATH, resolve_natural_feature

DATA = Path(__file__).resolve().parents[1] / "data" / "reference" / "pr_natural_features_resolver.json"


def test_slice_is_name_only_all_groups():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert data["_count"] == len(data["features"]) == 1982
    assert {g for r in data["features"] for g in [r["group"]]} == {"hydro", "terrain", "coastal"}
    # resolver projection carries no geometry
    assert all("lat" not in r and "lon" not in r for r in data["features"])


def test_resolves_accented_and_ascii_forms():
    for raw in ("Río Grande de Loíza", "Rio Grande de Loiza", "RIO GRANDE DE LOIZA"):
        res = resolve_natural_feature(raw)
        assert res["resolution_status"] == "resolved", res
        assert res["canonical_id"].startswith("place_")
        assert res["canonical_id"] == resolve_natural_feature("Río Grande de Loíza")["canonical_id"]


def test_unknown_place_is_unresolved():
    assert resolve_natural_feature("Nowhere Atlantis")["resolution_status"] == "unresolved"


def test_default_resolver_path_exists():
    assert RESOLVER_PATH == DATA and RESOLVER_PATH.exists()
