"""
STEP 5: REQ ENRICHMENT

Scrapes the Quebec business registry (REQ) for each candidate to get:
  - NEQ number (unique business identifier)
  - Registration date (used to calculate years in business)
  - Corporate status (active / dissolved)

WHY RUN AFTER DEDUPLICATION?
  This is the slowest, most fragile step. Running it on deduplicated data
  means fewer requests, less risk of IP banning, and faster execution.

Technical decisions:
  - SINGLE Playwright browser session reused across all companies.
    Launching a new browser per company would add 2-3 seconds each
    and make 200 companies take 10+ minutes just on startup overhead.
  - Retry logic (with backoff) is applied here per company.
    This is the ONLY place in the codebase with retries.
  - If REQ blocks us or a company is not found: flag as "Unverified".
    The lead is NEVER dropped. The broker can verify manually later.

Adds columns:
  - neq
  - req_registration_date
  - req_status
  - verification_status   ("Verified" or "Unverified")

Input:  data/deduped_candidates.csv
Output: data/req_enriched.csv
"""

import pandas as pd
import time
import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import CHECKPOINT_DEDUPED, CHECKPOINT_REQ, REQ_MAX_RETRIES, REQ_TIMEOUT_MS
from utils.req_scraper import scrape_page


# ─── Default result when scraping fails or company not found ─────────────────
UNVERIFIED = {
    "neq": None,
    "req_registration_date": None,
    "req_status": None,
    "verification_status": "Unverified",
}


def scrape_with_retry(page, company_name: str) -> dict:
    """
    Attempt to scrape REQ for a single company, with retry + backoff.
    Always returns a dict — never raises. Failures become "Unverified".
    """
    for attempt in range(1, REQ_MAX_RETRIES + 1):
        try:
            result = scrape_page(page, company_name)

            if result is None:
                # Company genuinely not in REQ (not an error)
                print(f"    → Not found in REQ")
                return UNVERIFIED

            # Success — mark as Verified only if we actually got a NEQ
            return {
                "neq": result.get("neq"),
                "req_registration_date": result.get("registration_date"),
                "req_status": result.get("status"),
                "verification_status": "Verified" if result.get("neq") else "Unverified",
            }

        except Exception as e:
            print(f"    → Attempt {attempt}/{REQ_MAX_RETRIES} failed: {e}")
            if attempt < REQ_MAX_RETRIES:
                wait = 3 * attempt  # 3s, 6s, 9s
                print(f"    → Retrying in {wait}s...")
                time.sleep(wait)

    # All retries exhausted
    print(f"    → All retries exhausted — flagged Unverified")
    return UNVERIFIED


def ensure_playwright_installed():
    """Make sure Playwright chromium browser is downloaded."""
    print("  [Setup] Checking Playwright browsers...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
    )
    print("  [Setup] Playwright ready.\n")


def main():
    print("=" * 60)
    print(" STEP 5: REQ ENRICHMENT (Playwright)")
    print("=" * 60)

    ensure_playwright_installed()

    df = pd.read_csv(CHECKPOINT_DEDUPED)
    print(f"  [INPUT] {len(df)} rows from {CHECKPOINT_DEDUPED}\n")

    from playwright.sync_api import sync_playwright

    req_rows = []

    with sync_playwright() as p:
        # ── Single browser session for all companies ───────────────────
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(REQ_TIMEOUT_MS)

        for i, row in df.iterrows():
            company = str(row["company_name"])
            print(f"  [{i + 1}/{len(df)}] {company}")

            fields = scrape_with_retry(page, company)
            req_rows.append(fields)

            # Polite delay between requests
            time.sleep(1)

        browser.close()

    # ── Merge REQ data back ─────────────────────────────────────────────
    req_df = pd.DataFrame(req_rows)
    df = pd.concat([df.reset_index(drop=True), req_df], axis=1)

    # ── Summary ─────────────────────────────────────────────────────────
    status_counts = df["verification_status"].value_counts().to_dict()
    print(f"\n  [REQ Results] {status_counts}")

    print(f"\n  [OUTPUT] REQ-enriched candidates: {len(df)}")
    df.to_csv(CHECKPOINT_REQ, index=False, encoding="utf-8")
    print(f"  [OUTPUT] Saved → {CHECKPOINT_REQ}")


if __name__ == "__main__":
    main()
