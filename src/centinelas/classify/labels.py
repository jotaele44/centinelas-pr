from enum import Enum


class DomainLabel(str, Enum):
    ENVIRONMENTAL = "ENVIRONMENTAL"
    FINANCIAL = "FINANCIAL"
    POLITICAL = "POLITICAL"
    GEO_GEOLOGY = "GEO_GEOLOGY"
    ANOMALOUS = "ANOMALOUS"
    MILITARY_AEROSPACE = "MILITARY_AEROSPACE"
    UNCLASSIFIED = "UNCLASSIFIED"


# Maps label → destination repo name (used by router)
LABEL_TO_REPO: dict[DomainLabel, str] = {
    DomainLabel.ENVIRONMENTAL: "aguayluz-pr",
    DomainLabel.FINANCIAL: "moneysweep-pr",
    DomainLabel.POLITICAL: "moneysweep-pr",
    DomainLabel.GEO_GEOLOGY: "spiderweb-pr",
    DomainLabel.ANOMALOUS: "ovnis-pr",
    DomainLabel.MILITARY_AEROSPACE: "skywatcher-pr",
}

HUB_REPO = "thehub-pr"
