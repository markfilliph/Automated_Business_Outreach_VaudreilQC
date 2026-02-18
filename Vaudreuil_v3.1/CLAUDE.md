# Vaudreuil Acquisition MVP v3 — Build Rules

## What this is
A script pipeline to generate 75 scored acquisition leads across ALL
sectors (except retail and restaurants) in Vaudreuil-Dorion, Quebec.
Revenue cap: $5M. It runs once or twice. It is NOT a SaaS product.

## Version history
- v1: Manufacturing-only, basic 4-factor scoring
- v2: Manufacturing-only, 6-factor scoring, Hamilton feature port
- v3: All sectors except retail/restaurants, subsidiary detection,
      cross-sector scoring, $5M cap, ownership signal scoring

## Hard Rules — Do Not Violate
- **Synchronous only.** No asyncio, no aiohttp. Use `requests` in sync mode.
- **No database.** State lives in Pandas DataFrames. Checkpoints are CSV files in `data/`.
- **No ORM, no models layer.** DataFrames only.
- **No YAML/JSON config loading.** Constants go in `config.py` as plain variables.
- **No complex class hierarchies.** Gates are simple functions: `def filter_by_X(df) -> df`
- **No tenacity retry decorators on everything.** Retries exist ONLY in `05_enrich_req.py`.
- **Cache is file-based JSON only.** No SQLite for caching. Files in `data/cache/`.

## Sector Scope (v3)
- **INCLUDE:** Manufacturing, construction, trades, transportation, logistics,
  professional services, wholesale/distribution, specialized services,
  food production, equipment, maintenance, IT services, engineering.
- **EXCLUDE:** Retail stores, restaurants/bars/food service, churches, schools,
  daycares, hospitals, government, non-profits.
- **EXCLUDE:** Known chains, franchises, large corporations.
- **EXCLUDE:** Subsidiaries of publicly traded or multinational parent companies.

## Pipeline Order
```
python 00_acquire_leads.py   -> data/raw_candidates.csv
python 01_ingest.py          -> data/raw_candidates.csv
python 02_filter.py          -> data/filtered_candidates.csv  (5 gates: region, sector, chains, subsidiaries, employees)
python 03_enrich_google.py   -> data/google_enriched.csv
python 04_deduplicate.py     -> data/deduped_candidates.csv
python 05_enrich_req.py      -> data/req_enriched.csv
python 06_score.py           -> data/scored_candidates.csv    (8-factor scoring)
python 07_export.py          -> data/top_75_for_review.csv    (Hamilton standard 17-field CSV)
python 08_export_excel.py    -> data/Vaudreuil_Acquisition_Leads.xlsx  (formatted workbook)
python 09_review_queue.py    -> human review CLI
```

## Output Format (Hamilton Standard)
The export scripts produce output identical to the Hamilton MVP's Burlington
STANDARDIZED format. 17 fields in this exact order:

1.  business_name
2.  address
3.  city
4.  postal_code
5.  website
6.  phone
7.  owner_name          (from REQ officer/dirigeant data)
8.  owner_confidence    (high/medium/none)
9.  owner_source        (REQ or manual research note)
10. industry            (manufacturing, construction, transportation, etc.)
11. category_standardized  (General Contractor, Precision Manufacturing, etc.)
12. employee_range_estimate (10-20, 12-35, etc.)
13. revenue_range_estimate  ($1.2M-$2.4M format)
14. sde_range_estimate      (SDE calculated from industry-specific margins)
15. age_range_estimate      (from REQ registration date)
16. acquisition_fit_score   (0-100, from 8-factor scoring)
17. important_notes         (category tag, fit assessment, ownership signals)

## Key Technical Decisions
- **Acquisition is two-phase** (v3): Phase 1 is a geographic grid sweep
  (type=establishment, no keywords) that catches everything in the bounding box.
  Phase 2 supplements with keyword queries for specific sectors. This ensures
  the funnel mouth is open wide enough to feed the exclusion-based filtering.
  Grid cell size is configurable: 500m (thorough, ~336 cells) to 1000m (fast, ~85 cells).
- **REQ scraping:** Playwright only. Single browser session reused across all lookups.
  Retry logic lives in `05_enrich_req.py`, not in the scraper utility.
  Slowest step: ~12 seconds per company, plan for 25-50 minutes on 200 companies.
- **Deduplication runs BEFORE REQ scraping** to avoid hitting the registry twice.
- **Sector filtering is exclusion-based** (v3): include everything, remove retail/restaurants.
  This is the opposite of v2 which was inclusion-based (only manufacturing keywords).
- **Subsidiary detection** (NEW v3): catches Mersen, Excelitas, Winpak, Cascades, etc.
  These pass all other filters but are divisions of multinationals.
  Uses REQ parent company data when available; falls back to name/description patterns.
- **Scoring uses 8 factors** (v3): years, reviews, sector signal, employees,
  data quality, website, location, ownership signal. Weights sum to 1.0.
- **Revenue cap:** $5M (was $2M in v2). External revenue data above the cap is
  FLAGGED but NOT removed (private company revenue data is unreliable).
  Internal estimate_revenue() has no hard cap (informational for broker).
  Flags surface in important_notes so human reviewer can investigate.
- **Export matches Hamilton MVP Burlington STANDARDIZED format** exactly.
  17 fields, identical column names and order. SDE uses industry-specific margins
  (not flat 15%).

## Dependencies
- Python 3.8+
- pandas, requests, python-dotenv
- playwright (for REQ scraping only; run `playwright install chromium` after pip install)
- openpyxl (for Excel export only)

## Utility Modules
- `utils/chain_filter.py` — chains/franchises (Quebec-calibrated, all sectors, 100+ entries)
- `utils/subsidiary_detector.py` — NEW v3: multinational subsidiary detection
- `utils/req_scraper.py` — Playwright-based Quebec enterprise registry scraper
- `utils/cache.py` — file-based JSON API response cache
- `utils/website_validator.py` — synchronous HTTP website validation
