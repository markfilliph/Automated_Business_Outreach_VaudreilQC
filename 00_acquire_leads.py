"""
STEP 0: ACQUIRE LEADS VIA GOOGLE PLACES

Searches Google Places API for manufacturing businesses in Vaudreuil area.
Bypasses the need for iCRIQ/YellowPages CSV exports.

This script searches for various manufacturing-related terms and compiles
results into the standard raw_candidates.csv format.

Output: data/raw_candidates.csv
"""

import pandas as pd
import googlemaps
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    GOOGLE_PLACES_API_KEY,
    TARGET_CITY,
    TARGET_POSTAL_PREFIXES,
    CHECKPOINT_RAW,
    GOOGLE_DELAY_SECONDS,
)

# Search queries to find manufacturing businesses
SEARCH_QUERIES = [
    "manufacturing Vaudreuil-Dorion",
    "fabrication Vaudreuil-Dorion",
    "usine Vaudreuil-Dorion",
    "industrial Vaudreuil-Dorion",
    "factory Vaudreuil-Dorion",
    "machine shop Vaudreuil-Dorion",
    "metal fabrication Vaudreuil-Dorion",
    "plastics manufacturing Vaudreuil-Dorion",
    "wood manufacturing Vaudreuil-Dorion",
    "food processing Vaudreuil-Dorion",
    "printing company Vaudreuil-Dorion",
    "packaging Vaudreuil-Dorion",
    "manufacturing Ile-Perrot",
    "manufacturing Pincourt",
    "manufacturing Dorion",
    "industrial park Vaudreuil",
]

# Vaudreuil-Dorion coordinates for nearby search
VAUDREUIL_LAT = 45.4008
VAUDREUIL_LNG = -74.0310
SEARCH_RADIUS = 15000  # 15km radius


def init_client() -> googlemaps.Client:
    """Initialize the Google Maps client."""
    if not GOOGLE_PLACES_API_KEY or GOOGLE_PLACES_API_KEY == "YOUR_GOOGLE_PLACES_API_KEY":
        raise ValueError(
            "GOOGLE_PLACES_API_KEY is not set.\n"
            "Create a .env file with: GOOGLE_PLACES_API_KEY=your_key"
        )
    return googlemaps.Client(key=GOOGLE_PLACES_API_KEY)


def search_places(client, query: str) -> list:
    """Search Google Places with a text query."""
    try:
        results = client.places(
            query=query,
            location=(VAUDREUIL_LAT, VAUDREUIL_LNG),
            radius=SEARCH_RADIUS,
        )
        return results.get("results", [])
    except Exception as e:
        print(f"    [Error] {query}: {e}")
        return []


def extract_place_data(place: dict) -> dict:
    """Extract relevant fields from a Google Places result."""
    address = place.get("formatted_address", "")

    # Extract postal code from address
    postal_code = ""
    import re
    postal_match = re.search(r"([A-Za-z]\d[A-Za-z])\s*(\d[A-Za-z]\d)", address)
    if postal_match:
        postal_code = f"{postal_match.group(1).upper()} {postal_match.group(2).upper()}"

    return {
        "source": "GooglePlaces",
        "company_name": place.get("name", ""),
        "address_raw": address,
        "address_normalized": address.upper(),
        "city": TARGET_CITY,
        "province": "QC",
        "postal_code": postal_code,
        "phone": "",  # Will be enriched later
        "email": "",
        "website": "",
        "sic_code": "",
        "industry_description": ", ".join(place.get("types", [])),
        "num_employees": None,
        "annual_revenue": None,
        "google_place_id": place.get("place_id"),
        "business_status": place.get("business_status", "UNKNOWN"),
        "review_count": place.get("user_ratings_total", 0),
        "google_rating": place.get("rating", 0),
    }


def get_place_details(client, place_id: str) -> dict:
    """Get detailed info for a place including phone and website."""
    try:
        result = client.place(place_id, fields=[
            "formatted_phone_number",
            "website",
            "url",
        ])
        return result.get("result", {})
    except Exception:
        return {}


def main():
    print("=" * 60)
    print(" STEP 0: ACQUIRE LEADS VIA GOOGLE PLACES")
    print("=" * 60)

    client = init_client()
    all_places = {}  # Use dict to dedupe by place_id

    # ── Search with multiple queries ─────────────────────────────────
    for query in SEARCH_QUERIES:
        print(f"  Searching: {query}")
        results = search_places(client, query)
        print(f"    Found {len(results)} results")

        for place in results:
            place_id = place.get("place_id")
            if place_id and place_id not in all_places:
                all_places[place_id] = place

        time.sleep(GOOGLE_DELAY_SECONDS)

    print(f"\n  [Total] {len(all_places)} unique places found")

    # ── Extract and enrich data ──────────────────────────────────────
    print("\n  Enriching with contact details...")
    rows = []

    for i, (place_id, place) in enumerate(all_places.items()):
        data = extract_place_data(place)

        # Get additional details (phone, website)
        details = get_place_details(client, place_id)
        data["phone"] = details.get("formatted_phone_number", "")
        data["website"] = details.get("website", "")
        data["google_url"] = details.get("url", "")

        rows.append(data)

        if (i + 1) % 10 == 0:
            print(f"    Processed {i + 1}/{len(all_places)}")

        time.sleep(GOOGLE_DELAY_SECONDS)

    # ── Filter to target postal codes ────────────────────────────────
    df = pd.DataFrame(rows)
    before = len(df)

    # Keep only businesses in target postal code area
    df["postal_prefix"] = df["postal_code"].str[:3].str.upper()
    df = df[
        df["postal_prefix"].isin(TARGET_POSTAL_PREFIXES) |
        df["postal_code"].str.strip().eq("")  # Keep unknowns for manual review
    ].copy()

    print(f"\n  [Filter] {before} → {len(df)} (Vaudreuil area postal codes)")

    # ── Save ─────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(CHECKPOINT_RAW), exist_ok=True)
    df.to_csv(CHECKPOINT_RAW, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] Saved {len(df)} leads → {CHECKPOINT_RAW}")

    # Preview
    print("\n  Sample leads found:")
    for _, row in df.head(5).iterrows():
        print(f"    • {row['company_name'][:50]}")


if __name__ == "__main__":
    main()
