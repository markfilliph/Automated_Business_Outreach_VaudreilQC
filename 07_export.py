"""
STEP 7: EXPORT

Takes the scored and ranked candidates, selects the top 50,
and exports a clean broker-friendly CSV for manual review.

The output includes only the columns that matter for the acquisition review,
plus an empty "notes" column for you to fill in during manual verification.

Input:  data/scored_candidates.csv
Output: data/top_50_for_review.csv
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CHECKPOINT_SCORED, OUTPUT_FINAL, TARGET_FINAL_LEADS


# Columns included in the final export — ordered for readability.
# Broker sees: identity → location → contact → business details → scores.
EXPORT_COLUMNS = [
    # Identity & ranking
    "rank",
    "company_name",
    "total_score",
    # Location
    "address_raw",
    "city",
    "postal_code",
    # Contact
    "phone",
    "email",
    "website",
    # Business details
    "industry_description",
    "num_employees",
    "annual_revenue",
    # REQ verification
    "neq",
    "req_registration_date",
    "req_status",
    "verification_status",
    # Google Places
    "business_status",
    "review_count",
    "google_rating",
    "google_url",
    # Score breakdown (for transparency)
    "score_years",
    "score_reviews",
    "score_sector",
    "score_employees",
    # Source tracking
    "source",
    # Manual review
    "notes",
]


def main():
    print("=" * 60)
    print(" STEP 7: EXPORT TOP 50")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_SCORED)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_SCORED}\n")

    # ── Select top N ────────────────────────────────────────────────────
    df_top = df.head(TARGET_FINAL_LEADS).copy()

    # ── Add empty notes column for manual review ───────────────────────
    df_top["notes"] = ""

    # ── Select and order export columns ─────────────────────────────────
    # Gracefully skip any columns that don't exist in this run
    cols = [c for c in EXPORT_COLUMNS if c in df_top.columns]
    df_export = df_top[cols]

    # ── Summary ─────────────────────────────────────────────────────────
    verified = df_export["verification_status"].value_counts().to_dict() if "verification_status" in df_export.columns else {}
    print(f"  [Export] {len(df_export)} leads")
    print(f"  [Export] Verification: {verified}")

    if "total_score" in df_export.columns:
        print(f"  [Export] Score range: {df_export['total_score'].min()} – {df_export['total_score'].max()}")

    # ── Save ────────────────────────────────────────────────────────────
    df_export.to_csv(OUTPUT_FINAL, index=False, encoding="utf-8")

    print(f"\n  [OUTPUT] Saved → {OUTPUT_FINAL}")
    print(f"\n{'=' * 60}")
    print(" PIPELINE COMPLETE")
    print(f"{'=' * 60}")
    print(f"\n  Next step: Open {OUTPUT_FINAL} and manually review the top 50.")
    print(f"  Click the google_url links, check websites, fill in the notes column.")
    print(f"  Automation cannot detect a 'bad' business — this is your job.\n")


if __name__ == "__main__":
    main()
