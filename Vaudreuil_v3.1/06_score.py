"""
STEP 6: SCORE & RANK (v3: All-Sector)

v3 changes from v2:
  - "Sector fit" replaced by "Sector signal" using cross-sector keywords
  - NEW: "Ownership signal" component (independent business indicators)
  - Revenue cap raised to $5M
  - Review count weight reduced (biased toward B2C, less reliable for trades)
  - Employee count weight increased (matters across all sectors)
  - Qualification threshold lowered to 40 (broader sweep)

Score components (100-point scale, 8 factors):
  - Years in business     (25%) — REQ registration date
  - Review count          (10%) — Google Places (reduced from 15%)
  - Sector signal         (15%) — high-value sector keyword match
  - Employee count        (15%) — sweet spot 10-50 for acquisition
  - Data quality          (15%) — completeness of lead data
  - Website presence      (10%) — has working, validated website
  - Location bonus         (5%) — core Vaudreuil postal codes
  - Ownership signal       (5%) — NEW: independent ownership indicators

Input:  data/req_enriched.csv
Output: data/scored_candidates.csv
"""

import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CHECKPOINT_REQ,
    CHECKPOINT_SCORED,
    WEIGHT_YEARS_IN_BUSINESS,
    WEIGHT_REVIEW_COUNT,
    WEIGHT_SECTOR_SIGNAL,
    WEIGHT_EMPLOYEE_COUNT,
    WEIGHT_DATA_QUALITY,
    WEIGHT_WEBSITE_PRESENCE,
    WEIGHT_LOCATION_BONUS,
    WEIGHT_OWNERSHIP_SIGNAL,
    HIGH_VALUE_SECTOR_KEYWORDS,
    MAX_ANNUAL_REVENUE,
    UNVERIFIED_PENALTY,
    QUALIFICATION_THRESHOLD,
    REVIEW_THRESHOLDS,
    REVENUE_ESTIMATION,
)


# ── Individual scoring functions ─────────────────────────────────────────────

def score_years_in_business(row: pd.Series) -> float:
    """
    Older businesses score higher. 30 years = 100 points.
    Unknown registration date = 15 points (conservative default).
    """
    reg_date = row.get("req_registration_date")
    if pd.isna(reg_date) or reg_date is None:
        return 15.0

    try:
        reg = pd.to_datetime(reg_date)
        years = (datetime.now() - reg).days / 365.25
        return min((years / 30.0) * 100, 100.0)
    except Exception:
        return 15.0


def score_review_count(row: pd.Series) -> float:
    """
    Granular review count thresholds.
    NOTE (v3): Weight reduced because reviews are biased toward B2C.
    A plumbing company with 3 reviews may be a $3M business.
    A precision machining shop with 0 reviews may be a $5M business.
    """
    count = row.get("review_count", 0)
    if pd.isna(count):
        count = 0
    count = float(count)

    if count < REVIEW_THRESHOLDS["very_low"]:
        return 10.0
    elif count < REVIEW_THRESHOLDS["low"]:
        return 30.0
    elif count < REVIEW_THRESHOLDS["moderate"]:
        return 50.0
    elif count < REVIEW_THRESHOLDS["good"]:
        return 70.0
    elif count < REVIEW_THRESHOLDS["excellent"]:
        return 85.0
    else:
        return 100.0


def score_sector_signal(row: pd.Series) -> float:
    """
    v3: Replaces manufacturing-only "sector_fit".
    Matches against HIGH_VALUE_SECTOR_KEYWORDS which span manufacturing,
    construction, trades, logistics, professional services, etc.
    Each keyword hit = 20 points (was 25 in v2). Caps at 100.
    """
    text = (
        str(row.get("industry_description", "")).lower()
        + " "
        + str(row.get("company_name", "")).lower()
    )
    matches = sum(1 for kw in HIGH_VALUE_SECTOR_KEYWORDS if kw.lower() in text)
    return min(matches * 20.0, 100.0)


