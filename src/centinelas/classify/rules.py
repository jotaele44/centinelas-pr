"""Keyword pre-filter — fast path that skips LLM calls for obvious domain hits."""

from centinelas.classify.labels import DomainLabel

# Each entry is (keywords, label). Keywords are lowercased substrings.
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
         "coral reef", "sea level", "carbon", "biodiversity", "species", "ecosystem"],
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
         "trade deficit", "tariff", "sanctions"],
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


def keyword_classify(text: str) -> list[DomainLabel]:
    """Return matched labels from keyword rules. May return multiple labels."""
    lower = text.lower()
    matched: list[DomainLabel] = []
    seen: set[DomainLabel] = set()
    for keywords, label in _RULES:
        if label in seen:
            continue
        if any(kw in lower for kw in keywords):
            matched.append(label)
            seen.add(label)
    return matched
