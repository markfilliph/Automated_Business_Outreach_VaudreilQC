"""
Fuzzy matching for business deduplication.

Strategy (in order of priority):
  1. Phone number exact match — phone is the most unique identifier.
  2. Fuzzy name similarity (>85%) AND postal code exact match — catches
     legal name vs trade name mismatches (e.g. "9123-4567 Québec Inc" vs
     "Construction Tremblay").

Returns groups of duplicate indices so the caller can decide which row to keep.
"""

import re
import pandas as pd
from rapidfuzz import fuzz

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import FUZZY_NAME_THRESHOLD


def normalize_phone(phone) -> str:
    """Strip to digits only. Returns empty string if unusable."""
    if phone is None:
        return ""
    text = str(phone).strip()
    if text.lower() in ("nan", "none", ""):
        return ""
    return re.sub(r"\D", "", text)


def normalize_name(name) -> str:
    """Lowercase + strip for fuzzy comparison."""
    if name is None:
        return ""
    text = str(name).strip()
    if text.lower() in ("nan", "none", ""):
        return ""
    return text.lower()


def find_duplicates(df: pd.DataFrame) -> list:
    """
    Identify groups of duplicate rows in the DataFrame.

    Returns:
        List of lists — each inner list contains DataFrame indices
        that refer to the same business.

    Example: [[0, 5], [12, 18, 22]] means rows 0&5 are duplicates,
             and rows 12, 18, 22 are all the same business.
    """
    groups = []
    assigned = set()

    # ─── Pass 1: Phone number exact match ─────────────────────────────
    # Build a lookup: normalized_phone → list of row indices
    phone_lookup = {}
    for idx, row in df.iterrows():
        phone = normalize_phone(row.get("phone_normalized", row.get("phone", "")))
        if phone == "":
            continue
        phone_lookup.setdefault(phone, []).append(idx)

    for phone, indices in phone_lookup.items():
        if len(indices) > 1:
            groups.append(indices)
            assigned.update(indices)

    print(f"    [Phone Match] {len([g for g in groups])} duplicate groups found")

    # ─── Pass 2: Fuzzy name + postal code ──────────────────────────────
    # Only look at rows not already matched by phone
    unassigned = df[~df.index.isin(assigned)].copy()

    if len(unassigned) == 0:
        return groups

    # Group by postal code first — postal code MUST match exactly.
    # This massively reduces the O(n²) comparison space.
    postal_col = "postal_code"
    fuzzy_group_count = 0

    for postal, idx_group in unassigned.groupby(postal_col).groups.items():
        if postal is None or str(postal).lower() in ("nan", "none", ""):
            continue
        indices = list(idx_group)
        if len(indices) <= 1:
            continue

        # Within this postal group, compare all pairs
        locally_assigned = set()
        for i in range(len(indices)):
            if indices[i] in locally_assigned:
                continue
            group = [indices[i]]
            name_a = normalize_name(df.loc[indices[i], "company_name"])

            for j in range(i + 1, len(indices)):
                if indices[j] in locally_assigned:
                    continue
                name_b = normalize_name(df.loc[indices[j], "company_name"])

                score = fuzz.ratio(name_a, name_b)
                if score >= FUZZY_NAME_THRESHOLD:
                    group.append(indices[j])
                    locally_assigned.add(indices[j])

            if len(group) > 1:
                groups.append(group)
                locally_assigned.update(group)
                fuzzy_group_count += 1

    print(f"    [Fuzzy Match] {fuzzy_group_count} additional duplicate groups found")

    return groups