def score_employee_count(row: pd.Series) -> float:
    """
    Sweet spot for acquisition targets: 10-50 employees = 100 points.
    v3: Weight increased to 15% because employee count is a strong
    signal across all sectors, not just manufacturing.
    """
    emp = row.get("num_employees")
    if pd.isna(emp):
        return 15.0

    emp = float(emp)
    if 10 <= emp <= 50:
        return 100.0
    elif 5 <= emp < 10:
        return 70.0
    elif 50 < emp <= 100:
        return 70.0
    elif emp > 100:
        return 50.0
    else:
        return 20.0


def score_data_quality(row: pd.Series) -> float:
    """Score based on completeness of lead data."""
    score = 0.0

    # Core fields (60 points total)
    if pd.notna(row.get("phone")) and str(row.get("phone")).strip():
        score += 15
    if pd.notna(row.get("website")) and str(row.get("website")).strip():
        score += 15
    if pd.notna(row.get("postal_code")) and str(row.get("postal_code")).strip():
        score += 10
    if pd.notna(row.get("address_raw")) and str(row.get("address_raw")).strip():
        score += 10
    if pd.notna(row.get("email")) and str(row.get("email")).strip():
        score += 10

    # Enrichment fields (40 points total)
    if pd.notna(row.get("google_place_id")):
        score += 10
    if row.get("verification_status") == "Verified":
        score += 15
    if pd.notna(row.get("num_employees")) and float(row.get("num_employees", 0)) > 0:
        score += 10
    if pd.notna(row.get("google_rating")) and float(row.get("google_rating", 0)) > 0:
        score += 5

    return min(score, 100.0)


def score_website_presence(row: pd.Series) -> float:
    """Score based on having a working, validated website."""
    website = row.get("website", "")
    if not website or str(website).lower() in ("nan", "none", "", "unknown"):
        return 0.0

    if pd.notna(row.get("website_valid")):
        if row.get("website_valid") == True:
            return 100.0
        elif row.get("website_valid") == False:
            return 10.0
        else:
            return 50.0

    return 50.0


def score_location_bonus(row: pd.Series) -> float:
    """Bonus for businesses in core Vaudreuil postal codes."""
    postal = str(row.get("postal_code", ""))[:3].upper()

    if postal == "J7V":
        return 100.0
    elif postal in ("J7X", "J7W"):
        return 70.0
    elif postal.startswith("J7"):
        return 40.0
    else:
        return 0.0


def score_ownership_signal(row: pd.Series) -> float:
    """
    NEW (v3): Score based on indicators of independent ownership.
    Owner-operated businesses are more likely acquisition targets.

    Positive signals: Inc./Ltée in name (incorporated, likely owner-held),
    single-location, local phone number, no parent company in REQ.
    Negative signals: "Canada" + "Inc" pattern (often subsidiary naming),
    corporate-style names.
    """
    name = str(row.get("company_name", "")).lower()
    score = 50.0  # Neutral baseline

    # Positive: typical Quebec small business naming patterns
    # "Les [X] Inc." or "[Name] Ltée" or "[Owner Name] et Fils"
    positive_patterns = [
        "ltée", "enr.", "et fils", "et filles", "& fils",
        "et associés", "et ass.", "& associés",
    ]
    for p in positive_patterns:
        if p in name:
            score += 25.0
            break

    # Positive: starts with "les " (very common Quebec small biz pattern)
    if name.startswith("les ") or name.startswith("la ") or name.startswith("le "):
        score += 10.0

    # Negative: has "canada" + corporate suffix (subsidiary naming convention)
    if "canada" in name and any(s in name for s in ["inc", "ltd", "corp", "ltée"]):
        score -= 20.0

    # Negative: "group" or "groupe" (often holding companies)
    if "group" in name or "groupe" in name:
        score -= 15.0

    # Check if REQ shows no parent company (positive signal)
    parent = row.get("req_parent_company", "")
    if pd.isna(parent) or str(parent).strip() in ("", "none", "nan", "n/a"):
        score += 15.0  # No parent = likely independent

    return max(min(score, 100.0), 0.0)


# ── Revenue estimation ───────────────────────────────────────────────────────

