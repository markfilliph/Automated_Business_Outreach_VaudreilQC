"""
STEP 8: BROKER-FRIENDLY EXCEL EXPORT

Generates a polished Excel file for broker presentation.
Includes formatting, conditional coloring, and summary sheet.

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


def calculate_years(reg_date):
    """Calculate years in business from registration date."""
    if pd.isna(reg_date) or reg_date is None:
        return "Unknown"
    try:
        reg = pd.to_datetime(reg_date)
        years = (datetime.now() - reg).days / 365.25
        return f"{int(years)} years"
    except Exception:
        return "Unknown"


def main():
    print("=" * 60)
    print(" STEP 8: BROKER-FRIENDLY EXCEL EXPORT")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_SCORED)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_SCORED}\n")

    # ── Prepare broker-friendly columns ──────────────────────────────
    # Clean NaN/None values for broker presentation
    def clean_value(val, default="—"):
        if pd.isna(val) or val is None or str(val).lower() in ("nan", "none", ""):
            return default
        return val

    export_df = pd.DataFrame()
    export_df["Rank"] = df["rank"].astype(int)
    export_df["Company Name"] = df["company_name"]
    export_df["Score"] = df["total_score"]
    export_df["Verified"] = df["verification_status"].apply(lambda x: "✓" if x == "Verified" else "")
    export_df["Years in Business"] = df["req_registration_date"].apply(calculate_years)
    export_df["NEQ"] = df["neq"].apply(clean_value)
    export_df["Phone"] = df["phone"].apply(clean_value)
    export_df["Website"] = df["website"].apply(clean_value)
    export_df["Address"] = df["address_raw"].apply(clean_value)
    export_df["City"] = df["city"].apply(clean_value)
    export_df["Postal Code"] = df["postal_code"].apply(clean_value)
    export_df["Google Rating"] = df["google_rating"].fillna(0)
    export_df["Reviews"] = df["review_count"].fillna(0).astype(int)
    export_df["Status"] = df["business_status"].apply(lambda x: clean_value(x, "Unknown"))
    export_df["Notes"] = ""

    # ── Create Excel workbook ────────────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = "Top Leads"

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    verified_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
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

            # Verified row highlighting
            if r_idx > 1 and c_idx == 4 and value == "✓":
                for col in range(1, len(row) + 1):
                    ws.cell(row=r_idx, column=col).fill = verified_fill

    # Column widths
    column_widths = {
        "A": 6,   # Rank
        "B": 40,  # Company Name
        "C": 8,   # Score
        "D": 10,  # Verified
        "E": 18,  # Years in Business
        "F": 14,  # NEQ
        "G": 16,  # Phone
        "H": 35,  # Website
        "I": 50,  # Address
        "J": 20,  # City
        "K": 12,  # Postal Code
        "L": 12,  # Google Rating
        "M": 10,  # Reviews
        "N": 14,  # Status
        "O": 30,  # Notes
    }

    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width

    # Freeze header row
    ws.freeze_panes = "A2"

    # ── Add Summary Sheet ────────────────────────────────────────────
    ws_summary = wb.create_sheet("Summary")

    summary_data = [
        ["Vaudreuil Manufacturing Acquisition Leads"],
        [""],
        ["Generated:", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Total Leads:", len(df)],
        ["Verified:", len(df[df["verification_status"] == "Verified"])],
        ["Unverified:", len(df[df["verification_status"] != "Verified"])],
        [""],
        ["Score Range:", f"{df['total_score'].min():.2f} - {df['total_score'].max():.2f}"],
        [""],
        ["Top 5 by Score:"],
    ]

    for idx, row in df.head(5).iterrows():
        verified = "✓" if row["verification_status"] == "Verified" else ""
        summary_data.append([f"  {int(row['rank'])}. {row['company_name']}", f"{row['total_score']:.2f}", verified])

    for r_idx, row in enumerate(summary_data, 1):
        for c_idx, value in enumerate(row, 1):
            cell = ws_summary.cell(row=r_idx, column=c_idx, value=value)
            if r_idx == 1:
                cell.font = Font(bold=True, size=14)

    ws_summary.column_dimensions["A"].width = 50
    ws_summary.column_dimensions["B"].width = 15

    # ── Save ─────────────────────────────────────────────────────────
    output_path = "data/Vaudreuil_Manufacturing_Leads.xlsx"
    wb.save(output_path)

    print(f"  [OUTPUT] Broker-friendly Excel: {output_path}")
    print(f"  [OUTPUT] Sheets: 'Top Leads' (data) + 'Summary' (overview)")
    print(f"\n  Verified leads highlighted in green.")


if __name__ == "__main__":
    main()
