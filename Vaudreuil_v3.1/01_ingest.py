"""
STEP 1: INGEST & NORMALIZE

Reads raw data from one or more sources and normalizes into a single
DataFrame with a consistent schema. Sources may include:

  1. data/raw_candidates.csv — output from 00_acquire_leads.py (Google Places)
  2. data/raw/icric_export.csv — CCIVS/ICRIC directory export (if available)
  3. data/raw/yellowpages_export.csv — Yellow Pages scrape (if available)

Each source has its own column naming conventions. This script maps
them all to the pipeline's internal schema, tags each row with its
origin source, and writes a unified raw_candidates.csv.

If only the Google Places source exists (most common case), this script
is effectively a pass-through with schema validation.

Input:  data/raw_candidates.csv (and optionally raw/ directory files)
Output: data/raw_candidates.csv (overwritten with normalized schema)
"""

import pandas as pd
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CHECKPOINT_RAW,
    RAW_ICRIC_FILE,
    RAW_YELLOWPAGES_FILE,
    TARGET_CITY,
    TARGET_PROVINCE,
)


# ── Internal Schema ──────────────────────────────────────────────────────────
# Every row in the pipeline after this step has these columns.
# Missing values are allowed (NaN) but the columns must exist.
SCHEMA_COLUMNS = [
    "google_place_id",      # Unique ID from Google (may be empty for non-Google sources)
    "company_name",         # Business name (required, non-empty)
    "address_raw",          # Full address string as received
    "city",                 # City name (parsed or provided)
    "province",             # Province code (QC)
    "postal_code",          # Canadian postal code
    "phone",                # Phone number (raw format)
    "website",              # Website URL
    "lat",                  # Latitude (float)
    "lng",                  # Longitude (float)
    "google_types",         # Google Places type tags (comma-separated)
    "google_rating",        # Rating (float, 1.0-5.0)
    "review_count",         # Number of Google reviews (int)
    "business_status",      # OPERATIONAL, CLOSED_PERMANENTLY, etc.
    "industry_description", # Free text industry description
    "num_employees",        # Employee count estimate (int)
    "data_source",          # Origin tag: google_places, icric, yellowpages
    "acquired_at",          # ISO timestamp when data was acquired
    "pipeline_version",     # v3
]


def ingest_google_places():
    """Load and normalize Google Places data (from 00_acquire_leads.py)."""
    if not os.path.exists(CHECKPOINT_RAW):
        return pd.DataFrame(columns=SCHEMA_COLUMNS)

    df = pd.read_csv(CHECKPOINT_RAW)
    print(f"    Google Places: {len(df)} rows")

    # Rename columns to match schema (most already match from 00_acquire_leads)
    rename_map = {
        "google_types": "google_types",
    }
    df = df.rename(columns=rename_map)

    # Ensure data_source tag
    if "data_source" not in df.columns:
        df["data_source"] = "google_places"

    # Parse city from address if not present
    if "city" not in df.columns:
        df["city"] = df["address_raw"].apply(parse_city_from_address)

    if "province" not in df.columns:
        df["province"] = TARGET_PROVINCE

    # Ensure all schema columns exist
    for col in SCHEMA_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[SCHEMA_COLUMNS].copy()


