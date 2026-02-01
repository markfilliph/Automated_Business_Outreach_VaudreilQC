# Vaudreuil Acquisition MVP — Build Rules

## What this is
A script pipeline to generate 50 scored manufacturing acquisition leads
in Vaudreuil, Quebec. It runs once or twice. It is NOT a SaaS product.

## Hard Rules — Do Not Violate
- **Synchronous only.** No asyncio, no aiohttp, no aiolimiter. Use `requests` or `httpx` in sync mode.
- **No database.** State lives in a Pandas DataFrame. Checkpoints are CSV files in `data/`.
- **No ORM, no models layer.** DataFrames only.
- **No YAML/JSON config loading.** Constants go in `config.py` as plain variables.
- **No complex class hierarchies.** Gates are simple functions: `def filter_by_category(df) -> df`
- **No tenacity retry decorators on everything.** Retries exist ONLY in `05_enrich_req.py`.

## Pipeline Order
Each script reads a CSV checkpoint, does one job, writes the next CSV.

**CRITICAL:** Deduplication runs BEFORE REQ scraping to avoid hitting the
government registry twice for the same company (saves time, reduces IP ban risk).

```
python 01_ingest.py        → data/raw_candidates.csv
python 02_filter.py        → data/filtered_candidates.csv
python 03_enrich_google.py → data/google_enriched.csv
python 04_deduplicate.py   → data/deduped_candidates.csv   ← dedup BEFORE REQ
python 05_enrich_req.py    → data/req_enriched.csv         ← slowest step, run last
python 06_score.py         → data/scored_candidates.csv
python 07_export.py        → data/top_50_for_review.csv
```

## Key Technical Decisions
- **REQ scraping:** Playwright only. Single browser session reused across all companies (performance).
  If it fails, flag lead as `verification_status = "Unverified"` — do NOT drop it.
- **Matching:** Phone number is primary key. Fuzzy name match (>85%) + postal code match as fallback.
  Use `rapidfuzz`. Do NOT use deterministic string matching.
- **Google Places:** Only call AFTER filtering. Check `business_status == "OPERATIONAL"` strictly.
- **Quebec addresses:** Trust postal code above all. Strip unit numbers before string comparison.
- **NEQ not found:** Do NOT discard the lead. Leave NEQ field blank, let broker verify later.

## Target Numbers
- Raw ingest: ~2,000 rows
- After filtering: ~200 candidates
- After enrichment + scoring: top 50 exported

## Setup
```bash
pip install -r requirements.txt
python -m playwright install chromium
```
