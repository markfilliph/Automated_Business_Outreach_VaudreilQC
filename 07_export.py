"""
STEP 7: EXPORT CSV (v3: Hamilton Standard Format)

Reads scored_candidates.csv and exports a clean CSV matching the
Hamilton MVP's Burlington STANDARDIZED format (17 fields).

This is the deliverable file. Every row should be a human-reviewable
acquisition lead with consistent formatting.

Hamilton Standard Fields (17):
  1.  business_name
  2.  address
  3.  city
  4.  postal_code
  5.  website
  6.  phone
  7.  owner_name
  8.  owner_confidence
  9.  owner_source
  10. industry
  11. category_standardized
  12. employee_range_estimate
  13. revenue_range_estimate
  14. sde_range_estimate
  15. age_range_estimate
  16. acquisition_fit_score
  17. important_notes

Input:  data/scored_candidates.csv
Output: data/top_75_for_review.csv
"""

import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CHECKPOINT_SCORED,
    OUTPUT_FINAL,
    TARGET_FINAL_LEADS,
    QUALIFICATION_THRESHOLD,
    INDUSTRY_MARGINS,
    HIGH_VALUE_SECTOR_KEYWORDS,
)


# ── Hamilton Standard Field Order ────────────────────────────────────────────
STANDARD_FIELDS = [
    "business_name",
    "address",
    "city",
    "postal_code",
    "website",
    "phone",
    "owner_name",
    "owner_confidence",
    "owner_source",
    "industry",
    "category_standardized",
    "employee_range_estimate",
    "revenue_range_estimate",
    "sde_range_estimate",
    "age_range_estimate",
    "acquisition_fit_score",
    "important_notes",
]


# ── Sector category mapping ─────────────────────────────────────────────────
# Maps keyword matches to standardized category names
CATEGORY_RULES = [
    # Check order matters: more specific patterns first
    (["usinage", "machinage", "cnc", "machining"], "Precision Manufacturing"),
    (["plastics", "plastique", "moulage", "injection"], "Plastics Manufacturing"),
    (["metal", "metallurg", "welding", "soudure", "steel", "acier"], "Metal Fabrication"),
    (["wood", "bois", "menuiserie", "ebenisterie", "charpente", "carpentry"], "Wood / Millwork"),
    (["printing", "imprimerie", "print"], "Printing & Packaging"),
    (["packaging", "emballage"], "Printing & Packaging"),
    (["food processing", "transformation alimentaire", "microbrasserie", "brewery"], "Food Processing"),
    (["manufactur", "fabricat", "usine", "production", "assemblage"], "Light Manufacturing"),
    (["electrical", "electrique", "electricien"], "Electrical Contractor"),
    (["plumbing", "plomberie", "plombier"], "Plumbing Contractor"),
    (["hvac", "chauffage", "climatisation", "ventilation", "refrigeration", "refrigeration"], "HVAC / Refrigeration"),
    (["roofing", "toiture", "couvreur"], "Roofing Contractor"),
    (["excavation", "excavat", "concrete", "beton", "paving", "pavage", "asphalte"], "Heavy Construction"),
    (["construction", "renovation", "renovation", "general contractor", "entrepreneur"], "General Contractor"),
    (["insulation", "isolation", "masonry", "maconnerie", "demolition", "demolition"], "Specialty Trades"),
    (["transport", "trucking", "camionnage", "freight", "fret", "moving", "demenagement"], "Transportation / Logistics"),
    (["warehouse", "entreposage", "entrepot", "logistics", "logistique"], "Warehousing / Distribution"),
    (["courier", "messagerie", "livraison"], "Courier / Delivery"),
    (["wholesale", "gros", "distribution", "distributeur", "supply", "fourniture"], "Wholesale / Distribution"),
    (["engineering", "ingenierie", "ingenieur"], "Engineering Services"),
    (["consulting", "conseil"], "Consulting / Professional Services"),
    (["it service", "informatique", "software", "logiciel"], "IT / Technology Services"),
    (["accounting", "comptab"], "Accounting / Financial Services"),
    (["laboratory", "laboratoire", "testing"], "Testing / Laboratory"),
    (["cleaning", "nettoyage", "janitorial"], "Cleaning Services"),
    (["landscaping", "paysagiste", "amenagement paysager"], "Landscaping"),
    (["security", "securite", "gardiennage"], "Security Services"),
    (["equipment", "equipement", "maintenance", "entretien"], "Equipment / Maintenance"),
    (["signage", "enseigne", "affichage"], "Signage / Display"),
    (["pest control", "extermination"], "Pest Control"),
    (["auto repair", "mecanique", "garage"], "Automotive Services"),
    (["towing", "remorquage"], "Towing / Recovery"),
    (["waste", "dechets"], "Waste Management"),
    (["surveying", "arpentage"], "Surveying"),
    (["architecture", "architecte"], "Architecture"),
]


