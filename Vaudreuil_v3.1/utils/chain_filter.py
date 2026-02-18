"""
Chain, franchise, and large corporation filtering (v3: All-Sector).

Rebuilt from v2 for cross-sector scope in Vaudreuil-Dorion.
v2 was calibrated for Hamilton, Ontario manufacturing (included Stelco,
Dofasco, ArcelorMittal). v3 is calibrated for Quebec across all sectors.

Three detection layers:
  1. Brand name match (chains/franchises across all sectors)
  2. Corporate pattern detection (multi-location, investor pages)
  3. URL patterns indicating large operations
"""

import re
from typing import Tuple


# ── Known chains and franchises (Quebec-calibrated, all sectors) ─────────────
KNOWN_CHAINS = [
    # National/international retail chains
    "walmart", "costco", "canadian tire", "home depot", "rona",
    "home hardware", "loblaws", "dollarama", "dollar tree",
    "staples", "bureau en gros", "best buy",
    "winners", "marshalls", "homesense",
    "ikea", "structube",

    # Quebec grocery and pharmacy
    "metro", "iga", "maxi", "provigo", "super c",
    "jean coutu", "pharmaprix", "shoppers drug mart",
    "rachelle béry",

    # Restaurant and food chains
    "tim hortons", "mcdonald", "subway", "starbucks",
    "a&w", "harvey's", "wendy's", "burger king",
    "pizza hut", "domino", "papa john",
    "st-hubert", "scores", "benny", "la belle province",
    "valentine", "ashton", "mike's", "pacini",
    "couche-tard", "alimentation couche",
    "dunkin", "second cup", "van houtte",
    "première moisson",

    # Construction/hardware franchise chains
    "reno-depot", "patrick morin", "canac",
    "matériaux coupal", "groupe bmr", "bmr",

    # Automotive chains
    "napa auto", "mr. lube", "jiffy lube", "midas", "speedy",
    "kal tire", "fountain tire", "canadian tire auto",
    "active green+ross", "pneus touchette",

    # Banks and financial institutions
    "banque nationale", "td bank", "rbc", "bmo", "scotiabank",
    "cibc", "desjardins",

    # Telecom and utilities
    "bell canada", "rogers", "telus", "videotron",
    "hydro-quebec", "énergir", "gazifere",

    # Large Quebec-based corporations (not acquirable targets)
    "cascades", "saputo", "quebecor", "bombardier",
    "cae ", "pratt & whitney", "general electric",
    "siemens", "honeywell", "3m", "dupont",

    # National service chains
    "servicemaster", "cintas", "iron mountain",
    "waste management", "gdi services", "bee-clean",
    "adecco", "manpower", "randstad",
    "h&r block", "liberty tax",

    # Hotel/accommodation chains
    "holiday inn", "comfort inn", "best western",
    "marriott", "hilton", "super 8", "days inn",

    # Fitness chains
    "goodlife", "fit4less", "nautilus plus", "econofitness",
    "anytime fitness",

    # Convenience/gas
    "petro-canada", "shell", "esso", "ultramar",
    "irving",
]

# ── Corporate pattern indicators ─────────────────────────────────────────────
CORPORATE_INDICATORS = [
    "holdings", "worldwide", "global ",
    "north america", "amérique du nord",
    "multi-location", "multi-sites",
    "franchise", "franchisé",
    "investor relations", "relations investisseurs",
    "publicly traded", "cotée en bourse",
    "tsx:", "tsxv:", "nyse:", "nasdaq:",
]

# ── Website patterns that indicate large operations ──────────────────────────
CORPORATE_URL_PATTERNS = [
    r"investor", r"careers\..*\.com", r"franchise\.",
    r"locations\.", r"store-locator", r"find-a-store",
    r"find-a-location",
]


def is_chain_or_franchise(company_name: str, website: str = "",
                          industry_desc: str = "") -> Tuple[bool, str]:
    """
    Check if a business is a chain, franchise, or large corporation.

    Returns:
        Tuple of (is_excluded: bool, reason: str)
    """
    name_lower = company_name.lower().strip()
    web_lower = (website or "").lower().strip()
    desc_lower = (industry_desc or "").lower().strip()

    # Layer 1: Brand name match
    for chain in KNOWN_CHAINS:
        if chain in name_lower:
            return True, f"Known chain: {chain}"

    # Layer 2: Corporate indicators in name or description
    for indicator in CORPORATE_INDICATORS:
        if indicator in name_lower:
            return True, f"Corporate indicator: {indicator}"
        if indicator in desc_lower:
            return True, f"Corporate indicator in desc: {indicator}"

    # Layer 3: Corporate URL patterns
    for pattern in CORPORATE_URL_PATTERNS:
        if re.search(pattern, web_lower):
            return True, f"Corporate URL: {pattern}"

    return False, ""


def filter_chains(df):
    """
    Apply chain/franchise filtering to a DataFrame.
    Returns (filtered_df, list_of_excluded_entries).
    """
    import pandas as pd

    excluded = []
    keep_mask = []

    for _, row in df.iterrows():
        name = str(row.get("company_name", ""))
        website = str(row.get("website", "")) if pd.notna(row.get("website")) else ""
        desc = str(row.get("industry_description", "")) if pd.notna(row.get("industry_description")) else ""

        is_excluded, reason = is_chain_or_franchise(name, website, desc)
        keep_mask.append(not is_excluded)

        if is_excluded:
            excluded.append({"company_name": name, "reason": reason})

    result = df[keep_mask].copy()
    return result, excluded
