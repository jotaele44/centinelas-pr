from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceEndpoint:
    adapter_id: str
    index_url: str
    robots_url: str
    policy_url: str
    enabled_for_pilot: bool = False
    remediation_note: str | None = None


SOURCE_ENDPOINTS: dict[str, SourceEndpoint] = {
    "nara_ndc": SourceEndpoint(
        "nara_ndc",
        "https://www.archives.gov/declassification/ndc/releases?page=1&page_size=100",
        "https://www.archives.gov/robots.txt",
        "https://www.archives.gov/global-pages/privacy.html",
    ),
    "nara_catalog": SourceEndpoint(
        "nara_catalog",
        "https://catalog.archives.gov/api/v1/records?page=1&page_size=100",
        "https://catalog.archives.gov/robots.txt",
        "https://www.archives.gov/global-pages/privacy.html",
        remediation_note="ROBOTS_DENIED_DO_NOT_BYPASS",
    ),
    "cia_reading_room": SourceEndpoint(
        "cia_reading_room",
        "https://www.cia.gov/readingroom/search/site?page=1&page_size=100",
        "https://www.cia.gov/robots.txt",
        "https://www.cia.gov/site-policies/",
        remediation_note="ROBOTS_DENIED_DO_NOT_BYPASS",
    ),
    "nsa_releases": SourceEndpoint(
        "nsa_releases",
        "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/?page=1&page_size=100",
        "https://www.nsa.gov/robots.txt",
        "https://www.nsa.gov/Site-Policies/",
        remediation_note="POLICY_URL_UPDATED_2026_07_28",
    ),
    "dia_reading_room": SourceEndpoint(
        "dia_reading_room",
        "https://www.dia.mil/FOIA/FOIA-Electronic-Reading-Room/?page=1&page_size=100",
        "https://www.dia.mil/robots.txt",
        "https://www.dia.mil/FOIA/",
    ),
    "nhhc": SourceEndpoint(
        "nhhc",
        "https://www.history.navy.mil/research/archives/digital-exhibits-highlights.html?page=1&page_size=100",
        "https://www.history.navy.mil/robots.txt",
        "https://www.history.navy.mil/about-us/privacy-policy.html",
        remediation_note="TLS_CHAIN_DIAGNOSIS_REQUIRED_NO_BYPASS",
    ),
    "doe_aec": SourceEndpoint(
        "doe_aec",
        "https://www.energy.gov/nnsa/nnsa-foia-library?page=1&page_size=100",
        "https://www.energy.gov/robots.txt",
        "https://www.energy.gov/web-policies",
        remediation_note="NNSA_FOIA_LIBRARY_URL_UPDATED_2026_07_28",
    ),
    "air_force_blue_book": SourceEndpoint(
        "air_force_blue_book",
        "https://www.archives.gov/research/military/air-force/ufos?page=1&page_size=100",
        "https://www.archives.gov/robots.txt",
        "https://www.archives.gov/global-pages/privacy.html",
    ),
}
