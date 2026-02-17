"""
REQ Scraper — Registraire des entreprises du Québec

Playwright-based scraper for the Quebec enterprise registry. Extracts:
  - NEQ number (unique enterprise identifier)
  - Registration date (critical for years-in-business scoring)
  - Officer/dirigeant name(s) (ownership identification)
  - Parent company (subsidiary detection)
  - Business status (active/inactive/struck off)
  - Legal form (inc., ltée, enr., SENC, etc.)

Design constraints (from CLAUDE.md hard rules):
  - Synchronous execution (no asyncio)
  - Retries allowed ONLY in 05_enrich_req.py (this module does not retry)
  - Single browser session reused across all lookups
  - File-based JSON cache (no SQLite)
  - Playwright only (no Selenium, no requests scraping)

The REQ site structure:
  Search page: /consulter/rechercher
  Results: JavaScript-rendered table
  Detail page: /consulter/[NEQ] — contains full enterprise info

Anti-blocking strategy:
  - 3-5 second random delays between requests
  - Human-like viewport and user agent
  - Session cookies maintained naturally via Playwright context
  - No concurrent requests; sequential processing only
"""

import json
import os
import re
import time
import random
from datetime import datetime

CACHE_DIR = "data/cache/req"


def init_browser():
    """Initialize a Playwright browser with a persistent context.

    Returns (playwright, browser, page) tuple.
    Caller is responsible for cleanup via close_browser().
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [ERROR] playwright not installed. Run: pip install playwright && playwright install chromium")
        return None, None, None

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="fr-CA",
    )
    page = context.new_page()
    return pw, browser, page


def close_browser(pw, browser):
    """Clean up browser resources."""
    try:
        if browser:
            browser.close()
        if pw:
            pw.stop()
    except Exception:
        pass


def get_cache_path(company_name):
    """Generate cache file path for a company."""
    import hashlib
    safe_name = hashlib.md5(company_name.lower().strip().encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"req_{safe_name}.json")


def load_cached(company_name):
    """Load cached REQ data for a company, if available."""
    path = get_cache_path(company_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Check cache age (7 day TTL)
                cached_at = data.get("cached_at", "")
                if cached_at:
                    age = (datetime.now() - datetime.fromisoformat(cached_at)).days
                    if age <= 7:
                        return data
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def save_cache(company_name, data):
    """Save REQ data to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    data["cached_at"] = datetime.now().isoformat()
    path = get_cache_path(company_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_company_name_for_search(name):
    """Clean company name for REQ search.

    The REQ search works best with the core legal name without
    common suffixes that may vary in registration vs. trade name.
    """
    name = name.strip()
    # Remove common suffixes that might differ
    suffixes = [
        " inc.", " inc", " ltée", " ltee", " ltd.", " ltd",
        " enr.", " enr", " s.e.n.c.", " senc",
    ]
    name_lower = name.lower()
    for suffix in suffixes:
        if name_lower.endswith(suffix):
            name = name[:len(name) - len(suffix)]
            break
    return name.strip()


def search_req(page, company_name, timeout_ms=30000):
    """Search the REQ for a company by name.

    Returns a list of search result dicts: [{neq, name, status, address}, ...]
    Returns empty list if no results or search fails.
    """
    search_url = "https://www.registraire.gouv.qc.ca/consulter/rechercher"
    clean_name = clean_company_name_for_search(company_name)

    try:
        page.goto(search_url, timeout=timeout_ms, wait_until="networkidle")
        time.sleep(random.uniform(1.0, 2.0))

        # Fill the search field
        # The REQ search page has a text input for company name
        search_input = page.locator('input[type="text"]').first
        search_input.fill(clean_name)
        time.sleep(random.uniform(0.5, 1.0))

        # Submit search
        submit_btn = page.locator('button[type="submit"], input[type="submit"]').first
        submit_btn.click()

        # Wait for results
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        time.sleep(random.uniform(1.5, 2.5))

        # Parse search results table
        results = []
        # Look for result rows (the REQ uses a table or list for results)
        rows = page.locator("table tbody tr, .result-item, .search-result").all()

        for row in rows[:10]:  # Cap at 10 results
            text = row.inner_text()
            # Try to extract NEQ (10-digit number)
            neq_match = re.search(r'\b(\d{10})\b', text)
            if neq_match:
                results.append({
                    "neq": neq_match.group(1),
                    "raw_text": text.strip()[:200],
                })

        return results

    except Exception as e:
        return []


def fetch_enterprise_detail(page, neq, timeout_ms=30000):
    """Fetch detailed enterprise info from REQ by NEQ number.

    Returns a dict with registration_date, officer_name, parent_company,
    status, legal_form, and other fields. Returns None on failure.
    """
    detail_url = f"https://www.registraire.gouv.qc.ca/consulter/{neq}"

    try:
        page.goto(detail_url, timeout=timeout_ms, wait_until="networkidle")
        time.sleep(random.uniform(1.5, 3.0))

        # Extract page text for parsing
        body_text = page.inner_text("body")

        result = {
            "neq": neq,
            "req_status": "Unknown",
            "req_registration_date": None,
            "req_officer_name": None,
            "req_parent_company": None,
            "req_legal_form": None,
            "req_address": None,
            "req_raw_text": body_text[:2000] if body_text else "",
        }

        # Extract registration date
        # Look for "Date d'immatriculation", "Constituée le", "Date de constitution"
        date_patterns = [
            r"(?:Date d'immatriculation|Constituée? le|Date de constitution)[:\s]*(\d{4}-\d{2}-\d{2})",
            r"(?:Date d'immatriculation|Constituée? le|Date de constitution)[:\s]*(\d{2}/\d{2}/\d{4})",
            r"(\d{4}-\d{2}-\d{2}).*(?:immatriculation|constitution)",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result["req_registration_date"] = match.group(1)
                break

        # Extract status
        status_patterns = [
            r"(Immatriculée?|Radiée?|Dissoute?|En défaut|Active|Inactive)",
        ]
        for pattern in status_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result["req_status"] = match.group(1)
                break

        # Extract officer/dirigeant name
        # REQ pages typically list "Administrateurs" or "Dirigeants"
        officer_patterns = [
            r"(?:Administrateur|Dirigeant|Président|Actionnaire)[:\s]*([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+){1,3})",
            r"(?:ADMINISTRATEUR|DIRIGEANT|PRÉSIDENT)[:\s]*([A-ZÀ-Ü][A-ZÀ-Ü\s]+[A-ZÀ-Ü])",
        ]
        for pattern in officer_patterns:
            match = re.search(pattern, body_text)
            if match:
                name = match.group(1).strip()
                # Exclude common false positives
                if len(name) > 4 and name.lower() not in ("québec", "canada", "montréal"):
                    result["req_officer_name"] = name
                    break

        # Extract parent company / "Constituant" / "Fondateur"
        parent_patterns = [
            r"(?:Constituant|Fondateur|Société mère|Actionnaire majoritaire)[:\s]*(.+?)(?:\n|$)",
        ]
        for pattern in parent_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                parent = match.group(1).strip()
                if len(parent) > 3:
                    result["req_parent_company"] = parent[:100]
                    break

        # Extract legal form
        legal_patterns = [
            r"(Société par actions|Personne morale|Société en nom collectif|"
            r"Société en commandite|Entreprise individuelle|Coopérative|"
            r"Organisme à but non lucratif|Corporation|Compagnie)",
        ]
        for pattern in legal_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result["req_legal_form"] = match.group(1)
                break

        return result

    except Exception as e:
        return None


def lookup_company(page, company_name):
    """Full lookup: search by name, then fetch detail of best match.

    Returns a dict with REQ data fields, or a dict with empty/None values
    if lookup fails. Never raises exceptions.
    """
    empty_result = {
        "neq": None,
        "req_status": None,
        "req_registration_date": None,
        "req_officer_name": None,
        "req_parent_company": None,
        "req_legal_form": None,
        "req_address": None,
        "req_lookup_status": "not_found",
    }

    # Check cache first
    cached = load_cached(company_name)
    if cached:
        cached["req_lookup_status"] = "cached"
        return cached

    # Search
    results = search_req(page, company_name)
    if not results:
        empty_result["req_lookup_status"] = "no_results"
        save_cache(company_name, empty_result)
        return empty_result

    # Use first result (best match by REQ relevance ranking)
    best_neq = results[0]["neq"]

    # Small delay between search and detail fetch
    time.sleep(random.uniform(2.0, 4.0))

    # Fetch detail
    detail = fetch_enterprise_detail(page, best_neq)
    if detail:
        detail["req_lookup_status"] = "found"
        save_cache(company_name, detail)
        return detail
    else:
        empty_result["neq"] = best_neq
        empty_result["req_lookup_status"] = "detail_failed"
        save_cache(company_name, empty_result)
        return empty_result
