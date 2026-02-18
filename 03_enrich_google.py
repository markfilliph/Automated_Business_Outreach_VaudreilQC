"""
STEP 3: GOOGLE PLACES ENRICHMENT (Enhanced v2)

v2 enhancements ported from Hamilton MVP:
  - API response caching (saves 50%+ on re-runs)
  - Website validation (verify URLs actually resolve)
  - Review count integration for revenue estimation signals

Queries Google Places API for each filtered candidate to verify the business
is real and operational. Adds review data for scoring.

IMPORTANT: This runs AFTER filtering. We only spend API credits on the ~200
rows that already passed the gates, not the full 2,000.

Input:  data/filtered_candidates.csv
Output: data/google_enriched.csv
"""

import pandas as pd
import googlemaps
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    GOOGLE_PLACES_API_KEY,
    CHECKPOINT_FILTERED,
    CHECKPOINT_GOOGLE,
    TARGET_CITY,
    GOOGLE_DELAY_SECONDS,
    CACHE_ENABLED,
    WEBSITE_VALIDATION_ENABLED,
)
from utils import cache
from utils.website_validator import validate_website, normalize_url


def init_client() -> googlemaps.Client:
    """Initialize the Google Maps client. Fails fast if no API key."""
    if not GOOGLE_PLACES_API_KEY or GOOGLE_PLACES_API_KEY == "YOUR_GOOGLE_PLACES_API_KEY":
        raise ValueError(
            "GOOGLE_PLACES_API_KEY is not set.\n"
            "Option A: export GOOGLE_PLACES_API_KEY=your_key\n"
            "Option B: create a .env file with GOOGLE_PLACES_API_KEY=your_key"
        )
    return googlemaps.Client(key=GOOGLE_PLACES_API_KEY)


def search_and_get_details(client, company_name: str, postal_code: str) -> dict:
    """
    Search Google Places by name + location, then fetch full details.
    Uses cache to avoid redundant API calls on re-runs.
    """
    query = f"{company_name}, {TARGET_CITY}, {postal_code}, QC, Canada"

    # Check cache first
    if CACHE_ENABLED:
        cached = cache.get("google_details", query)
        if cached is not None:
            return cached

    try:
        results = client.places(query)
        if not results.get("results"):
            # Cache the miss too (avoids re-querying known misses)
            if CACHE_ENABLED:
                cache.put("google_details", query, {})
            return {}

        place_id = results["results"][0].get("place_id")
        if not place_id:
            if CACHE_ENABLED:
                cache.put("google_details", query, {})
            return {}

        details = client.place(place_id)
        result = details.get("result", {})

        # Cache the result
        if CACHE_ENABLED:
            cache.put("google_details", query, result)

        return result

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


def validate_websites(df: pd.DataFrame) -> pd.DataFrame:
    """
    NEW (v2): Validate that business websites actually resolve.
    Ported from Hamilton MVP's website verification system.

    Adds columns: website_valid, website_status
    """
    if not WEBSITE_VALIDATION_ENABLED:
        df["website_valid"] = None
        df["website_status"] = "Not checked"
        return df

    print("\n  Validating websites...")
    valid_count = 0
    invalid_count = 0
    no_url_count = 0

    results = []
    for _, row in df.iterrows():
        url = row.get("website", "")
        if not url or str(url).lower() in ("nan", "none", "", "unknown"):
            results.append({"website_valid": None, "website_status": "No URL"})
            no_url_count += 1
            continue

        is_valid, status, _ = validate_website(str(url))
        results.append({"website_valid": is_valid, "website_status": status})

        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1

        time.sleep(0.3)  # Polite delay

    result_df = pd.DataFrame(results, index=df.index)
    df = pd.concat([df, result_df], axis=1)

    print(f"    Valid: {valid_count}, Invalid: {invalid_count}, No URL: {no_url_count}")
    return df


def main():
    print("=" * 60)
    print(" STEP 3: GOOGLE PLACES ENRICHMENT (Enhanced v2)")
    print("=" * 60)

    if CACHE_ENABLED:
        cs = cache.stats()
        print(f"  [Cache] {cs['entries']} cached entries ({cs['size_kb']} KB)")

    client = init_client()
    df = pd.read_csv(CHECKPOINT_FILTERED)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_FILTERED}\n")

    google_rows = []
    cache_hits = 0
    api_calls = 0

    for i, row in df.iterrows():
        company = str(row["company_name"])
        postal = str(row.get("postal_code", ""))
        print(f"  [{i + 1}/{len(df)}] {company[:50]}...", end="")

        # Check if we'll get a cache hit
        query = f"{company}, {TARGET_CITY}, {postal}, QC, Canada"
        cached = cache.get("google_details", query) if CACHE_ENABLED else None

        if cached is not None:
            print(" (cached)")
            cache_hits += 1
        else:
            print("")
            api_calls += 1

        place = search_and_get_details(client, company, postal)
        google_rows.append(extract_fields(place))

        # Only delay on actual API calls, not cache hits
        if cached is None:
            time.sleep(GOOGLE_DELAY_SECONDS)

    if CACHE_ENABLED:
        print(f"\n  [Cache Stats] Hits: {cache_hits}, API calls: {api_calls}")
        savings = (cache_hits / max(len(df), 1)) * 100
        print(f"  [Cache Stats] Saved {savings:.0f}% of API calls")

    # Merge google data back
    google_df = pd.DataFrame(google_rows)
    df = pd.concat([df.reset_index(drop=True), google_df], axis=1)
    # Remove duplicate columns (keep first occurrence)
    df = df.loc[:, ~df.columns.duplicated()]

    # Filter out permanently closed businesses
    before = len(df)
    mask = df["business_status"] != "CLOSED_PERMANENTLY"
    df = df[mask].reset_index(drop=True)
    removed = before - len(df)
    print(f"\n  [Status Filter] Removed {removed} permanently closed businesses")

    # Website validation (NEW in v2)
    df = validate_websites(df)

    # Status breakdown
    status_counts = df["business_status"].value_counts().to_dict()
    print(f"  [Status Breakdown] {status_counts}")

    print(f"\n  [OUTPUT] Google-enriched candidates: {len(df)}")
    df.to_csv(CHECKPOINT_GOOGLE, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved -> {CHECKPOINT_GOOGLE}")


if __name__ == "__main__":
    main()
