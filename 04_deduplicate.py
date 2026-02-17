"""
STEP 4: DEDUPLICATE

Removes duplicate companies from the enriched dataset using three
deduplication strategies applied in sequence:

  1. Exact match: google_place_id (already done in 00/01, but recheck)
  2. Fuzzy name match: Levenshtein ratio on normalized company names
  3. Phone match: Same phone number = same company

Each duplicate pair is resolved by keeping the row with more data
(higher field completion count). The other row is dropped.

This step runs BEFORE REQ enrichment (step 05) because:
  - REQ lookups cost ~12 seconds each
  - Deduplicating 200 companies down to 160 saves ~8 minutes of
    government registry queries
  - Duplicate REQ queries for the same company waste rate-limit budget

Input:  data/google_enriched.csv
Output: data/deduped_candidates.csv
"""

import pandas as pd
import re
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CHECKPOINT_GOOGLE,
    CHECKPOINT_DEDUPED,
    FUZZY_NAME_THRESHOLD,
)


# ── Name normalization ────────────────────────────────────────────────────────

# Suffixes that don't affect identity (case-insensitive)
LEGAL_SUFFIXES = [
    r"\binc\.?\b", r"\bltee\.?\b", r"\bltee\.?\b", r"\bltd\.?\b",
    r"\benr\.?\b", r"\bs\.e\.n\.c\.?\b", r"\bsenc\b",
    r"\bcorp\.?\b", r"\bco\.?\b", r"\bcie\.?\b",
    r"\bgroup\b", r"\bgroupe\b",
]

# Common words that add noise but not identity signal
NOISE_WORDS = [
    r"\bles\b", r"\bla\b", r"\ble\b", r"\bde\b", r"\bdu\b",
    r"\bet\b", r"\band\b", r"\bthe\b", r"\bdes\b",
]


def normalize_name(name):
    """Normalize a company name for comparison.

    Steps:
      1. Lowercase
      2. Remove legal suffixes (inc, ltee, enr, etc.)
      3. Remove noise words (les, la, de, du, et)
      4. Strip punctuation (periods, commas, hyphens)
      5. Collapse whitespace
    """
    if pd.isna(name):
        return ""

    s = str(name).lower().strip()

    # Remove legal suffixes
    for pattern in LEGAL_SUFFIXES:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)

    # Remove noise words
    for pattern in NOISE_WORDS:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)

    # Strip punctuation
    s = re.sub(r"[.\-,/()&'\"]", " ", s)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


def name_similarity(a, b):
    """Calculate similarity ratio between two normalized names.

    Uses Levenshtein-based ratio. Returns float 0.0 to 100.0.
    Falls back to simple set-based overlap if no Levenshtein library.
    """
    if not a or not b:
        return 0.0

    try:
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, a, b).ratio() * 100
        return ratio
    except Exception:
        return 0.0


def data_completeness(row):
    """Count non-empty fields in a row. Higher = better data."""
    count = 0
    for val in row:
        if pd.notna(val) and str(val).strip() not in ("", "nan", "None", "N/A"):
            count += 1
    return count


# ── Dedup strategies ──────────────────────────────────────────────────────────

def dedup_by_place_id(df):
    """Remove exact duplicates by google_place_id."""
    before = len(df)

    has_pid = df["google_place_id"].notna() & (df["google_place_id"] != "")
    # For rows with a place_id, keep the one with more data
    df["_completeness"] = df.apply(data_completeness, axis=1)
    df = df.sort_values("_completeness", ascending=False)
    df = df.drop_duplicates(subset=["google_place_id"], keep="first")
    df = df.drop(columns=["_completeness"])

    removed = before - len(df)
    if removed > 0:
        print(f"    Place ID dedup: removed {removed}")
    return df


