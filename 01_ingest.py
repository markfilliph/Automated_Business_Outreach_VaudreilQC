"""
STEP 1: INGEST

Loads raw data exports from iCRIQ and YellowPages into a single Pandas DataFrame
with a standardized column schema. Handles French and English column headers.

Input:  data/raw/icric_export.csv  +  data/raw/yellowpages_export.csv
Output: data/raw_candidates.csv
"""

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import RAW_ICRIC_FILE, RAW_YELLOWPAGES_FILE, CHECKPOINT_RAW
from utils.address import normalize_address


# ─── Standard column schema ─────────────────────────────────────────────────
# All sources get mapped to these columns. Missing data = NaN.
STANDARD_COLUMNS = [
    "source",
    "company_name",
    "address_raw",
    "address_normalized",
    "city",
    "province",
    "postal_code",
    "phone",
    "email",
    "website",
    "sic_code",
    "industry_description",
    "num_employees",
    "annual_revenue",
]


def _get_col(df: pd.DataFrame, candidates: list, default="") -> pd.Series:
    """Try a list of possible column names. Return the first one found, or a default Series."""
    for name in candidates:
        if name in df.columns:
            return df[name]
    return pd.Series([default] * len(df), index=df.index)


def load_icric(filepath: str) -> pd.DataFrame:
    """Load an iCRIQ export CSV and map to the standard schema."""
    if not os.path.exists(filepath):
        print(f"  [WARNING] iCRIQ file not found: {filepath}")
        print(f"  [WARNING] Place your iCRIQ export at: {filepath}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = pd.read_csv(filepath, encoding="utf-8-sig")
    print(f"  [iCRIQ] Loaded {len(df)} rows")

    # ── Map columns ─────────────────────────────────────────────────────
    # iCRIQ exports can vary — these cover the common French and English headers.
    mapped = pd.DataFrame(index=df.index)
    mapped["source"] = "iCRIQ"
    mapped["company_name"] = _get_col(df, ["Nom de l'établissement", "Company Name", "Nom"])
    mapped["address_raw"] = _get_col(df, ["Adresse", "Address"])
    mapped["city"] = _get_col(df, ["Ville", "City"])
    mapped["province"] = _get_col(df, ["Province"], default="QC")
    mapped["postal_code"] = _get_col(df, ["Code postal", "Postal Code"]).astype(str).str.strip().str.upper()
    mapped["phone"] = _get_col(df, ["Téléphone", "Phone", "Tél."]).astype(str).str.strip()
    mapped["email"] = _get_col(df, ["Courriel", "Email"])
    mapped["website"] = _get_col(df, ["Site web", "Website"])
    mapped["sic_code"] = _get_col(df, ["Code SIC", "SIC Code", "Code NAICS"])
    mapped["industry_description"] = _get_col(df, ["Description de l'industrie", "Industry", "Secteur"])
    mapped["num_employees"] = pd.to_numeric(_get_col(df, ["Nb employés", "Employees", "Nombre d'employés"]), errors="coerce")
    mapped["annual_revenue"] = pd.to_numeric(_get_col(df, ["Chiffre d'affaires", "Revenue", "CA annuel"]), errors="coerce")

    mapped["address_normalized"] = mapped["address_raw"].apply(normalize_address)
    return mapped


def load_yellowpages(filepath: str) -> pd.DataFrame:
    """Load a YellowPages export CSV and map to the standard schema."""
    if not os.path.exists(filepath):
        print(f"  [WARNING] YellowPages file not found: {filepath}")
        print(f"  [WARNING] Place your YellowPages export at: {filepath}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = pd.read_csv(filepath, encoding="utf-8-sig")
    print(f"  [YellowPages] Loaded {len(df)} rows")

    mapped = pd.DataFrame(index=df.index)
    mapped["source"] = "YellowPages"
    mapped["company_name"] = _get_col(df, ["Business Name", "Nom", "Name"])
    mapped["address_raw"] = _get_col(df, ["Address", "Adresse"])
    mapped["city"] = _get_col(df, ["City", "Ville"])
    mapped["province"] = _get_col(df, ["Province"], default="QC")
    mapped["postal_code"] = _get_col(df, ["Postal Code", "Code postal"]).astype(str).str.strip().str.upper()
    mapped["phone"] = _get_col(df, ["Phone", "Téléphone"]).astype(str).str.strip()
    mapped["email"] = _get_col(df, ["Email", "Courriel"])
    mapped["website"] = _get_col(df, ["Website", "Site web"])
    mapped["sic_code"] = _get_col(df, ["SIC Code", "Code SIC", "Category Code"])
    mapped["industry_description"] = _get_col(df, ["Category", "Catégorie", "Industry"])
    mapped["num_employees"] = pd.to_numeric(_get_col(df, ["Employees", "Nb employés"]), errors="coerce")
    mapped["annual_revenue"] = pd.to_numeric(_get_col(df, ["Revenue", "Chiffre d'affaires"]), errors="coerce")

    mapped["address_normalized"] = mapped["address_raw"].apply(normalize_address)
    return mapped


def main():
    print("=" * 60)
    print(" STEP 1: INGEST")
    print("=" * 60)

    icric_df = load_icric(RAW_ICRIC_FILE)
    yp_df = load_yellowpages(RAW_YELLOWPAGES_FILE)

    # Merge both sources
    df = pd.concat([icric_df, yp_df], ignore_index=True)

    # Drop rows with no company name (useless)
    before = len(df)
    df = df.dropna(subset=["company_name"])
    df = df[df["company_name"].astype(str).str.strip() != ""]
    print(f"\n  [Clean] Dropped {before - len(df)} rows with no company name")

    print(f"\n  [OUTPUT] Total merged rows: {len(df)}")
    df.to_csv(CHECKPOINT_RAW, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved → {CHECKPOINT_RAW}")


if __name__ == "__main__":
    main()
