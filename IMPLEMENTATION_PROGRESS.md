# Vaudreuil Acquisition MVP — Implementation Progress

## Overview
Pipeline to generate 50 scored manufacturing acquisition leads in Vaudreuil, Quebec.

---

## Pipeline Status

| Step | Script | Status | Description |
|------|--------|--------|-------------|
| 1 | `01_ingest.py` | ✅ Complete | Loads iCRIQ + YellowPages CSVs → `data/raw_candidates.csv` |
| 2 | `02_filter.py` | ✅ Complete | Region/category/employee filters → `data/filtered_candidates.csv` |
| 3 | `03_enrich_google.py` | ✅ Complete | Google Places API enrichment → `data/google_enriched.csv` |
| 4 | `04_deduplicate.py` | ✅ Complete | Phone/fuzzy name deduplication → `data/deduped_candidates.csv` |
| 5 | `05_enrich_req.py` | ✅ Complete | REQ registry scraping (Playwright) → `data/req_enriched.csv` |
| 6 | `06_score.py` | ✅ Complete | Weighted scoring + ranking → `data/scored_candidates.csv` |
| 7 | `07_export.py` | ✅ Complete | Export top 50 → `data/top_50_for_review.csv` |

**Note:** Deduplication (step 4) runs BEFORE REQ scraping (step 5) to avoid hitting
the government registry twice for the same company. Google data improves fuzzy matching.

---

## Utilities Status

| Module | Status | Description |
|--------|--------|-------------|
| `utils/address.py` | ✅ Complete | Quebec address normalization |
| `utils/fuzzy_match.py` | ✅ Complete | Phone + fuzzy name matching |
| `utils/req_scraper.py` | ✅ Complete | REQ page interaction logic |
| `config.py` | ✅ Complete | All constants/configuration |

---

## Directory Structure

```
project/
├── config.py                 # ✅ Exists
├── requirements.txt          # ✅ Exists
├── CLAUDE.md                 # ✅ Exists
├── .gitignore                # ✅ Exists
├── 01_ingest.py              # ✅ Exists
├── 02_filter.py              # ✅ Exists
├── 03_enrich_google.py       # ✅ Exists
├── 04_deduplicate.py         # ✅ Exists
├── 05_enrich_req.py          # ✅ Exists
├── 06_score.py               # ✅ Exists
├── 07_export.py              # ✅ Exists
├── utils/                    # ✅ Exists
│   ├── __init__.py           # ✅ Exists
│   ├── address.py            # ✅ Exists
│   ├── fuzzy_match.py        # ✅ Exists
│   └── req_scraper.py        # ✅ Exists
└── data/                     # ✅ Exists
    └── raw/                  # ✅ Exists (place input CSVs here)
```

---

## Pre-Run Checklist

- [x] Create `data/` and `data/raw/` directories
- [x] Move utility files to `utils/` directory
- [x] Create `utils/__init__.py`
- [x] Push to GitHub
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Install Playwright browser: `python -m playwright install chromium`
- [ ] Set Google API key: `export GOOGLE_PLACES_API_KEY=your_key`
- [ ] Place input files:
  - `data/raw/icric_export.csv`
  - `data/raw/yellowpages_export.csv`

---

## Run Order

```bash
# Step 1: Ingest raw data
python 01_ingest.py

# Step 2: Filter by region/category/employees
python 02_filter.py

# Step 3: Enrich with Google Places (requires API key)
python 03_enrich_google.py

# Step 4: Deduplicate (BEFORE REQ to reduce scraping load)
python 04_deduplicate.py

# Step 5: Enrich with REQ registry (slowest step, runs on deduped data)
python 05_enrich_req.py

# Step 6: Score and rank candidates
python 06_score.py

# Step 7: Export top 50 leads
python 07_export.py
```

---

## Expected Data Flow

```
~2,000 rows (raw) → ~200 (filtered) → ~150 (deduped) → 50 (exported)
```

---

## Known Issues

All structural issues resolved.

---

## Next Steps (Priority Order)

1. ✅ **Code complete** — all 7 pipeline scripts written
2. ✅ **Fix structure** — directories created, files moved
3. ✅ **Push to GitHub** — repo initialized and pushed
4. ⏳ **Acquire data** — get iCRIQ + YellowPages exports
5. ⏳ **Get API key** — Google Places API
6. ⏳ **Run pipeline** — execute steps 1-7
7. ⏳ **Manual review** — verify top 50 leads

---

*Last updated: 2026-02-01*
