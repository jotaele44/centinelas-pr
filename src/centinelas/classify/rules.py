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
         "outage", "apagon", "aee",
         # PR permit ecosystem — DRNA coastal/environmental permitting + federal
         # coastal (Corps §404 / EPA). These are the pre-officialization permit
         # signals (boundary certifications, impact determinations, hearings,
         # notices, reviews) that anchor to aguayluz-pr. Accent-folded at compile
         # time ("maritimo" matches "marítimo"). Deliberately omits over-generic
         # tokens: bare "dia" (collides with Spanish "día"/"días"), bare "permiso"
         # / "endoso" / "costera" / "section 10" (too broad) — precise multi-word
         # phrases are used instead so non-permit text is not mislabeled.
         "deslinde", "zmt", "zona maritimo terrestre", "maritimo terrestre",
         "zona costanera", "zona costera", "litoral", "ambiental",
         "impacto ambiental", "declaracion de impacto", "cumplimiento ambiental",
         "endosos y permisos", "fuente de contaminacion", "contaminacion",
         "calidad de agua", "calidad del agua", "calidad de aire",
         "calidad del aire", "inyeccion subterranea", "revision publica",
         "npdes", "drna", "recursos naturales", "junta de calidad ambiental",
         "section 404", "clean water act", "corps of engineers", "dredge",
         "antilles",
         # Permit hearings. Scraped OGPe/JP hearing entries are titled with a
         # bare case number ("2025-663228-PU-438754") or a short code
         # ("VP - Poblado Castañer"), so the hearing vocabulary is the only thing
         # that routes them to the permit lane. Both plural forms are listed
         # because _compile() only tolerates a trailing "s" on the whole phrase,
         # and Spanish pluralizes both words ("vistas públicas").
         "vista publica", "vistas publicas", "junta de planificacion",
         "consulta de ubicacion"],
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
    (
        # Workplace safety & compliance — OSHA/DOL enforcement, inspections, citations,
        # workplace fatalities/amputations, occupational health (English + PR Spanish).
        # Routes to aguayluz-pr's INDUSTRIAL alert module.
        ["osha", "occupational safety", "occupational health", "workplace safety",
         "worker safety", "workplace fatality", "worker death", "safety violation",
         "willful violation", "serious violation", "safety citation", "workplace hazard",
         "imminent danger", "amputation", "severe injury report", "workplace injury",
         "seguridad ocupacional", "seguridad laboral", "salud ocupacional",
         "muerte de trabajador", "accidente laboral"],
        DomainLabel.SAFETY_COMPLIANCE,
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


# ── Permit-ecosystem sub-taxonomy ─────────────────────────────────────────────
# Like the water/utility layer above, ENVIRONMENTAL stays coarse (routes to
# aguayluz-pr). This finer layer tags *which* permit beat a signal is about — a
# ZMT boundary certification vs. an environmental-impact determination vs. a
# public hearing vs. a pollution-source permit — so aguayluz/the Hub can route
# within the permit domain instead of treating every DRNA/federal permit item
# alike. Merged into ``domain_tags`` alongside the water tags in
# router.build_payload. Tag names are chosen to not collide with the water tags.
_PERMIT_TAGS: dict[str, list[str]] = {
    "coastal_zmt": ["deslinde", "zmt", "zona maritimo terrestre", "maritimo terrestre",
                    "zona costanera", "zona costera", "litoral", "pmzc"],
    "environmental_impact": ["impacto ambiental", "declaracion de impacto",
                             "environmental impact"],
    "air_quality": ["calidad de aire", "calidad del aire", "air quality"],
    "water_permit": ["calidad de agua", "calidad del agua", "npdes",
                     "fuente de contaminacion", "water quality permit"],
    "wells_injection": ["inyeccion subterranea", "pozo de inyeccion",
                        "underground injection"],
    "underground_tanks": ["tanques soterrados", "tanque soterrado",
                          "underground storage tank"],
    "land_contamination": ["contaminacion de terrenos", "terrenos contaminados",
                           "land contamination"],
    "public_hearing": ["vista publica", "revision publica", "comentario publico",
                       "public hearing", "public comment"],
    "procurement_permit": ["sdp", "rfp", "subasta", "licitacion"],
    "regulation": ["reglamento", "reglamento propuesto", "orden administrativa"],
}
_COMPILED_PERMIT_TAGS: list[tuple[str, list[re.Pattern[str]]]] = [
    (tag, [_compile(kw) for kw in kws]) for tag, kws in _PERMIT_TAGS.items()
]


def permit_subtypes(text: str) -> list[str]:
    """Return the permit-ecosystem sub-taxonomy tags a signal matches (may be empty).

    Order-stable (matches ``_PERMIT_TAGS`` insertion order); deterministic.
    """
    lower = _fold(text)
    return [tag for tag, pats in _COMPILED_PERMIT_TAGS if any(p.search(lower) for p in pats)]


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
    # Workplace life-safety (OSHA): a fatality/amputation/imminent-danger signal is
    # ASAP-tier just like a natural-hazard emergency.
    "workplace fatality", "worker death", "muerte de trabajador", "imminent danger",
    "peligro inminente", "amputation", "fatal injury", "workplace explosion",
]
_COMPILED_URGENCY = [_compile(kw) for kw in _URGENCY_KEYWORDS]


def is_critical_signal(text: str) -> bool:
    """True when a signal carries life-safety / emergency language (ASAP push tier)."""
    lower = _fold(text)
    return any(p.search(lower) for p in _COMPILED_URGENCY)
