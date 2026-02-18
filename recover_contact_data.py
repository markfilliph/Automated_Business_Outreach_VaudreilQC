"""
RECOVERY SCRIPT: Extract phone and website from existing cache.
Backfills contact data into google_enriched.csv and re-runs
steps 04 onwards to produce a clean final export.
Zero API calls. Zero cost.
"""

import os
import json
import pandas as pd

CACHE_DIR = "data/cache"
INPUT_FILE = "data/google_enriched.csv"
OUTPUT_FILE = "data/google_enriched.csv"  # Overwrites in place


def build_lookup_from_cache():
    """Scan all cache files and extract place_id -> phone/website mapping."""
    lookup = {}
    checked = 0
    recovered = 0

    for root, dirs, files in os.walk(CACHE_DIR):
        for f in files:
            path = os.path.join(root, f)
            try:
                with open(path) as fp:
                    entry = json.load(fp)

                data = entry.get("data", entry)

                if not isinstance(data, dict):
                    continue

                place_id = data.get("place_id")
                phone = data.get("formatted_phone_number")
                website = data.get("website")
                google_url = data.get("url")

                if place_id and (phone or website):
                    lookup[place_id] = {
                        "phone": phone,
                        "website": website,
                        "google_url": google_url or lookup.get(place_id, {}).get("google_url"),
                    }
                    recovered += 1

                checked += 1
            except Exception:
                pass

    print(f"  Cache files scanned: {checked}")
    print(f"  Entries with phone or website: {recovered}")
    return lookup


def main():
    print("=" * 60)
    print(" RECOVERY: Backfill phone + website from cache")
    print("=" * 60)

    lookup = build_lookup_from_cache()

    df = pd.read_csv(INPUT_FILE)
    print(f"\n  [INPUT] {len(df)} rows from {INPUT_FILE}")

    # Add columns if missing
    for col in ["phone", "website"]:
        if col not in df.columns:
            df[col] = None

    # Backfill from lookup
    phone_filled = 0
    website_filled = 0

    for idx, row in df.iterrows():
        pid = str(row.get("google_place_id", ""))
        if pid in lookup:
            entry = lookup[pid]
            if pd.isna(row.get("phone")) and entry.get("phone"):
                df.at[idx, "phone"] = entry["phone"]
                phone_filled += 1
            if pd.isna(row.get("website")) and entry.get("website"):
                df.at[idx, "website"] = entry["website"]
                website_filled += 1
            if entry.get("google_url") and pd.isna(row.get("google_url")):
                df.at[idx, "google_url"] = entry["google_url"]

    print(f"  Phone numbers recovered: {phone_filled}")
    print(f"  Websites recovered: {website_filled}")

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] Updated {OUTPUT_FILE}")
    print(f"  [COST] $0.00")


if __name__ == "__main__":
    main()
