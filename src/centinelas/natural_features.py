"""Resolve raw place strings to the federation's canonical natural-feature ids.

centinelas is the upstream router; it consumes the *name-only resolver slice*
(no geometry) of the canonical PR natural-features gazetteer owned by spiderweb-pr,
so classified signals reference the same ``canonical_id`` / ``normalized_name`` the
Hub joins producers on. See spiderweb-pr ``docs/NATURAL_FEATURES_CONTRACT.md``.

Distinct features can share a name (e.g. "Arrecife Algarrobo" in two municipios);
those resolve to ``collision_review_required`` rather than silently picking one.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

# Packaged alongside the module (like ingest/sources.yaml) so it resolves after a
# normal pip install, not only from an editable/source checkout.
RESOLVER_PATH = Path(__file__).resolve().parent / "data" / "pr_natural_features_resolver.json"


def _fold(value: Any) -> str:
    """Accent-fold to the federation join key: lower, strip diacritics, alnum-space."""
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=4)
def _load_index(path_str: str):
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    key_to_ids: Dict[str, set] = {}
    records: Dict[str, Dict[str, Any]] = {}
    for rec in data.get("features", []) or []:
        cid = rec["canonical_id"]
        records[cid] = rec
        for key in {_fold(rec.get("canonical_name")), _fold(rec.get("normalized_name"))}:
            if key:
                key_to_ids.setdefault(key, set()).add(cid)
    return key_to_ids, records


def resolve_natural_feature(
    raw_text: str, resolver_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Map a raw place string to a canonical natural feature.

    Returns a dict with ``resolution_status`` in
    {``resolved``, ``collision_review_required``, ``unresolved``}; when resolved,
    ``canonical_id``/``canonical_name``/``feature_type``/``group`` are populated.
    """
    key_to_ids, records = _load_index(str(resolver_path or RESOLVER_PATH))
    key = _fold(raw_text)
    ids = key_to_ids.get(key)
    if not ids:
        return {"raw_text": raw_text, "canonical_id": None, "resolution_status": "unresolved"}
    if len(ids) > 1:
        return {
            "raw_text": raw_text,
            "canonical_id": None,
            "resolution_status": "collision_review_required",
            "candidate_count": len(ids),
        }
    rec = records[next(iter(ids))]
    return {
        "raw_text": raw_text,
        "canonical_id": rec["canonical_id"],
        "canonical_name": rec["canonical_name"],
        "feature_type": rec["feature_type"],
        "group": rec["group"],
        "resolution_status": "resolved",
    }
