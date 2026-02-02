"""
STEP 6: SCORE & RANK

Calculates a weighted composite score (0-100) for each candidate based on
four factors. Unknown values get a moderate default — we don't penalize
leads just because we couldn't scrape one data point.

Score components:
  - Years in business   (35%) — from REQ registration date. Older = better.
  - Review count        (25%) — from Google Places. More reviews = more established.
  - Sector fit          (25%) — keyword match strength against target industries.
  - Employee count      (15%) — sweet spot is 10-50 employees for acquisition targets.

Weights are defined in config.py (WEIGHT_*).

Input:  data/req_enriched.csv
Output: data/scored_candidates.csv  (sorted descending by total_score)
"""

import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import (
    CHECKPOINT_REQ,
    CHECKPOINT_SCORED,
    WEIGHT_YEARS_IN_BUSINESS,
    WEIGHT_REVIEW_COUNT,
    WEIGHT_SECTOR_FIT,
    WEIGHT_EMPLOYEE_COUNT,
    TARGET_KEYWORDS,
    MAX_ANNUAL_REVENUE,
)


# ─── Individual scoring functions ────────────────────────────────────────────


def score_years_in_business(row: pd.Series) -> float:
    """
    Older businesses score higher. 30 years = 100 points.
    Unknown registration date → 15 points (equivalent to ~4.5 years).

    NOTE: Default lowered from 30 to 15 so unverified leads don't
    outrank verified young businesses (a 2-year verified company
    should beat an unverified unknown).
    """
    reg_date = row.get("req_registration_date")
    if pd.isna(reg_date) or reg_date is None:
        return 15.0  # ~4.5 year equivalent, not 9 years

    try:
        reg = pd.to_datetime(reg_date)
        years = (datetime.now() - reg).days / 365.25
        return min((years / 30.0) * 100, 100.0)
    except Exception:
        return 15.0


def score_review_count(row: pd.Series) -> float:
    """
    More Google reviews = more established business. 100 reviews = 100 points.
    Unknown or 0 reviews → 0 points.
    """
    count = row.get("review_count", 0)
    if pd.isna(count):
        count = 0
    return min((float(count) / 100.0) * 100, 100.0)


def score_sector_fit(row: pd.Series) -> float:
    """
    How well does this business match our target manufacturing keywords?
    Each keyword hit = 25 points. Caps at 100.
    """
    text = (
        str(row.get("industry_description", "")).lower()
        + " "
        + str(row.get("company_name", "")).lower()
    )
    matches = sum(1 for kw in TARGET_KEYWORDS if kw.lower() in text)
    return min(matches * 25.0, 100.0)


def score_employee_count(row: pd.Series) -> float:
    """
    Sweet spot for acquisition targets: 10-50 employees = 100 points.
    Tapers off for smaller or larger companies.
    Unknown → 15 points (conservative default).
    """
    emp = row.get("num_employees")
    if pd.isna(emp):
        return 15.0

    emp = float(emp)
    if 10 <= emp <= 50:
        return 100.0   # Sweet spot
    elif 5 <= emp < 10:
        return 70.0    # Slightly small
    elif 50 < emp <= 100:
        return 70.0    # Slightly large
    elif emp > 100:
        return 50.0    # Too large for typical acquisition
    else:
        return 20.0    # Very small


# ─── Verification penalty ────────────────────────────────────────────────────

UNVERIFIED_PENALTY = 0.90  # Unverified leads get 10% penalty


def calculate_total_score(row: pd.Series) -> float:
    """
    Weighted sum of all component scores. Result is 0-100.
    Unverified leads receive a 10% penalty to prevent them from
    outranking verified businesses with known data.
    """
    base_score = (
        score_years_in_business(row) * WEIGHT_YEARS_IN_BUSINESS
        + score_review_count(row) * WEIGHT_REVIEW_COUNT
        + score_sector_fit(row) * WEIGHT_SECTOR_FIT
        + score_employee_count(row) * WEIGHT_EMPLOYEE_COUNT
    )

    # Apply penalty for unverified leads
    if row.get("verification_status") != "Verified":
        base_score *= UNVERIFIED_PENALTY

    return round(base_score, 2)


def main():
    print("=" * 60)
    print(" STEP 6: SCORE & RANK")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_REQ)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_REQ}\n")

    # ── Filter by revenue cap ────────────────────────────────────────────
    # Keep companies with revenue <= $2M OR unknown revenue (can't exclude unknowns)
    before_count = len(df)
    df = df[
        (df["annual_revenue"].isna()) |
        (df["annual_revenue"] == 0) |
        (df["annual_revenue"] <= MAX_ANNUAL_REVENUE)
    ].copy()
    filtered_out = before_count - len(df)
    if filtered_out > 0:
        print(f"  [FILTER] Removed {filtered_out} companies with revenue > ${MAX_ANNUAL_REVENUE/1_000_000:.0f}M")
        print(f"  [FILTER] Remaining: {len(df)} candidates\n")

    # ── Calculate component scores ──────────────────────────────────────
    df["score_years"] = df.apply(score_years_in_business, axis=1)
    df["score_reviews"] = df.apply(score_review_count, axis=1)
    df["score_sector"] = df.apply(score_sector_fit, axis=1)
    df["score_employees"] = df.apply(score_employee_count, axis=1)

    # ── Composite score ─────────────────────────────────────────────────
    df["total_score"] = df.apply(calculate_total_score, axis=1)

    # ── Sort and rank ───────────────────────────────────────────────────
    df = df.sort_values("total_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # ── Preview ─────────────────────────────────────────────────────────
    print("  Top 10 candidates:\n")
    print(f"  {'#':<5} {'Company':<40} {'Score':<8} {'Verified'}")
    print(f"  {'─'*5} {'─'*40} {'─'*8} {'─'*10}")
    for _, row in df.head(10).iterrows():
        verified = "✓" if row.get("verification_status") == "Verified" else "○"
        print(f"  {int(row['rank']):<5} {str(row['company_name'])[:40]:<40} {row['total_score']:<8} {verified}")

    print(f"\n  [OUTPUT] Scored candidates: {len(df)}")
    df.to_csv(CHECKPOINT_SCORED, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved → {CHECKPOINT_SCORED}")


if __name__ == "__main__":
    main()
