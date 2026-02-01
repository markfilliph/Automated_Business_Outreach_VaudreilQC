"""
STEP 2: FILTER

Applies four filtering gates to narrow the raw candidate list.
Gates are simple functions — no classes, no decorators.

Gate 1 — Region:     Keep only Vaudreuil-area postal codes.
Gate 2 — Category:   Keep only manufacturing businesses (SIC code OR keyword match).
Gate 3 — Exclusions: Remove restaurants, retail, services (false positives from "usine" etc.)
Gate 4 — Employees:  Keep businesses in the 5-200 employee sweet spot.
                     Rows with UNKNOWN employee counts are KEPT (not discarded).

Input:  data/raw_candidates.csv
Output: data/filtered_candidates.csv
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import (
    CHECKPOINT_RAW,
    CHECKPOINT_FILTERED,
    TARGET_POSTAL_PREFIXES,
    TARGET_KEYWORDS,
    TARGET_SIC_RANGE,
    MIN_EMPLOYEES,
    MAX_EMPLOYEES,
)

# ─── NEGATIVE KEYWORDS ───────────────────────────────────────────────────────
# Exclude businesses that match manufacturing keywords but are actually retail/service
EXCLUDE_KEYWORDS = [
    # Food service (not food processing/manufacturing)
    "restaurant",
    "café",
    "cafe",
    "bistro",
    "bar",
    "pub",
    "souvlaki",
    "pizza",
    "sushi",
    "diner",
    "grill",
    "bakery",  # retail bakery, not industrial
    "boulangerie",
    "patisserie",
    "traiteur",
    "catering",
    # Retail
    "store",
    "magasin",
    "boutique",
    "shop",
    "retail",
    "grocery",
    "épicerie",
    "supermarket",
    "pharmacy",
    "pharmacie",
    # Services
    "salon",
    "spa",
    "gym",
    "fitness",
    "dentist",
    "clinic",
    "clinique",
    "hospital",
    "hotel",
    "motel",
    "school",
    "école",
    "daycare",
    "garderie",
    "church",
    "église",
    # Auto (unless auto manufacturing)
    "car wash",
    "lave-auto",
    "gas station",
    "station-service",
    "tire",
    "pneu",
]


def filter_by_region(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only businesses whose postal code starts with a Vaudreuil prefix."""
    before = len(df)
    postal_prefix = df["postal_code"].astype(str).str[:3].str.upper()
    mask = postal_prefix.isin(TARGET_POSTAL_PREFIXES)
    df = df[mask].copy()
    print(f"  [Region]    {before:>5} → {len(df):>5}  (prefixes: {TARGET_POSTAL_PREFIXES})")
    return df


def filter_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Keep manufacturing businesses matched by SIC code OR industry keywords."""
    before = len(df)

    # ── SIC code match ──
    sic_numeric = pd.to_numeric(df["sic_code"], errors="coerce")
    sic_mask = sic_numeric.between(TARGET_SIC_RANGE[0], TARGET_SIC_RANGE[1])

    # ── Keyword match on industry description + company name ──
    text = (
        df["industry_description"].fillna("").astype(str).str.lower()
        + " "
        + df["company_name"].fillna("").astype(str).str.lower()
    )
    keyword_mask = text.apply(
        lambda t: any(kw.lower() in t for kw in TARGET_KEYWORDS)
    )

    # Keep if EITHER SIC or keyword matches
    df = df[sic_mask | keyword_mask].copy()
    print(f"  [Category]  {before:>5} → {len(df):>5}  (manufacturing match)")
    return df


def filter_by_exclusions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove false positives: businesses that matched manufacturing keywords
    but are actually restaurants, retail, or services.

    Example: "Usine Grecque Souvlaki" matches "usine" but is a restaurant.

    IMPORTANT: Only check company name for exclusions, NOT industry_description.
    Google Places labels many legitimate manufacturers as "store" or "establishment"
    which would cause false exclusions.
    """
    before = len(df)

    # Only check company name — Google's industry labels are unreliable
    company_names = df["company_name"].fillna("").astype(str).str.lower()

    # Exclude if company name contains a clear non-manufacturing indicator
    exclude_mask = company_names.apply(
        lambda name: any(kw.lower() in name for kw in EXCLUDE_KEYWORDS)
    )

    excluded = df[exclude_mask]["company_name"].tolist()
    df = df[~exclude_mask].copy()

    print(f"  [Exclude]   {before:>5} → {len(df):>5}  (removed {len(excluded)} non-manufacturing)")
    if excluded:
        for name in excluded[:5]:  # Show first 5
            print(f"              ✗ {name[:50]}")
        if len(excluded) > 5:
            print(f"              ... and {len(excluded) - 5} more")

    return df


def filter_by_employee_count(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep businesses in the MIN-MAX employee range.
    IMPORTANT: Rows where employee count is unknown (NaN) are KEPT.
    We don't discard leads just because we lack one data point.
    """
    before = len(df)
    emp = pd.to_numeric(df["num_employees"], errors="coerce")
    in_range = emp.between(MIN_EMPLOYEES, MAX_EMPLOYEES)
    unknown = emp.isna()
    mask = in_range | unknown
    df = df[mask].copy()
    print(f"  [Employees] {before:>5} → {len(df):>5}  (range {MIN_EMPLOYEES}-{MAX_EMPLOYEES}, unknowns kept)")
    return df


def main():
    print("=" * 60)
    print(" STEP 2: FILTER")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_RAW)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_RAW}\n")

    df = filter_by_region(df)
    df = filter_by_category(df)
    df = filter_by_exclusions(df)
    df = filter_by_employee_count(df)

    print(f"\n  [OUTPUT] Filtered candidates: {len(df)}")
    df.to_csv(CHECKPOINT_FILTERED, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved → {CHECKPOINT_FILTERED}")


if __name__ == "__main__":
    main()
