"""
STEP 8: BROKER-FRIENDLY EXCEL EXPORT

Generates a polished Excel file for broker presentation.
Matches the standard acquisition leads format with SDE calculations.

Input:  data/scored_candidates.csv
Output: data/Vaudreuil_Manufacturing_Leads.xlsx
"""

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import CHECKPOINT_SCORED


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
        return "Unknown"

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
        return f"${sde/1_000_000:.1f}M ({margin_pct}% margin)"
    elif sde >= 1_000:
        return f"${sde/1_000:.0f}K ({margin_pct}% margin)"
    else:
        return f"${sde:.0f} ({margin_pct}% margin)"


def calculate_confidence_score(row):
    """Calculate confidence score based on data completeness and verification."""
    score = 0

    if row.get("verification_status") == "Verified":
        score += 30
    if pd.notna(row.get("phone")) and str(row.get("phone")).strip():
        score += 15
    if pd.notna(row.get("website")) and str(row.get("website")).strip():
        score += 15
    if pd.notna(row.get("annual_revenue")) and row.get("annual_revenue", 0) > 0:
        score += 15
    if pd.notna(row.get("num_employees")) and row.get("num_employees", 0) > 0:
        score += 10
    if pd.notna(row.get("google_rating")) and row.get("google_rating", 0) > 0:
        score += 10
    if pd.notna(row.get("neq")):
        score += 5

    return f"{score}%"


def determine_status(row):
    """Determine lead status: QUALIFIED or REVIEW_REQUIRED."""
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
    print(" STEP 8: BROKER-FRIENDLY EXCEL EXPORT")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_SCORED)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_SCORED}\n")

    # ── Build export DataFrame in standard acquisition format ──────────
    export_rows = []
    for _, row in df.iterrows():
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
            "Estimated SDE (CAD)": calculate_sde(row.get("annual_revenue"), row.get("industry_description")),
            "Estimated Revenue (CAD)": format_revenue(row.get("annual_revenue")),
            "Confidence Score": calculate_confidence_score(row),
            "Status": determine_status(row),
            "Data Sources": row.get("source", "GooglePlaces"),
        })

    export_df = pd.DataFrame(export_rows)

    # ── Create Excel workbook ────────────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = "Acquisition Leads"

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    qualified_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    review_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # Write data
    for r_idx, row in enumerate(dataframe_to_rows(export_df, index=False, header=True), 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)

            # Header styling
            if r_idx == 1:
                cell.font = header_font
                cell.fill = header_fill

        # Row highlighting based on status (column 13 is Status)
        if r_idx > 1:
            status = row[12] if len(row) > 12 else ""
            fill = qualified_fill if status == "QUALIFIED" else review_fill
            for col in range(1, len(row) + 1):
                ws.cell(row=r_idx, column=col).fill = fill

    # Column widths
    column_widths = {
        "A": 40,  # Business Name
        "B": 50,  # Address
        "C": 18,  # City
        "D": 10,  # Province
        "E": 12,  # Postal Code
        "F": 16,  # Phone Number
        "G": 35,  # Website
        "H": 15,  # Industry
        "I": 22,  # Estimated Employees (Range)
        "J": 25,  # Estimated SDE (CAD)
        "K": 22,  # Estimated Revenue (CAD)
        "L": 16,  # Confidence Score
        "M": 18,  # Status
        "N": 20,  # Data Sources
    }

    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    # Freeze header row
    ws.freeze_panes = "A2"

    # ── Add Summary Sheet ────────────────────────────────────────────
    ws_summary = wb.create_sheet("Summary")

    qualified_count = len(export_df[export_df["Status"] == "QUALIFIED"])
    review_count = len(export_df[export_df["Status"] == "REVIEW_REQUIRED"])

    summary_data = [
        ["Vaudreuil Manufacturing Acquisition Leads"],
        [""],
        ["Generated:", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Total Leads:", len(df)],
        ["QUALIFIED:", qualified_count],
        ["REVIEW_REQUIRED:", review_count],
        [""],
        ["Top 5 Leads:"],
    ]

    for idx, row in export_df.head(5).iterrows():
        summary_data.append([
            f"  {idx+1}. {row['Business Name']}",
            row['Estimated Revenue (CAD)'],
            row['Status']
        ])

    for r_idx, row in enumerate(summary_data, 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws_summary.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                cell.font = Font(bold=True, size=14)

    ws_summary.column_dimensions["A"].width = 50
    ws_summary.column_dimensions["B"].width = 20
    ws_summary.column_dimensions["C"].width = 20

    # ── Save ─────────────────────────────────────────────────────────
    output_path = "data/Vaudreuil_Manufacturing_Leads.xlsx"
    wb.save(output_path)

    print(f"  [OUTPUT] Broker-friendly Excel: {output_path}")
    print(f"  [OUTPUT] Sheets: 'Acquisition Leads' (data) + 'Summary' (overview)")
    print(f"\n  QUALIFIED leads highlighted in green.")
    print(f"  REVIEW_REQUIRED leads highlighted in yellow.")


if __name__ == "__main__":
    main()
