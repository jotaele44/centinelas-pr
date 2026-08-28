from __future__ import annotations

from typing import Any

from centinelas.space_discovery import ManualReceiptAdapter, build_lead


def qualified_lead(
    *,
    identity: str = "item",
    synthetic: bool = False,
    sensor: dict[str, Any] | None = None,
    case_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_url = f"https://example.test/{identity}"
    body = f"space observation fixture:{identity}".encode()
    lead = build_lead(
        source_id=f"CENT-SRC-SPACE-{identity.upper()}",
        source_url=source_url,
        title=f"Dataset release {identity}",
        subcategory="SATELLITE_DATASET_RELEASE",
        body=body,
        receipt=ManualReceiptAdapter().receipt(source_url=source_url, body=body),
        sensor=sensor,
        case_links=case_links,
        synthetic=synthetic,
    )
    lead["review_status"] = "qualified"
    return lead