def ingest_icric():
    """Load and normalize CCIVS/ICRIC directory export."""
    if not os.path.exists(RAW_ICRIC_FILE):
        return pd.DataFrame(columns=SCHEMA_COLUMNS)

    df = pd.read_csv(RAW_ICRIC_FILE)
    print(f"    ICRIC/CCIVS: {len(df)} rows")

    # ICRIC exports use different column names. Common ones:
    rename_map = {
        "Nom de l'entreprise": "company_name",
        "Nom": "company_name",
        "Adresse": "address_raw",
        "Ville": "city",
        "Code postal": "postal_code",
        "Téléphone": "phone",
        "Site web": "website",
        "Secteur": "industry_description",
        "Employés": "num_employees",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    df["data_source"] = "icric"
    df["acquired_at"] = datetime.now().isoformat()
    df["pipeline_version"] = "v3"

    # Ensure all schema columns exist
    for col in SCHEMA_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[SCHEMA_COLUMNS].copy()


def ingest_yellowpages():
    """Load and normalize Yellow Pages scrape."""
    if not os.path.exists(RAW_YELLOWPAGES_FILE):
        return pd.DataFrame(columns=SCHEMA_COLUMNS)

    df = pd.read_csv(RAW_YELLOWPAGES_FILE)
    print(f"    Yellow Pages: {len(df)} rows")

    rename_map = {
        "name": "company_name",
        "business_name": "company_name",
        "address": "address_raw",
        "city": "city",
        "postal_code": "postal_code",
        "phone": "phone",
        "website": "website",
        "category": "industry_description",
    }
    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    df["data_source"] = "yellowpages"
    df["acquired_at"] = datetime.now().isoformat()
    df["pipeline_version"] = "v3"

    for col in SCHEMA_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[SCHEMA_COLUMNS].copy()


def parse_city_from_address(address):
    """Best-effort city extraction from a raw address string."""
    if pd.isna(address):
        return TARGET_CITY

    addr = str(address)
    # Common patterns: "123 Rue X, Vaudreuil-Dorion, QC J7V ..."
    parts = addr.split(",")
    if len(parts) >= 2:
        candidate = parts[-2].strip() if len(parts) >= 3 else parts[-1].strip()
        # Remove postal code and province if attached
        candidate = candidate.replace("QC", "").replace("Québec", "").strip()
        if len(candidate) > 2:
            return candidate

    return TARGET_CITY


def validate_schema(df):
    """Verify the DataFrame has the expected schema."""
    missing = [col for col in SCHEMA_COLUMNS if col not in df.columns]
    if missing:
        print(f"  [ERROR] Missing schema columns: {missing}")
        return False

    # Check for required fields
    empty_names = df["company_name"].isna().sum() + (df["company_name"] == "").sum()
    if empty_names > 0:
        print(f"  [WARNING] {empty_names} rows with empty company_name")

    return True


def main():
    print("=" * 60)
    print(" STEP 1: INGEST & NORMALIZE")
    print("=" * 60)

    frames = []

    # Load each source
    print("\n  Loading sources:")
    gp = ingest_google_places()
    if len(gp) > 0:
        frames.append(gp)

    ic = ingest_icric()
    if len(ic) > 0:
        frames.append(ic)

    yp = ingest_yellowpages()
    if len(yp) > 0:
        frames.append(yp)

    if not frames:
        print("\n  [ERROR] No data sources found. Run 00_acquire_leads.py first.")
        sys.exit(1)

    # Merge all sources
    df = pd.concat(frames, ignore_index=True)
    print(f"\n  Combined: {len(df)} total rows from {len(frames)} source(s)")

    # Source breakdown
    source_counts = df["data_source"].value_counts()
    for source, count in source_counts.items():
        print(f"    {source:20s} {count:>5}")

    # Schema validation
    if not validate_schema(df):
        print("  [ERROR] Schema validation failed. Check column mappings.")
        sys.exit(1)

    # Basic dedup by google_place_id (cross-source)
    before = len(df)
    gp_mask = df["google_place_id"].notna() & (df["google_place_id"] != "")
    if gp_mask.any():
        # Keep first occurrence (Google source takes priority)
        df = df.sort_values("data_source", ascending=True)  # google_places sorts first
        df = df.drop_duplicates(subset=["google_place_id"], keep="first")
    after = len(df)
    if before > after:
        print(f"\n  [DEDUP] Removed {before - after} cross-source duplicates (by place_id)")

    # Remove rows with no company name
    empty_mask = df["company_name"].isna() | (df["company_name"].str.strip() == "")
    if empty_mask.any():
        df = df[~empty_mask].copy()
        print(f"  [CLEAN] Removed {empty_mask.sum()} rows with empty company_name")

    # Save
    os.makedirs(os.path.dirname(CHECKPOINT_RAW), exist_ok=True)
    df.to_csv(CHECKPOINT_RAW, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] {len(df)} normalized rows -> {CHECKPOINT_RAW}")
    print(f"  [OUTPUT] Schema: {len(SCHEMA_COLUMNS)} columns")


if __name__ == "__main__":
    main()
