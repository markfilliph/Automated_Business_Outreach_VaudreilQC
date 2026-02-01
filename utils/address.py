"""
Quebec address normalization utilities.

Design rules:
  - Postal code is the trust anchor — it trumps everything else.
  - Strip unit/suite/apartment numbers before any string comparison.
  - Normalize French street type keywords (Rue, Blvd, Ave) to a standard form.
"""

import re


# French/English street type variants → normalized form
STREET_TYPE_MAP = {
    "rue": "rue",
    "r.": "rue",
    "street": "rue",
    "st.": "rue",
    "boulevard": "blvd",
    "blvd": "blvd",
    "boul.": "blvd",
    "avenue": "ave",
    "ave": "ave",
    "av.": "ave",
    "route": "route",
    "rte": "route",
    "chemin": "chemin",
    "ch.": "chemin",
    "place": "place",
    "pl.": "place",
    "impasse": "impasse",
    "imp.": "impasse",
    "drive": "drive",
    "dr.": "drive",
    "allée": "allee",
    "allee": "allee",
}

# Patterns that match unit/suite/apartment references
UNIT_PATTERNS = [
    r"\b(app|appart|appartement|suite|ste|unit|unité|unite)\s*[#.]?\s*\d+\b",
    r"\b#\s*\d+\b",
    r"\bsuite\s+\d+\b",
    r"\bunit\s+\d+\b",
]


def extract_postal_code(text: str) -> str:
    """
    Extract a Canadian postal code from any string.
    Returns uppercase formatted code (e.g. 'J7V 1A1') or empty string.
    """
    if not text:
        return ""
    match = re.search(r"([A-Za-z]\d[A-Za-z])\s*(\d[A-Za-z]\d)", str(text))
    if match:
        return f"{match.group(1).upper()} {match.group(2).upper()}"
    return ""


def strip_unit_number(address: str) -> str:
    """Remove unit/suite/apartment references from an address string."""
    result = address
    for pattern in UNIT_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    return result.strip()


def normalize_street_type(address: str) -> str:
    """Replace street type variants with their normalized form."""
    result = address.lower()
    # Sort by length descending so longer variants match first
    # e.g. "boulevard" before "blvd"
    for variant in sorted(STREET_TYPE_MAP.keys(), key=len, reverse=True):
        pattern = r"\b" + re.escape(variant) + r"\b"
        result = re.sub(pattern, STREET_TYPE_MAP[variant], result)
    return result


def normalize_address(address) -> str:
    """
    Full normalization pipeline for a Quebec address.
    Steps: strip unit → normalize street type → collapse whitespace → uppercase.
    Handles None, NaN, and empty inputs gracefully.
    """
    if address is None:
        return ""
    text = str(address).strip()
    if text.lower() in ("", "nan", "none"):
        return ""

    text = strip_unit_number(text)
    text = normalize_street_type(text)
    text = re.sub(r"\s+", " ", text)  # collapse whitespace
    text = text.strip().upper()
    return text
