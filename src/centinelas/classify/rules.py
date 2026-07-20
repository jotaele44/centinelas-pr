"""Keyword pre-filter — fast path that skips LLM calls for obvious domain hits."""

import re
import unicodedata

from centinelas.classify.labels import DomainLabel


def _fold(text: str) -> str:
    """Lowercase + strip accents so PR Spanish text matches ASCII keywords.

    PR source text uses accents (``sequía``, ``apagón``, ``contaminación``); the
    taxonomy keywords are ASCII. Fold both sides (NFKD → drop combining marks →
    lower) so accented and unaccented forms match interchangeably.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()

# Each entry is (keywords, label). Keywords are lowercased and matched on WORD
# BOUNDARIES (not naive substring containment), so a short token like "sec"
# matches the standalone word "sec"/"SEC" but not the substring inside
# "Second", "secret", or "consecutive". A single trailing "s" is tolerated so
# genuine plurals ("rockets", "missiles", "elections") still match.
# First match wins per label (a title can match multiple labels).
_RULES: list[tuple[list[str], DomainLabel]] = [
    (
        ["earthquake", "seismic", "volcano", "volcanic", "eruption", "tsunami",
         "landslide", "geology", "tectonic", "fault line", "magnitude", "usgs"],
        DomainLabel.GEO_GEOLOGY,
    ),
    (
        ["hurricane", "tropical storm", "flood", "wildfire", "drought", "deforestation",
         "climate change", "emissions", "pollution", "epa", "noaa", "water quality",
         "coral reef", "sea level", "carbon", "biodiversity", "species", "ecosystem",
         # PR water/utility infrastructure — routes to aguayluz-pr (the water/power
         # /outage monitoring node), not just generic global climate news.
         "prasa", "acueducto", "aqueduct", "wastewater", "alcantarillado", "sewer",
         "reservoir", "embalse", "represa", "boil water", "boil-water",
         "hervir el agua", "racionamiento", "sequia", "luma", "prepa", "preb",
         "outage", "apagon", "aee"],
        DomainLabel.ENVIRONMENTAL,
    ),
    (
        ["ufo", "uap", "unidentified", "anomalous aerial", "paranormal", "extraterrestrial",
         "alien", "crop circle", "orb sighting", "seti", "unexplained phenomenon",
         "abduction", "cryptid", "bigfoot", "ghost", "poltergeist", "interdimensional"],
        DomainLabel.ANOMALOUS,
    ),
    (
        ["military", "defense", "pentagon", "nato", "air force", "navy", "army",
         "missile", "drone strike", "fighter jet", "aircraft carrier", "satellite launch",
         "space force", "rocket", "aerospace", "lockheed", "boeing defense", "raytheon",
         "northrop", "general dynamics", "hypersonic", "stealth", "warplane", "combat",
         "aviation", "faa", "airspace", "flight test"],
        DomainLabel.MILITARY_AEROSPACE,
    ),
    (
        ["stock market", "interest rate", "federal reserve", "inflation", "gdp",
         "recession", "cryptocurrency", "bitcoin", "sec", "ipo", "merger", "acquisition",
         "earnings", "hedge fund", "bond yield", "treasury", "imf", "world bank",
         "trade deficit", "tariff", "sanctions",
         # Public-money / procurement / award vocabulary (English + PR Spanish) —
         # routes contractor/government award announcements to moneysweep-pr (the
         # money anchor), which only ingests FINANCIAL/POLITICAL drops. Without
         # these, a construction-award story classifies MILITARY_AEROSPACE or
         # UNCLASSIFIED and never reaches the finance lane. Accent-folded at
         # compile time, so "adjudicacion" matches "adjudicación".
         "contract", "contrato", "contractor", "contratista", "award", "awarded",
         "adjudicacion", "aviso de adjudicacion", "subasta", "licitacion",
         "procurement", "rfp", "joint venture", "obra publica", "obras publicas",
         "construccion", "infraestructura"],
        DomainLabel.FINANCIAL,
    ),
    (
        ["election", "congress", "senate", "legislation", "bill passed", "executive order",
         "president", "prime minister", "parliament", "geopolitics", "diplomacy",
         "sanctions", "war", "conflict", "protest", "coup", "treaty", "summit",
         "government", "policy", "regulation"],
        DomainLabel.POLITICAL,
    ),
]


def _compile(keyword: str) -> re.Pattern[str]:
    r"""Word-boundary matcher for a keyword, tolerating a single trailing plural "s".

    Using ``\b...\b`` prevents substring collisions (e.g. "sec" in "Second",
    "war" in "warehouse") while a trailing ``s?`` keeps genuine plurals matching
    ("rocket" -> "rockets"). ``re.escape`` keeps multi-word phrases literal.
    """
    return re.compile(rf"\b{re.escape(_fold(keyword))}s?\b")


# Precompile once: [(patterns, label), ...] mirroring _RULES order.
_COMPILED_RULES: list[tuple[list[re.Pattern[str]], DomainLabel]] = [
    ([_compile(kw) for kw in keywords], label) for keywords, label in _RULES
]


def keyword_classify(text: str) -> list[DomainLabel]:
    """Return matched labels from keyword rules. May return multiple labels."""
    lower = _fold(text)
    matched: list[DomainLabel] = []
    seen: set[DomainLabel] = set()
    for patterns, label in _COMPILED_RULES:
        if label in seen:
            continue
        if any(pat.search(lower) for pat in patterns):
            matched.append(label)
            seen.add(label)
    return matched


# ── Water/utility sub-taxonomy ────────────────────────────────────────────────
# The six DomainLabels stay coarse (ENVIRONMENTAL routes to aguayluz-pr). This
# finer layer tags *which* water/utility beat a signal is about, so aguayluz can
# recognize a PRASA boil-water notice vs. a reservoir/drought vs. a grid outage
# instead of treating every ENVIRONMENTAL item as generic climate news. Emitted
# as `domain_tags` on the aguayluz/hub dispatch payload (router.build_payload).
_WATER_UTILITY_TAGS: dict[str, list[str]] = {
    "potable_water": ["prasa", "acueducto", "aqueduct", "agua potable", "drinking water",
                      "water utility", "water main", "water service"],
    "boil_water": ["boil water", "boil-water", "hervir el agua", "boil advisory",
                   "boil-water advisory"],
    "water_quality": ["water quality", "contamination", "contaminacion", "turbidity",
                      "sdwis", "e. coli", "coliform"],
    "wastewater": ["wastewater", "alcantarillado", "sewer", "sewage", "aguas usadas",
                   "aguas negras", "npdes"],
    "reservoir_drought": ["reservoir", "embalse", "represa", "drought", "sequia",
                          "racionamiento", "water rationing", "dam safety"],
    "flood": ["flood", "inundacion", "flash flood", "flooding"],
    "power_grid": ["luma", "prepa", "preb", "power outage", "apagon", "blackout",
                   "grid", "aee", "generation"],
}
_COMPILED_WATER_TAGS: list[tuple[str, list[re.Pattern[str]]]] = [
    (tag, [_compile(kw) for kw in kws]) for tag, kws in _WATER_UTILITY_TAGS.items()
]


def water_utility_subtypes(text: str) -> list[str]:
    """Return the water/utility sub-taxonomy tags a signal matches (may be empty).

    Order-stable (matches ``_WATER_UTILITY_TAGS`` insertion order); deterministic.
    """
    lower = _fold(text)
    return [tag for tag, pats in _COMPILED_WATER_TAGS if any(p.search(lower) for p in pats)]


# Life-safety / emergency vocabulary (English + PR Spanish). A signal matching any of
# these is flagged is_critical so downstream producers/the Hub can fast-track it into
# the ASAP push/SMS tier instead of a batched brief.
_URGENCY_KEYWORDS: list[str] = [
    "emergency", "emergencia", "evacuate", "evacuation", "evacuacion", "evacuar",
    "boil water", "hervir el agua", "tsunami", "hurricane warning", "aviso de huracan",
    "flash flood", "inundacion repentina", "mandatory", "obligatorio", "shelter in place",
    "refugio", "curfew", "toque de queda", "immediate", "inmediato", "urgent", "urgente",
    "life-threatening", "peligro de muerte", "explosion", "explosión", "wildfire",
    "landslide", "derrumbe", "toxic", "toxico", "contamination emergency",
]
_COMPILED_URGENCY = [_compile(kw) for kw in _URGENCY_KEYWORDS]


def is_critical_signal(text: str) -> bool:
    """True when a signal carries life-safety / emergency language (ASAP push tier)."""
    lower = _fold(text)
    return any(p.search(lower) for p in _COMPILED_URGENCY)
