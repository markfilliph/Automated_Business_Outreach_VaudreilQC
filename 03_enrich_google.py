"""
STEP 3: GOOGLE PLACES ENRICHMENT

Queries Google Places API for each filtered candidate to verify the business
is real and operational. Adds review data for scoring.

IMPORTANT: This runs AFTER filtering — we only spend API credits on the ~200
rows that already passed the gates, not the full 2,000.

Adds columns:
  - google_place_id
  - business_status      (OPERATIONAL, CLOSED_PERMANENTLY, etc.)
  - review_count
  - google_rating
  - google_url

Removes any business with business_status == CLOSED_PERMANENTLY.

Input:  data/filtered_candidates.csv
Output: data/google_enriched.csv
"""

import pandas as pd
import googlemaps
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import (
    GOOGLE_PLACES_API_KEY,
    CHECKPOINT_FILTERED,
    CHECKPOINT_GOOGLE,
    TARGET_CITY,
    GOOGLE_DELAY_SECONDS,
)


def init_client() -> googlemaps.Client:
    """Initialize the Google Maps client. Fails fast if no API key."""
    if not GOOGLE_PLACES_API_KEY or GOOGLE_PLACES_API_KEY == "YOUR_GOOGLE_PLACES_API_KEY":
        raise ValueError(
            "GOOGLE_PLACES_API_KEY is not set.\n"
            "Option A: export GOOGLE_PLACES_API_KEY=your_key\n"
            "Option B: edit config.py and replace the default value."
        )
    return googlemaps.Client(key=GOOGLE_PLACES_API_KEY)


def search_and_get_details(client, company_name: str, postal_code: str) -> dict:
    """
    Search Google Places by name + location, then fetch full details.
    Returns the place details dict, or empty dict if not found.
    """
    query = f"{company_name}, {TARGET_CITY}, {postal_code}, QC, Canada"

    try:
        # Text search to find the place
        results = client.places(query)
        if not results.get("results"):
            return {}

        place_id = results["results"][0].get("place_id")
        if not place_id:
            return {}

        # Full details fetch
        details = client.place(place_id)
        return details.get("result", {})

    except Exception as e:
        print(f"    [Google Error] {company_name}: {e}")
        return {}


def extract_fields(place: dict) -> dict:
    """Pull the fields we care about from a Google Places result."""
    if not place:
        return {
            "google_place_id": None,
            "business_status": "NOT_FOUND",
            "review_count": 0,
            "google_rating": 0.0,
            "google_url": None,
        }

    return {
        "google_place_id": place.get("place_id"),
        "business_status": place.get("business_status", "UNKNOWN"),
        "review_count": place.get("user_ratings_total", 0),
        "google_rating": place.get("rating", 0.0),
        "google_url": place.get("url"),
    }


def main():
    print("=" * 60)
    print(" STEP 3: GOOGLE PLACES ENRICHMENT")
    print("=" * 60)

    client = init_client()
    df = pd.read_csv(CHECKPOINT_FILTERED)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_FILTERED}\n")

    google_rows = []

    for i, row in df.iterrows():
        company = str(row["company_name"])
        postal = str(row.get("postal_code", ""))
        print(f"  [{i + 1}/{len(df)}] {company}...")

        place = search_and_get_details(client, company, postal)
        google_rows.append(extract_fields(place))

        time.sleep(GOOGLE_DELAY_SECONDS)

    # ── Merge google data back ──────────────────────────────────────────
    google_df = pd.DataFrame(google_rows)
    df = pd.concat([df.reset_index(drop=True), google_df], axis=1)

    # ── Filter out permanently closed businesses ───────────────────────
    before = len(df)
    df = df[df["business_status"] != "CLOSED_PERMANENTLY"].copy()
    removed = before - len(df)
    print(f"\n  [Status Filter] Removed {removed} permanently closed businesses")

    # ── Summary ─────────────────────────────────────────────────────────
    status_counts = df["business_status"].value_counts().to_dict()
    print(f"  [Status Breakdown] {status_counts}")

    print(f"\n  [OUTPUT] Google-enriched candidates: {len(df)}")
    df.to_csv(CHECKPOINT_GOOGLE, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved → {CHECKPOINT_GOOGLE}")


if __name__ == "__main__":
    main()