def estimate_revenue(row: pd.Series) -> dict:
    """
    Multi-factor revenue estimation.
    v3: Wider base range and confidence margin for cross-sector scope.
    """
    base_min, base_max = REVENUE_ESTIMATION["base_range"]
    midpoint = (base_min + base_max) / 2
    confidence = 25  # Lower base confidence for cross-sector

    adjustments = []

    # Factor 1: Review count
    reviews = float(row.get("review_count", 0)) if pd.notna(row.get("review_count")) else 0
    if reviews >= 50:
        adjustments.append(0.15)
        confidence += 12
    elif reviews >= 20:
        adjustments.append(0.08)
        confidence += 10
    elif reviews >= 10:
        adjustments.append(0.0)
        confidence += 7
    elif reviews >= 5:
        adjustments.append(-0.05)
        confidence += 4
    else:
        adjustments.append(-0.10)

    # Factor 2: Years in business
    reg_date = row.get("req_registration_date")
    if pd.notna(reg_date):
        try:
            years = (datetime.now() - pd.to_datetime(reg_date)).days / 365.25
            if years >= 20:
                adjustments.append(0.15)
                confidence += 12
            elif years >= 10:
                adjustments.append(0.05)
                confidence += 8
            elif years >= 5:
                adjustments.append(0.0)
                confidence += 4
            else:
                adjustments.append(-0.10)
        except Exception:
            pass

    # Factor 3: Employee count (v3: stronger signal than reviews)
    emp = row.get("num_employees")
    if pd.notna(emp):
        emp = float(emp)
        if emp >= 50:
            adjustments.append(0.20)
            confidence += 15
        elif emp >= 20:
            adjustments.append(0.10)
            confidence += 10
        elif emp >= 10:
            adjustments.append(0.0)
            confidence += 7
        elif emp >= 5:
            adjustments.append(-0.05)
            confidence += 3

    # Factor 4: Website presence
    has_website = (
        pd.notna(row.get("website"))
        and str(row.get("website")).strip()
        and str(row.get("website")).lower() not in ("nan", "none", "unknown")
    )
    if has_website:
        website_valid = row.get("website_valid")
        if website_valid == True:
            adjustments.append(0.10)
            confidence += 8
        elif website_valid is None:
            adjustments.append(0.05)
            confidence += 3
    else:
        adjustments.append(-0.05)

    # Apply adjustments
    total_adjustment = sum(adjustments)
    estimated = midpoint * (1 + total_adjustment)

    margin = REVENUE_ESTIMATION["confidence_margin"]
    est_low = estimated * (1 - margin)
    est_high = estimated * (1 + margin)

    return {
        "estimated_revenue_low": round(est_low),
        "estimated_revenue_mid": round(estimated),
        "estimated_revenue_high": round(est_high),
        "revenue_confidence": min(confidence, 80),  # Cap at 80%: cross-sector uncertainty
    }


# ── Composite score ──────────────────────────────────────────────────────────

def calculate_total_score(row: pd.Series) -> float:
    """
    Weighted sum of all component scores. Result is 0-100.
    v3: 8 factors (was 7 in v2). Unverified leads get 10% penalty.
    """
    base_score = (
        score_years_in_business(row) * WEIGHT_YEARS_IN_BUSINESS
        + score_review_count(row) * WEIGHT_REVIEW_COUNT
        + score_sector_signal(row) * WEIGHT_SECTOR_SIGNAL
        + score_employee_count(row) * WEIGHT_EMPLOYEE_COUNT
        + score_data_quality(row) * WEIGHT_DATA_QUALITY
        + score_website_presence(row) * WEIGHT_WEBSITE_PRESENCE
        + score_location_bonus(row) * WEIGHT_LOCATION_BONUS
        + score_ownership_signal(row) * WEIGHT_OWNERSHIP_SIGNAL
    )

    if row.get("verification_status") != "Verified":
        base_score *= UNVERIFIED_PENALTY

    return round(base_score, 2)