def dedup_by_phone(df):
    """Remove duplicates sharing the same phone number."""
    before = len(df)

    # Normalize phone: strip non-digits
    df["_phone_clean"] = df["phone"].apply(
        lambda x: re.sub(r"[^\d]", "", str(x)) if pd.notna(x) else ""
    )

    # Only match on 10+ digit numbers (skip empties and short numbers)
    valid_phone = df["_phone_clean"].str.len() >= 10
    df_valid = df[valid_phone].copy()
    df_invalid = df[~valid_phone].copy()

    if len(df_valid) > 0:
        df_valid["_completeness"] = df_valid.apply(data_completeness, axis=1)
        df_valid = df_valid.sort_values("_completeness", ascending=False)
        df_valid = df_valid.drop_duplicates(subset=["_phone_clean"], keep="first")
        df_valid = df_valid.drop(columns=["_completeness"])

    df = pd.concat([df_valid, df_invalid], ignore_index=True)
    df = df.drop(columns=["_phone_clean"])

    removed = before - len(df)
    if removed > 0:
        print(f"    Phone dedup: removed {removed}")
    return df


def dedup_by_fuzzy_name(df, threshold=None):
    """Remove near-duplicate company names using fuzzy matching.

    O(n^2) comparison, so only practical for < 1000 rows.
    For larger datasets, this should use blocking (by first letter
    or postal code prefix) to reduce comparisons.
    """
    if threshold is None:
        threshold = FUZZY_NAME_THRESHOLD

    before = len(df)

    # Pre-compute normalized names
    df["_norm_name"] = df["company_name"].apply(normalize_name)

    # Block by first 3 characters to reduce O(n^2) comparisons
    # Companies with the same first 3 chars of normalized name are candidates
    drop_indices = set()

    df["_completeness"] = df.apply(data_completeness, axis=1)

    # Group by first 3 chars for blocking
    df["_block"] = df["_norm_name"].str[:3]

    for block_key, group in df.groupby("_block"):
        if len(group) < 2:
            continue

        indices = group.index.tolist()
        for i in range(len(indices)):
            if indices[i] in drop_indices:
                continue
            for j in range(i + 1, len(indices)):
                if indices[j] in drop_indices:
                    continue

                name_a = df.at[indices[i], "_norm_name"]
                name_b = df.at[indices[j], "_norm_name"]

                sim = name_similarity(name_a, name_b)
                if sim >= threshold:
                    # Keep the row with more data
                    comp_a = df.at[indices[i], "_completeness"]
                    comp_b = df.at[indices[j], "_completeness"]
                    if comp_b > comp_a:
                        drop_indices.add(indices[i])
                    else:
                        drop_indices.add(indices[j])

    if drop_indices:
        df = df.drop(index=list(drop_indices))

    df = df.drop(columns=["_norm_name", "_block", "_completeness"])

    removed = before - len(df)
    if removed > 0:
        print(f"    Fuzzy name dedup: removed {removed}")
    return df


def main():
    print("=" * 60)
    print(" STEP 4: DEDUPLICATE")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_GOOGLE)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_GOOGLE}")

    # Strategy 1: Place ID (exact)
    print("\n  Running dedup strategies:")
    if "google_place_id" in df.columns:
        df = dedup_by_place_id(df)

    # Strategy 2: Phone number
    if "phone" in df.columns:
        df = dedup_by_phone(df)

    # Strategy 3: Fuzzy company name
    if len(df) <= 1000:
        df = dedup_by_fuzzy_name(df)
    else:
        print(f"    [SKIP] Fuzzy name dedup skipped ({len(df)} rows > 1000 limit)")
        print(f"           Use postal code blocking for larger datasets")

    # Reset index
    df = df.reset_index(drop=True)

    # Save
    os.makedirs(os.path.dirname(CHECKPOINT_DEDUPED), exist_ok=True)
    df.to_csv(CHECKPOINT_DEDUPED, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] {len(df)} unique candidates -> {CHECKPOINT_DEDUPED}")

    # Source breakdown after dedup
    if "data_source" in df.columns:
        print(f"\n  Source breakdown (post-dedup):")
        for source, count in df["data_source"].value_counts().items():
            print(f"    {source:20s} {count:>5}")


if __name__ == "__main__":
    main()
