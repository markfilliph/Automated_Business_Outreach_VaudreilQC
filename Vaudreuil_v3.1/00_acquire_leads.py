"""
STEP 0: ACQUIRE LEADS (v3: All-Sector Geographic Sweep)

Two-phase acquisition strategy:
  Phase 1: Geographic grid sweep — divides the Vaudreuil-Dorion bounding box
           into ~500m cells, queries Google Places nearbySearch with
           type=establishment for each cell. This catches EVERYTHING:
           manufacturers, contractors, trucking companies, accountants,
           auto shops — anything that exists as a business listing.

  Phase 2: Keyword supplement — targeted textSearch queries for specific
           sectors that may not appear as "establishment" in Places
           (e.g., home-based businesses, newly listed companies).

Deduplication is by Google place_id, so overlapping cells and redundant
keyword hits don't produce duplicate rows.

Output: data/raw_candidates.csv

Requires: GOOGLE_PLACES_API_KEY in .env

Cost estimate:
  Grid: ~40-80 cells depending on density x 1-3 pages each = 40-240 API calls
  Keywords: ~40 keywords x 1-3 pages each = 40-120 API calls
  Total: 80-360 API calls at $0.032/call = $2.50-$11.50 per run
  Budget ceiling with 60-result pagination: ~$20 worst case
"""

import requests
import pandas as pd
import time
import json
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    GOOGLE_PLACES_API_KEY,
    GEO_BOUNDS,
    GRID_CELL_SIZE_M,
    GRID_SEARCH_RADIUS_M,
    GRID_MAX_RESULTS_PER_CELL,
    GOOGLE_DELAY_SECONDS,
    TARGET_CITY,
    TARGET_PROVINCE,
    TARGET_POSTAL_PREFIXES,
    CHECKPOINT_RAW,
    ACQUISITION_KEYWORDS_FR,
    ACQUISITION_KEYWORDS_EN,
    CACHE_ENABLED,
)

NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
TEXT_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Cache directory for raw API responses (avoids re-querying on re-runs)
CACHE_DIR = "data/cache/acquisition"


def meters_to_degrees_lat(meters):
    """Convert meters to approximate latitude degrees."""
    return meters / 111_320


def meters_to_degrees_lng(meters, lat):
    """Convert meters to approximate longitude degrees at a given latitude."""
    return meters / (111_320 * math.cos(math.radians(lat)))


def generate_grid_centers():
    """Generate grid cell center points covering the bounding box."""
    centers = []
    mid_lat = (GEO_BOUNDS["south"] + GEO_BOUNDS["north"]) / 2
    lat_step = meters_to_degrees_lat(GRID_CELL_SIZE_M)
    lng_step = meters_to_degrees_lng(GRID_CELL_SIZE_M, mid_lat)

    lat = GEO_BOUNDS["south"]
    while lat <= GEO_BOUNDS["north"]:
        lng = GEO_BOUNDS["west"]
        while lng <= GEO_BOUNDS["east"]:
            centers.append((lat, lng))
            lng += lng_step
        lat += lat_step

    return centers