def classify_category(text: str) -> str:
    """Classify a business into a standardized category based on keywords."""
    text_lower = text.lower()
    for keywords, category in CATEGORY_RULES:
        if any(kw in text_lower for kw in keywords):
            return category
    return "General Business"


def get_industry_label(text: str) -> str:
    """Extract a clean industry label from description text."""
    text_lower = text.lower()

    # Map to Hamilton-style industry labels
    industry_map = [
        (["manufactur", "fabricat", "usine", "production"], "manufacturing"),
        (["construction", "renovation", "contractor", "entrepreneur"], "construction"),
        (["transport", "trucking", "camionnage", "logistics"], "transportation"),
        (["wholesale", "gros", "distribution"], "wholesale"),
        (["cleaning", "nettoyage"], "cleaning_services"),
        (["landscaping", "paysagiste"], "landscaping"),
        (["it service", "informatique", "software"], "it_services"),
        (["consulting", "conseil", "engineering", "ingenierie"], "professional_services"),
        (["equipment", "maintenance"], "equipment_rental"),
        (["printing", "imprimerie"], "printing"),
        (["food", "alimentaire", "brasserie"], "food_processing"),
        (["plumbing", "electrical", "hvac", "roofing", "welding"], "trades"),
    ]

    for keywords, label in industry_map:
        if any(kw in text_lower for kw in keywords):
            return label
    return "general"


def format_revenue_range(low: float, high: float) -> str:
    """Format revenue range like Hamilton: '$1.8M-$3.1M' or '$500K-$900K'."""
    def fmt(val):
        if val >= 1_000_000:
            return f"${val/1_000_000:.1f}M"
        elif val >= 1000:
            return f"${val/1000:.0f}K"
        else:
            return f"${val:.0f}"
    return f"{fmt(low)}-{fmt(high)}"


def format_sde_range(revenue_low: float, revenue_high: float,
                     industry: str) -> str:
    """Calculate and format SDE range based on industry margins."""
    margin = INDUSTRY_MARGINS.get(industry, INDUSTRY_MARGINS["default"])
    sde_low = revenue_low * margin
    sde_high = revenue_high * margin

    def fmt(val):
        if val >= 1_000_000:
            return f"${val/1_000_000:.1f}M"
        elif val >= 1000:
            return f"${val/1000:.0f}K"
        else:
            return f"${val:.0f}"
    return f"{fmt(sde_low)}-{fmt(sde_high)}"


def format_age_range(reg_date) -> str:
    """Format business age from REQ registration date."""
    if pd.isna(reg_date) or reg_date is None:
        return "Unknown"

    try:
        reg = pd.to_datetime(reg_date)
        years = (datetime.now() - reg).days / 365.25

        if years >= 30:
            return "30+ years"
        elif years >= 20:
            return "20-30 years"
        elif years >= 15:
            return "15-20 years"
        elif years >= 10:
            return "10-15 years"
        elif years >= 5:
            return "5-10 years"
        elif years >= 2:
            return "2-5 years"
        else:
            return "<2 years"
    except Exception:
        return "Unknown"


def format_employee_range(emp_count) -> str:
    """Format employee count into a range like Hamilton: '12-35'."""
    if pd.isna(emp_count) or emp_count is None:
        return "Unknown"

    try:
        emp = int(float(emp_count))
        if emp <= 5:
            return "1-5"
        elif emp <= 10:
            return "5-10"
        elif emp <= 20:
            return "10-20"
        elif emp <= 35:
            return "12-35"
        elif emp <= 50:
            return "25-50"
        elif emp <= 100:
            return "50-100"
        elif emp <= 200:
            return "100-200"
        else:
            return f"{emp}+"
    except Exception:
        return "Unknown"


def compose_notes(row: pd.Series, category: str) -> str:
    """Compose the important_notes field like Hamilton format."""
    notes_parts = []

    # Category tag
    notes_parts.append(f"Category: {category}")

    # Revenue signal
    rev_mid = row.get("estimated_revenue_mid", 0)
    if pd.notna(rev_mid) and float(rev_mid) > 0:
        rev_conf = row.get("revenue_confidence", 0)
        if float(rev_conf) >= 60:
            notes_parts.append("Revenue estimate has reasonable confidence")

    # Qualification status
    score = row.get("total_score", 0)
    if float(score) >= 70:
        notes_parts.append("High acquisition fit; priority follow-up")
    elif float(score) >= 55:
        notes_parts.append("Good acquisition fit; worth investigating")
    elif float(score) >= QUALIFICATION_THRESHOLD:
        notes_parts.append("Moderate fit; review recommended")
    else:
        notes_parts.append("Below threshold; manual review needed")

    # Ownership signal
    ownership_score = row.get("score_ownership", 50)
    if pd.notna(ownership_score) and float(ownership_score) >= 75:
        notes_parts.append("Strong independent ownership signals")

    # Verification status
    if row.get("verification_status") == "Verified":
        notes_parts.append("Google verified")

    # Revenue cap warning
    if row.get("revenue_cap_flag") == True:
        ext_rev = row.get("annual_revenue", 0)
        if pd.notna(ext_rev) and float(ext_rev) > 0:
            notes_parts.append(f"REVIEW: external revenue ${float(ext_rev):,.0f} exceeds cap")

    return " | ".join(notes_parts)


