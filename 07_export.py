"""
STEP 7: EXPORT

Takes the scored and ranked candidates, selects the top 50,
and exports a broker-friendly CSV matching the standard acquisition format.

Output columns:
- Business Name, Address, City, Province, Postal Code, Phone Number, Website
- Industry, Estimated Employees (Range), Estimated SDE (CAD), Estimated Revenue (CAD)
- Confidence Score, Status, Data Sources

Input:  data/scored_candidates.csv
Output: data/top_50_for_review.csv
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CHECKPOINT_SCORED, OUTPUT_FINAL, TARGET_FINAL_LEADS


# SDE margins by industry type (manufacturing typically 15-20%)
INDUSTRY_MARGINS = {
    "manufacturing": 0.15,
    "printing": 0.18,
    "wholesale": 0.17,
    "professional_services": 0.30,
    "equipment_rental": 0.25,
    "default": 0.18,
}


def get_employee_range(num_employees):
    """Convert employee count to a range string."""
    if pd.isna(num_employees) or num_employees is None:
        return "Unknown"
    emp = int(num_employees)
    if emp <= 5:
        return "1-5"
    elif emp <= 10:
        return "5-10"
    elif emp <= 25:
        return "10-25"
    elif emp <= 50:
        return "25-50"
    elif emp <= 100:
        return "50-100"
    elif emp <= 250:
        return "100-250"
    elif emp <= 500:
        return "250-500"
    else:
        return "500+"


def format_revenue(revenue):
    """Format revenue as $X.XM or $XXK."""
    if pd.isna(revenue) or revenue is None or revenue == 0:
        return "Unknown"
    rev = float(revenue)
    if rev >= 1_000_000:
        return f"${rev/1_000_000:.1f}M"
    elif rev >= 1_000:
        return f"${rev/1_000:.0f}K"
    else:
        return f"${rev:.0f}"


def calculate_sde(revenue, industry_desc):
    """Calculate SDE (Seller's Discretionary Earnings) based on industry margin."""
    if pd.isna(revenue) or revenue is None or revenue == 0:
        return "Unknown", "Unknown"

    # Determine margin based on industry
    margin = INDUSTRY_MARGINS["default"]
    if pd.notna(industry_desc):
        desc_lower = str(industry_desc).lower()
        for industry, m in INDUSTRY_MARGINS.items():
            if industry in desc_lower:
                margin = m
                break

    sde = float(revenue) * margin
    margin_pct = int(margin * 100)

    if sde >= 1_000_000:
        return f"${sde/1_000_000:.1f}M ({margin_pct}% margin)", f"${sde/1_000_000:.1f}M"
    elif sde >= 1_000:
        return f"${sde/1_000:.0f}K ({margin_pct}% margin)", f"${sde/1_000:.0f}K"
    else:
        return f"${sde:.0f} ({margin_pct}% margin)", f"${sde:.0f}"


def calculate_confidence_score(row):
    """Calculate confidence score based on data completeness and verification."""
    score = 0
    max_score = 100

    # Verification status (30 points)
    if row.get("verification_status") == "Verified":
        score += 30

    # Has phone (15 points)
    if pd.notna(row.get("phone")) and str(row.get("phone")).strip():
        score += 15

    # Has website (15 points)
    if pd.notna(row.get("website")) and str(row.get("website")).strip():
        score += 15

    # Has revenue data (15 points)
    if pd.notna(row.get("annual_revenue")) and row.get("annual_revenue", 0) > 0:
        score += 15

    # Has employee data (10 points)
    if pd.notna(row.get("num_employees")) and row.get("num_employees", 0) > 0:
        score += 10

    # Has Google rating (10 points)
    if pd.notna(row.get("google_rating")) and row.get("google_rating", 0) > 0:
        score += 10

    # Has NEQ (5 points)
    if pd.notna(row.get("neq")):
        score += 5

    return f"{score}%"


def determine_status(row):
    """Determine lead status: QUALIFIED or REVIEW_REQUIRED."""
    # Qualified if verified AND has key data points
    has_phone = pd.notna(row.get("phone")) and str(row.get("phone")).strip()
    has_website = pd.notna(row.get("website")) and str(row.get("website")).strip()
    is_verified = row.get("verification_status") == "Verified"
    has_revenue = pd.notna(row.get("annual_revenue")) and row.get("annual_revenue", 0) > 0

    if is_verified and has_phone and (has_website or has_revenue):
        return "QUALIFIED"
    else:
        return "REVIEW_REQUIRED"


def main():
    print("=" * 60)
    print(" STEP 7: EXPORT TOP 50")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_SCORED)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_SCORED}\n")

    # ── Select top N ────────────────────────────────────────────────────
    df_top = df.head(TARGET_FINAL_LEADS).copy()

    # ── Build export DataFrame in standard acquisition format ──────────
    export_rows = []
    for _, row in df_top.iterrows():
        sde_display, _ = calculate_sde(row.get("annual_revenue"), row.get("industry_description"))

        export_rows.append({
            "Business Name": row.get("company_name", ""),
            "Address": row.get("address_raw", ""),
            "City": row.get("city", ""),
            "Province": row.get("province", "QC"),
            "Postal Code": row.get("postal_code", ""),
            "Phone Number": row.get("phone", ""),
            "Website": row.get("website", "") if pd.notna(row.get("website")) else "Unknown",
            "Industry": "manufacturing",
            "Estimated Employees (Range)": get_employee_range(row.get("num_employees")),
            "Estimated SDE (CAD)": sde_display,
            "Estimated Revenue (CAD)": format_revenue(row.get("annual_revenue")),
            "Confidence Score": calculate_confidence_score(row),
            "Status": determine_status(row),
            "Data Sources": row.get("source", "GooglePlaces"),
        })

    df_export = pd.DataFrame(export_rows)

    # ── Summary ─────────────────────────────────────────────────────────
    qualified = len(df_export[df_export["Status"] == "QUALIFIED"])
    review_req = len(df_export[df_export["Status"] == "REVIEW_REQUIRED"])
    print(f"  [Export] {len(df_export)} leads")
    print(f"  [Export] QUALIFIED: {qualified}, REVIEW_REQUIRED: {review_req}")

    # ── Save ────────────────────────────────────────────────────────────
    df_export.to_csv(OUTPUT_FINAL, index=False, encoding="utf-8")

    print(f"\n  [OUTPUT] Saved → {OUTPUT_FINAL}")
    print(f"\n{'=' * 60}")
    print(" PIPELINE COMPLETE")
    print(f"{'=' * 60}")
    print(f"\n  Review REVIEW_REQUIRED leads manually.")
    print(f"  QUALIFIED leads have verified data and are ready for outreach.\n")


if __name__ == "__main__":
    main()