def cache_key(prefix, params_str):
    """Generate a safe filesystem cache key."""
    import hashlib
    h = hashlib.md5(params_str.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{prefix}_{h}.json")


def cached_request(url, params, prefix="api"):
    """Make a cached API request. Returns JSON response or None on failure."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key_str = json.dumps(params, sort_keys=True)
    c_path = cache_key(prefix, key_str)

    if CACHE_ENABLED and os.path.exists(c_path):
        with open(c_path, "r") as f:
            return json.load(f)

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if CACHE_ENABLED and data.get("status") in ("OK", "ZERO_RESULTS"):
            with open(c_path, "w") as f:
                json.dump(data, f)

        return data
    except requests.RequestException as e:
        print(f"    [ERROR] API request failed: {e}")
        return None


def extract_place_data(result):
    """Extract standardized fields from a Google Places result."""
    location = result.get("geometry", {}).get("location", {})
    return {
        "google_place_id": result.get("place_id", ""),
        "company_name": result.get("name", ""),
        "address_raw": result.get("vicinity", result.get("formatted_address", "")),
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "google_types": ",".join(result.get("types", [])),
        "google_rating": result.get("rating"),
        "review_count": result.get("user_ratings_total", 0),
        "business_status": result.get("business_status", ""),
        "price_level": result.get("price_level"),
    }


def fetch_all_pages(url, params, prefix, max_results=60):
    """Fetch up to 3 pages of Google Places results (20 per page, max 60)."""
    all_results = []

    data = cached_request(url, params, prefix=prefix)
    if not data or data.get("status") not in ("OK", "ZERO_RESULTS"):
        return all_results

    all_results.extend(data.get("results", []))

    # Follow next_page_token for pages 2 and 3
    page = 1
    while "next_page_token" in data and len(all_results) < max_results and page < 3:
        page += 1
        # Google requires a short delay before using next_page_token
        time.sleep(2.0)
        next_params = {
            "pagetoken": data["next_page_token"],
            "key": params["key"],
        }
        data = cached_request(url, next_params, prefix=f"{prefix}_p{page}")
        if data and data.get("status") == "OK":
            all_results.extend(data.get("results", []))
        else:
            break

    return all_results


def phase1_grid_sweep():
    """Phase 1: Geographic grid sweep with type=establishment."""
    print("\n  PHASE 1: Geographic Grid Sweep")
    print("  " + "-" * 40)

    centers = generate_grid_centers()
    print(f"  Grid cells: {len(centers)} ({GRID_CELL_SIZE_M}m spacing)")
    print(f"  Search radius per cell: {GRID_SEARCH_RADIUS_M}m")
    print(f"  Bounds: {GEO_BOUNDS}")

    all_places = {}  # Keyed by place_id for dedup
    api_calls = 0

    for i, (lat, lng) in enumerate(centers):
        params = {
            "location": f"{lat},{lng}",
            "radius": GRID_SEARCH_RADIUS_M,
            "type": "establishment",
            "key": GOOGLE_PLACES_API_KEY,
        }

        results = fetch_all_pages(NEARBY_URL, params, prefix=f"grid_{i}")
        api_calls += 1  # Approximate (pagination adds more)

        for r in results:
            pid = r.get("place_id")
            if pid and pid not in all_places:
                all_places[pid] = extract_place_data(r)

        # Progress every 10 cells
        if (i + 1) % 10 == 0 or i == len(centers) - 1:
            print(f"    Cell {i+1}/{len(centers)}: {len(all_places)} unique places found")

        time.sleep(GOOGLE_DELAY_SECONDS)

    print(f"  Phase 1 complete: {len(all_places)} unique places from grid sweep")
    return all_places, api_calls


def phase2_keyword_supplement(existing_places):
    """Phase 2: Keyword-based textSearch to catch businesses missed by grid."""
    print("\n  PHASE 2: Keyword Supplement")
    print("  " + "-" * 40)

    all_keywords = ACQUISITION_KEYWORDS_FR + ACQUISITION_KEYWORDS_EN
    print(f"  Keywords: {len(all_keywords)} ({len(ACQUISITION_KEYWORDS_FR)} FR + {len(ACQUISITION_KEYWORDS_EN)} EN)")

    new_places = 0
    api_calls = 0

    for i, keyword in enumerate(all_keywords):
        query = f"{keyword} {TARGET_CITY}"
        params = {
            "query": query,
            "key": GOOGLE_PLACES_API_KEY,
        }

        results = fetch_all_pages(TEXT_URL, params, prefix=f"kw_{i}")
        api_calls += 1

        added_this_kw = 0
        for r in results:
            pid = r.get("place_id")
            if pid and pid not in existing_places:
                existing_places[pid] = extract_place_data(r)
                new_places += 1
                added_this_kw += 1

        if added_this_kw > 0:
            print(f"    [{keyword:30s}] +{added_this_kw} new")

        time.sleep(GOOGLE_DELAY_SECONDS)

    print(f"  Phase 2 complete: {new_places} new places from keywords")
    return existing_places, api_calls


def add_metadata(places_dict):
    """Add pipeline metadata columns to each place."""
    for pid, place in places_dict.items():
        place["data_source"] = "google_places"
        place["acquired_at"] = datetime.now().isoformat()
        place["pipeline_version"] = "v3"
    return places_dict


def basic_quality_filter(df):
    """Remove obviously non-business results before saving."""
    before = len(df)

    # Remove places with no name
    df = df[df["company_name"].str.strip().str.len() > 0].copy()

    # Remove permanently closed businesses
    df = df[df["business_status"] != "CLOSED_PERMANENTLY"].copy()

    # Remove place types that are clearly not businesses
    non_business_types = [
        "locality", "political", "natural_feature",
        "park", "cemetery", "campground",
        "bus_station", "train_station", "transit_station",
        "parking", "gas_station",
    ]
    for nbt in non_business_types:
        df = df[~df["google_types"].str.contains(nbt, case=False, na=False)].copy()

    after = len(df)
    removed = before - after
    if removed > 0:
        print(f"  [QUALITY] Removed {removed} non-business entries (closed, parks, transit, etc.)")
    return df


def main():
    print("=" * 60)
    print(" STEP 0: ACQUIRE LEADS (v3: All-Sector Geographic Sweep)")
    print("=" * 60)

    if GOOGLE_PLACES_API_KEY == "YOUR_GOOGLE_PLACES_API_KEY":
        print("\n  [ERROR] GOOGLE_PLACES_API_KEY not set in .env file.")
        print("  Set it and re-run. Exiting.")
        sys.exit(1)

    # Phase 1: Grid sweep
    places, calls_1 = phase1_grid_sweep()

    # Phase 2: Keyword supplement
    places, calls_2 = phase2_keyword_supplement(places)

    # Add metadata
    places = add_metadata(places)

    # Convert to DataFrame
    df = pd.DataFrame(list(places.values()))
    print(f"\n  Total unique places acquired: {len(df)}")
    print(f"  Total API calls (approx): {calls_1 + calls_2}")

    # Basic quality filter
    df = basic_quality_filter(df)

    # Save
    os.makedirs(os.path.dirname(CHECKPOINT_RAW), exist_ok=True)
    df.to_csv(CHECKPOINT_RAW, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] {len(df)} raw candidates saved -> {CHECKPOINT_RAW}")

    # Summary stats
    print(f"\n  Place type summary (top 15):")
    type_counts = {}
    for types_str in df["google_types"]:
        if pd.notna(types_str):
            for t in str(types_str).split(","):
                t = t.strip()
                if t:
                    type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"    {t:35s} {c:>4}")

    est_cost = (calls_1 + calls_2) * 0.032
    print(f"\n  Estimated API cost: ${est_cost:.2f}")


if __name__ == "__main__":
    main()