def transform_row(row: pd.Series) -> dict:
    """Transform a scored pipeline row into Hamilton standard format."""

    # Build text for classification
    desc_text = str(row.get("industry_description", "")) + " " + str(row.get("company_name", ""))
    industry_label = get_industry_label(desc_text)
    category = classify_category(desc_text)

    # Revenue range
    rev_low = float(row.get("estimated_revenue_low", 0)) if pd.notna(row.get("estimated_revenue_low")) else 0
    rev_high = float(row.get("estimated_revenue_high", 0)) if pd.notna(row.get("estimated_revenue_high")) else 0
    revenue_range = format_revenue_range(rev_low, rev_high) if rev_low > 0 else "Unknown"
    sde_range = format_sde_range(rev_low, rev_high, industry_label) if rev_low > 0 else "Unknown"

    # Owner info from REQ
    officer_name = row.get("req_officer_name", "")
    if pd.isna(officer_name) or str(officer_name).strip() in ("", "nan", "None", "N/A"):
        owner_name = "Not found"
        owner_confidence = "none"
        owner_source = "Owner not found; manual research required"
    else:
        owner_name = str(officer_name).strip()
        owner_confidence = "medium"
        owner_source = "REQ (Registraire des entreprises du Quebec)"

    # Address: use address_raw or street_address
    address = str(row.get("address_raw", "")) if pd.notna(row.get("address_raw")) else ""
    # Strip city/province if embedded in address
    city = str(row.get("city", "Vaudreuil-Dorion")) if pd.notna(row.get("city")) else "Vaudreuil-Dorion"

    return {
        "business_name": str(row.get("company_name", "")),
        "address": address,
        "city": city,
        "postal_code": str(row.get("postal_code", "")),
        "website": str(row.get("website", "")) if pd.notna(row.get("website")) else "",
        "phone": str(row.get("phone", "")) if pd.notna(row.get("phone")) else "",
        "owner_name": owner_name,
        "owner_confidence": owner_confidence,
        "owner_source": owner_source,
        "industry": industry_label,
        "category_standardized": category,
        "employee_range_estimate": format_employee_range(row.get("num_employees")),
        "revenue_range_estimate": revenue_range,
        "sde_range_estimate": sde_range,
        "age_range_estimate": format_age_range(row.get("req_registration_date")),
        "acquisition_fit_score": int(round(float(row.get("total_score", 0)))),
        "important_notes": compose_notes(row, category),
    }


def main():
    print("=" * 60)
    print(" STEP 7: EXPORT CSV (Hamilton Standard Format)")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_SCORED)
    print(f"  [INPUT] {len(df)} scored candidates from {CHECKPOINT_SCORED}")

    # Take top N by score (already sorted in 06_score.py)
    top = df.head(TARGET_FINAL_LEADS).copy()
    print(f"  [SELECT] Top {len(top)} candidates (target: {TARGET_FINAL_LEADS})")

    # Transform each row to Hamilton standard format
    print(f"\n  Transforming to Hamilton standard 17-field format...")
    leads = []
    for _, row in top.iterrows():
        leads.append(transform_row(row))

    # Create output DataFrame with exact field order
    output_df = pd.DataFrame(leads, columns=STANDARD_FIELDS)

    # Summary stats
    categories = output_df["category_standardized"].value_counts()
    print(f"\n  Category breakdown:")
    for cat, count in categories.head(10).items():
        print(f"    {cat:35s} {count:>3}")
    if len(categories) > 10:
        print(f"    ... and {len(categories) - 10} more categories")

    owner_found = len(output_df[output_df["owner_name"] != "Not found"])
    print(f"\n  Owner/officer found: {owner_found}/{len(output_df)} ({owner_found/len(output_df)*100:.0f}%)")

    scores = output_df["acquisition_fit_score"]
    print(f"  Score range: {scores.min()} to {scores.max()} (mean: {scores.mean():.0f})")

    # Save
    output_df.to_csv(OUTPUT_FINAL, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] {len(output_df)} leads saved -> {OUTPUT_FINAL}")
    print(f"  [OUTPUT] Fields: {len(STANDARD_FIELDS)} (Hamilton standard)")

    # Verify field order
    print(f"\n  Field order verification:")
    for i, field in enumerate(STANDARD_FIELDS, 1):
        print(f"    {i:>2}. {field}")


if __name__ == "__main__":
    main()
