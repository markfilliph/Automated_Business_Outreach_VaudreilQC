"""
STEP 2: FILTER (v3: All-Sector)

Applies five filtering gates. v3 flips the logic from v2:
  v2: Include manufacturing -> exclude non-manufacturing
  v3: Include everything -> exclude retail, restaurants, chains, subsidiaries

Gate 1 — Region:       Keep only Vaudreuil-area postal codes.
Gate 2 — Exclusions:   Remove retail stores and restaurants (by keyword).
Gate 3 — Chains:       Remove known chains, franchises, and large corporations.
Gate 4 — Subsidiaries: NEW: Flag/remove multinational subsidiary operations.
Gate 5 — Employees:    Keep businesses in the 5-200 employee range.
                       Rows with UNKNOWN employee counts are KEPT.

Input:  data/raw_candidates.csv
Output: data/filtered_candidates.csv
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CHECKPOINT_RAW,
    CHECKPOINT_FILTERED,
    TARGET_POSTAL_PREFIXES,
    EXCLUDED_SECTOR_KEYWORDS,
    MIN_EMPLOYEES,
    MAX_EMPLOYEES,
    CHAIN_FILTER_ENABLED,
    SUBSIDIARY_FILTER_ENABLED,
)
from utils.chain_filter import filter_chains
from utils.subsidiary_detector import flag_subsidiaries


def filter_by_region(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only businesses whose postal code starts with a Vaudreuil prefix."""
    before = len(df)
    postal_prefix = df["postal_code"].astype(str).str[:3].str.upper()
    mask = postal_prefix.isin(TARGET_POSTAL_PREFIXES)
    df = df[mask].copy()
    print(f"  [Region]       {before:>5} -> {len(df):>5}  (prefixes: {TARGET_POSTAL_PREFIXES})")
    return df


def filter_by_excluded_sectors(df: pd.DataFrame) -> pd.DataFrame:
    """
    v3: Remove retail stores and restaurants.
    Checks company name AND industry description for excluded keywords.

    IMPORTANT: Some keywords contain spaces to avoid false positives.
    Example: "bar " won't match "Barnaby" but will match "Bar Le Central".
    """
    before = len(df)

    combined_text = (
        df["company_name"].fillna("").astype(str).str.lower()
        + " | "
        + df.get("industry_description", pd.Series([""] * len(df))).fillna("").astype(str).str.lower()
    )

    def is_excluded(text):
        for kw in EXCLUDED_SECTOR_KEYWORDS:
            if kw.lower() in text:
                return True
        return False

    exclude_mask = combined_text.apply(is_excluded)

    excluded_names = df[exclude_mask]["company_name"].tolist()
    df = df[~exclude_mask].copy()

    print(f"  [Sector]       {before:>5} -> {len(df):>5}  (removed {len(excluded_names)} retail/restaurant/other)")
    if excluded_names:
        for name in excluded_names[:8]:
            print(f"                 x {str(name)[:55]}")
        if len(excluded_names) > 8:
            print(f"                 ... and {len(excluded_names) - 8} more")

    return df


def filter_by_chains(df: pd.DataFrame) -> pd.DataFrame:
    """Remove known chains, franchises, and large corporations."""
    if not CHAIN_FILTER_ENABLED:
        print(f"  [Chains]       SKIPPED (disabled in config)")
        return df

    before = len(df)
    df, excluded = filter_chains(df)

    print(f"  [Chains]       {before:>5} -> {len(df):>5}  (removed {len(excluded)} chains/franchises)")
    if excluded:
        for entry in excluded[:5]:
            print(f"                 x {entry['company_name'][:35]} ({entry['reason']})")
        if len(excluded) > 5:
            print(f"                 ... and {len(excluded) - 5} more")

    return df


def filter_by_subsidiaries(df: pd.DataFrame) -> pd.DataFrame:
    """
    NEW (v3): Detect and remove subsidiaries of large/public corporations.
    This is the single highest-value filter for clean acquisition leads.
    Companies that are divisions of multinationals are not acquirable targets.
    """
    if not SUBSIDIARY_FILTER_ENABLED:
        print(f"  [Subsidiary]   SKIPPED (disabled in config)")
        return df

    before = len(df)
    df, flagged = flag_subsidiaries(df)

    removed = len(flagged)
    print(f"  [Subsidiary]   {before:>5} -> {len(df):>5}  (removed {removed} subsidiary/division)")
    if flagged:
        for entry in flagged[:5]:
            print(f"                 x {entry['company_name'][:35]} ({entry['reason']})")
        if len(flagged) > 5:
            print(f"                 ... and {len(flagged) - 5} more")

    return df


def filter_by_employee_count(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep businesses in the MIN-MAX employee range.
    Rows where employee count is unknown (NaN) are KEPT.
    """
    before = len(df)
    emp = pd.to_numeric(df["num_employees"], errors="coerce")
    in_range = emp.between(MIN_EMPLOYEES, MAX_EMPLOYEES)
    unknown = emp.isna()
    mask = in_range | unknown
    df = df[mask].copy()
    print(f"  [Employees]    {before:>5} -> {len(df):>5}  (range {MIN_EMPLOYEES}-{MAX_EMPLOYEES}, unknowns kept)")
    return df


def main():
    print("=" * 60)
    print(" STEP 2: FILTER (v3: All-Sector)")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_RAW)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_RAW}\n")

    df = filter_by_region(df)
    df = filter_by_excluded_sectors(df)   # v3: replaces category + exclusions
    df = filter_by_chains(df)
    df = filter_by_subsidiaries(df)       # NEW v3 gate
    df = filter_by_employee_count(df)

    print(f"\n  [OUTPUT] Filtered candidates: {len(df)}")
    df.to_csv(CHECKPOINT_FILTERED, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved -> {CHECKPOINT_FILTERED}")


if __name__ == "__main__":
    main()