def main():
    print("=" * 60)
    print(" STEP 6: SCORE & RANK (v3: All-Sector)")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_REQ)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_REQ}\n")

    # Revenue cap check (external data only, FLAG not REMOVE)
    # If an external source populates annual_revenue above the cap, we flag
    # the company but KEEP it in the pipeline. External revenue data for
    # private companies is notoriously inaccurate; hard-deleting on a possibly
    # wrong $6M estimate from D&B or similar would throw away valid leads.
    # The flag shows up in important_notes via 07_export.py so the human
    # reviewer can investigate.
    #
    # Our internal estimate_revenue() does NOT cap its output. It can produce
    # estimates above $5M for companies with high employee counts and long
    # business history. That is intentional: the estimate is informational
    # for the broker, not a filter gate.
    if "annual_revenue" in df.columns:
        over_cap_mask = (
            (df["annual_revenue"].notna()) &
            (df["annual_revenue"] > 0) &
            (df["annual_revenue"] > MAX_ANNUAL_REVENUE)
        )
        over_cap_count = over_cap_mask.sum()
        if over_cap_count > 0:
            print(f"  [WARNING] {over_cap_count} companies have external revenue > ${MAX_ANNUAL_REVENUE/1_000_000:.0f}M cap:")
            for _, row in df[over_cap_mask].iterrows():
                print(f"           {row.get('company_name', 'Unknown'):40s}  ${row['annual_revenue']:,.0f}  (FLAGGED, not removed)")
            # Flag them for review instead of dropping
            df.loc[over_cap_mask, "revenue_cap_flag"] = True
        else:
            df["revenue_cap_flag"] = False
    else:
        df["revenue_cap_flag"] = False

    # Component scores
    df["score_years"] = df.apply(score_years_in_business, axis=1)
    df["score_reviews"] = df.apply(score_review_count, axis=1)
    df["score_sector"] = df.apply(score_sector_signal, axis=1)
    df["score_employees"] = df.apply(score_employee_count, axis=1)
    df["score_data_quality"] = df.apply(score_data_quality, axis=1)
    df["score_website"] = df.apply(score_website_presence, axis=1)
    df["score_location"] = df.apply(score_location_bonus, axis=1)
    df["score_ownership"] = df.apply(score_ownership_signal, axis=1)

    # Composite score
    df["total_score"] = df.apply(calculate_total_score, axis=1)

    # Revenue estimation
    print("\n  Estimating revenue ranges...")
    rev_estimates = df.apply(estimate_revenue, axis=1, result_type="expand")
    df = pd.concat([df, rev_estimates], axis=1)

    # Sort and rank
    df = df.sort_values("total_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # Qualification gate
    df["qualification"] = df["total_score"].apply(
        lambda s: "QUALIFIED" if s >= QUALIFICATION_THRESHOLD else "REVIEW_REQUIRED"
    )
    qualified = len(df[df["qualification"] == "QUALIFIED"])
    review_req = len(df[df["qualification"] == "REVIEW_REQUIRED"])

    # Score distribution
    excellent = len(df[df["total_score"] >= 70])
    good = len(df[df["total_score"].between(50, 70)])
    fair = len(df[df["total_score"].between(30, 50)])
    poor = len(df[df["total_score"] < 30])

    print(f"\n  Score Distribution:")
    print(f"    Excellent (70+): {excellent}")
    print(f"    Good (50-70):    {good}")
    print(f"    Fair (30-50):    {fair}")
    print(f"    Poor (<30):      {poor}")
    print(f"\n  Qualification: {qualified} QUALIFIED, {review_req} REVIEW_REQUIRED")

    # Preview top 10
    print(f"\n  Top 10 candidates:\n")
    print(f"  {'#':<5} {'Company':<40} {'Score':<8} {'Rev Est':<12} {'Status'}")
    print(f"  {'_'*5} {'_'*40} {'_'*8} {'_'*12} {'_'*15}")
    for _, row in df.head(10).iterrows():
        verified = "V" if row.get("verification_status") == "Verified" else "o"
        qual = "Q" if row.get("qualification") == "QUALIFIED" else "R"
        rev_mid = row.get("estimated_revenue_mid", 0)
        rev_str = f"${rev_mid/1000:.0f}K" if rev_mid > 0 else "N/A"
        conf = row.get("revenue_confidence", 0)
        print(f"  {int(row['rank']):<5} {str(row['company_name'])[:40]:<40} {row['total_score']:<8} {rev_str:<12} [{verified}][{qual}] {conf}% conf")

    print(f"\n  [OUTPUT] Scored candidates: {len(df)}")
    df.to_csv(CHECKPOINT_SCORED, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved -> {CHECKPOINT_SCORED}")


if __name__ == "__main__":
    main()
