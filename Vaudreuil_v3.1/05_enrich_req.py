"""
STEP 5: ENRICH WITH REQ (Registraire des entreprises du Québec)

Reads deduped_candidates.csv and enriches each company with data from
the Quebec enterprise registry:
  - Registration date (years in business)
  - Officer/dirigeant name (owner identification)
  - Parent company (subsidiary detection)
  - Legal form and status
  - NEQ number

This is the SLOWEST step in the pipeline. Each lookup requires:
  1. Loading the REQ search page (JS-heavy, ~2-3s)
  2. Submitting a search query (~1-2s)
  3. Loading the detail page (~2-3s)
  4. Random delay between lookups (2-5s)
  Total: ~7-15 seconds per company. 200 companies = 25-50 minutes.

CRITICAL: Deduplication runs BEFORE this step (step 04) to avoid
hitting the government registry twice for the same company.

Retry logic lives HERE, not in the scraper utility.
The build rules specify: "Retries exist ONLY in 05_enrich_req.py"

Input:  data/deduped_candidates.csv
Output: data/req_enriched.csv
"""

import pandas as pd
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config import (
    CHECKPOINT_DEDUPED,
    CHECKPOINT_REQ,
    REQ_MAX_RETRIES,
)
from utils.req_scraper import init_browser, close_browser, lookup_company


# REQ fields to merge into the DataFrame
REQ_FIELDS = [
    "neq",
    "req_status",
    "req_registration_date",
    "req_officer_name",
    "req_parent_company",
    "req_legal_form",
    "req_lookup_status",
]


def enrich_with_retry(page, company_name, max_retries=3):
    """Look up a company in REQ with retry logic.

    Retries on failure with exponential backoff.
    Returns the lookup result dict (always returns something).
    """
    for attempt in range(1, max_retries + 1):
        try:
            result = lookup_company(page, company_name)
            if result and result.get("req_lookup_status") != "detail_failed":
                return result
            # detail_failed is retryable
            if attempt < max_retries:
                wait = 5 * (2 ** (attempt - 1))  # 5s, 10s, 20s
                time.sleep(wait)
        except Exception as e:
            if attempt < max_retries:
                wait = 5 * (2 ** (attempt - 1))
                print(f"      Retry {attempt}/{max_retries} after error: {str(e)[:60]}")
                time.sleep(wait)
            else:
                return {
                    "neq": None,
                    "req_status": None,
                    "req_registration_date": None,
                    "req_officer_name": None,
                    "req_parent_company": None,
                    "req_legal_form": None,
                    "req_lookup_status": f"error: {str(e)[:100]}",
                }
    return result


def main():
    print("=" * 60)
    print(" STEP 5: ENRICH WITH REQ (Quebec Enterprise Registry)")
    print("=" * 60)

    df = pd.read_csv(CHECKPOINT_DEDUPED)
    print(f"  [INPUT] {len(df)} companies from {CHECKPOINT_DEDUPED}")

    # Estimate time
    est_minutes = len(df) * 12 / 60  # ~12 seconds per lookup average
    print(f"  [ESTIMATE] ~{est_minutes:.0f} minutes for {len(df)} lookups")

    # Initialize browser
    print(f"\n  Initializing Playwright browser...")
    pw, browser, page = init_browser()

    if not page:
        print("  [ERROR] Could not initialize browser. Saving without REQ data.")
        for field in REQ_FIELDS:
            df[field] = None
        df["req_lookup_status"] = "browser_init_failed"
        df.to_csv(CHECKPOINT_REQ, index=False, encoding="utf-8")
        print(f"  [OUTPUT] {len(df)} rows saved (no REQ data) -> {CHECKPOINT_REQ}")
        return

    # Process each company
    found = 0
    cached = 0
    failed = 0
    start_time = time.time()

    for i, (idx, row) in enumerate(df.iterrows()):
        company = str(row.get("company_name", "")).strip()
        if not company:
            for field in REQ_FIELDS:
                df.at[idx, field] = None
            df.at[idx, "req_lookup_status"] = "no_company_name"
            continue

        result = enrich_with_retry(page, company, max_retries=REQ_MAX_RETRIES)

        # Merge result into DataFrame
        for field in REQ_FIELDS:
            df.at[idx, field] = result.get(field)

        # Track stats
        status = result.get("req_lookup_status", "unknown")
        if status == "found":
            found += 1
        elif status == "cached":
            cached += 1
        else:
            failed += 1

        # Progress every 10 companies
        if (i + 1) % 10 == 0 or i == len(df) - 1:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
            remaining = (len(df) - i - 1) / rate if rate > 0 else 0
            print(
                f"    [{i+1:>4}/{len(df)}]  "
                f"found={found} cached={cached} failed={failed}  "
                f"({rate:.0f}/min, ~{remaining:.0f}m left)"
            )

    # Clean up browser
    close_browser(pw, browser)

    # Summary
    elapsed = time.time() - start_time
    print(f"\n  REQ enrichment complete in {elapsed/60:.1f} minutes")
    print(f"  Found: {found} | Cached: {cached} | Failed: {failed}")

    officer_count = df["req_officer_name"].notna().sum()
    date_count = df["req_registration_date"].notna().sum()
    parent_count = df["req_parent_company"].notna().sum()
    print(f"  Officers identified: {officer_count}/{len(df)}")
    print(f"  Registration dates: {date_count}/{len(df)}")
    print(f"  Parent companies: {parent_count}/{len(df)}")

    # Save
    df.to_csv(CHECKPOINT_REQ, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] {len(df)} rows saved -> {CHECKPOINT_REQ}")


if __name__ == "__main__":
    main()
