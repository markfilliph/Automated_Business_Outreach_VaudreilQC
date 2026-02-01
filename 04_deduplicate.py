"""
STEP 4: DEDUPLICATE

Merges duplicate business entries that appeared in both iCRIQ and YellowPages.
The same company can appear in both sources with slightly different names,
addresses, and data completeness.

WHY RUN BEFORE REQ SCRAPING?
  Google Places normalizes addresses and phone numbers effectively, making
  fuzzy matching more accurate. Running dedup here avoids scraping the
  government registry twice for the same company (saves time, reduces IP risk).

Matching strategy (handled by utils/fuzzy_match.py):
  1. Phone number exact match (primary) — most unique identifier.
  2. Fuzzy name match (>85% similarity) + postal code exact match (fallback).
     This catches cases like "Construction Tremblay" vs "Groupe Tremblay"
     at the same postal code.

When duplicates are found: keep the row with the most non-null fields
(i.e. the most complete record).

Input:  data/google_enriched.csv
Output: data/deduped_candidates.csv
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CHECKPOINT_GOOGLE, CHECKPOINT_DEDUPED
from utils.fuzzy_match import find_duplicates, normalize_phone


def main():
    print("=" * 60)
    print(" STEP 4: DEDUPLICATE")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_GOOGLE)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_GOOGLE}\n")

    # ── Prepare phone column for matching ───────────────────────────────
    df["phone_normalized"] = df["phone"].apply(normalize_phone)

    # ── Find duplicate groups ───────────────────────────────────────────
    duplicate_groups = find_duplicates(df)

    # ── Resolve: keep the most complete row in each group ──────────────
    indices_to_drop = []
    for group in duplicate_groups:
        if len(group) <= 1:
            continue

        # Score each row by how many fields are non-null
        group_df = df.loc[group]
        completeness = group_df.notna().sum(axis=1)

        # Keep the row with highest completeness
        best_idx = completeness.idxmax()
        drop_indices = [idx for idx in group if idx != best_idx]
        indices_to_drop.extend(drop_indices)

    # ── Apply drops ─────────────────────────────────────────────────────
    df = df.drop(index=indices_to_drop).copy()

    # Clean up the temp column
    df = df.drop(columns=["phone_normalized"], errors="ignore")

    print(f"\n  [Dedup] Removed {len(indices_to_drop)} duplicate rows")
    print(f"\n  [OUTPUT] Deduplicated candidates: {len(df)}")
    df.to_csv(CHECKPOINT_DEDUPED, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved → {CHECKPOINT_DEDUPED}")


if __name__ == "__main__":
    main()
