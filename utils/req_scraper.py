"""
REQ Scraper — Registraire des entreprises du Québec (REAL VERSION)

Playwright-based scraper for the Quebec enterprise registry. Extracts:
  - NEQ number (unique enterprise identifier)
  - Registration date (critical for years-in-business scoring)
  - Officer/dirigeant name(s) (ownership identification)
  - Business status (active/inactive/struck off)
  - Legal form (inc., ltée, enr., SENC, etc.)

The REQ site structure:
  Search: https://www.registreentreprises.gouv.qc.ca/RQEntrepriseGREff/GR/GR03/GR03A2_19A_PIU_RechsijNom_PC/PageEcran.aspx
  Results: Server-rendered HTML table
  Detail page: Contains full enterprise info including administrators

Anti-blocking strategy:
  - 2-4 second random delays between requests
  - Human-like viewport and user agent
  - Session cookies maintained via Playwright context
  - No concurrent requests; sequential processing only
"""

import json
import os
import re
import time
import random
from datetime import datetime
from typing import Optional, Tuple

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
        headless=False,  # Visible browser required to bypass Cloudflare
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
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


def get_cache_path(company_name: str) -> str:
    """Generate cache file path for a company."""
    import hashlib
    safe_name = hashlib.md5(company_name.lower().strip().encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"req_{safe_name}.json")


def load_cached(company_name: str) -> Optional[dict]:
    """Load cached REQ data for a company, if available and fresh."""
    path = get_cache_path(company_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Check cache age (7 day TTL)
                cached_at = data.get("cached_at", "")
                if cached_at:
                    try:
                        age = (datetime.now() - datetime.fromisoformat(cached_at)).days
                        if age <= 7:
                            return data
                    except ValueError:
                        pass
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def save_cache(company_name: str, data: dict):
    """Save REQ data to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    data["cached_at"] = datetime.now().isoformat()
    path = get_cache_path(company_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_company_name_for_search(name: str) -> str:
    """Clean company name for REQ search.

    The REQ search works best with the core name without
    common suffixes that may vary in registration vs. trade name.
    """
    name = name.strip()
    # Remove common suffixes
    suffixes = [
        r"\s+inc\.?$", r"\s+ltée\.?$", r"\s+ltee\.?$", r"\s+ltd\.?$",
        r"\s+enr\.?$", r"\s+s\.?e\.?n\.?c\.?$", r"\s+senc$",
        r"\s+corp\.?$", r"\s+cie\.?$", r"\s+co\.?$",
    ]
    name_lower = name.lower()
    for suffix in suffixes:
        name = re.sub(suffix, "", name, flags=re.IGNORECASE)
    return name.strip()


def search_req(page, company_name: str, timeout_ms: int = 30000) -> list:
    """Search the REQ for a company by name.

    Returns a list of search result dicts with NEQ and name.
    """
    # Correct URL for REQ search (note the .MVC extension)
    search_url = "https://www.registreentreprises.gouv.qc.ca/REQNA/GR/GR03/GR03A71.RechercheRegistre.MVC/GR03A71"
    clean_name = clean_company_name_for_search(company_name)

    try:
        page.goto(search_url, timeout=timeout_ms, wait_until="domcontentloaded")
        time.sleep(random.uniform(1.5, 2.5))

        # STEP 1: Check the terms of service checkbox (REQUIRED before search)
        # The checkbox text: "Je reconnais avoir lu, compris et accepté les conditions d'utilisation..."
        terms_checkbox_selectors = [
            'input[type="checkbox"]',
            'input[id*="conditions"]',
            'input[id*="Conditions"]',
            'input[name*="conditions"]',
            'input[name*="Conditions"]',
            '#ChkConditions',
            'input[id="ChkConditions"]',
        ]

        checkbox_checked = False
        for selector in terms_checkbox_selectors:
            try:
                checkbox = page.locator(selector).first
                if checkbox.is_visible():
                    # Check if not already checked
                    if not checkbox.is_checked():
                        checkbox.check()
                    checkbox_checked = True
                    break
            except Exception:
                continue

        # If we couldn't find a specific checkbox, try clicking any visible checkbox
        if not checkbox_checked:
            try:
                all_checkboxes = page.locator('input[type="checkbox"]').all()
                for cb in all_checkboxes:
                    if cb.is_visible():
                        if not cb.is_checked():
                            cb.check()
                        checkbox_checked = True
                        break
            except Exception:
                pass

        time.sleep(random.uniform(0.3, 0.6))

        # STEP 2: Find and fill the search input
        # The REQ search page has input id="Objet" for company name
        search_selectors = [
            '#Objet',
            'input[id="Objet"]',
            'input[name="Objet"]',
            'input[name*="NomEntreprise"]',
            'input[id*="NomEntreprise"]',
            'input[type="text"]',
        ]

        search_input = None
        for selector in search_selectors:
            try:
                search_input = page.locator(selector).first
                if search_input.is_visible():
                    break
            except Exception:
                continue

        if not search_input:
            return []

        search_input.fill(clean_name)
        time.sleep(random.uniform(0.5, 1.0))

        # STEP 3: Find and click submit button ("Consulter")
        submit_selectors = [
            'input[value="Consulter"]',
            'button:has-text("Consulter")',
            'input[type="submit"]',
            'button[type="submit"]',
            'input[value*="Rechercher"]',
            'a[id*="Rechercher"]',
            '#BtnConsulter',
        ]

        for selector in submit_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible():
                    btn.click()
                    break
            except Exception:
                continue

        # Wait for results
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        time.sleep(random.uniform(2.0, 3.0))

        # Parse search results
        results = []

        # Look for result table rows
        try:
            # REQ typically shows results in a table or grid
            rows = page.locator("table tr, .resultRow, [id*='Result']").all()

            for row in rows[:10]:  # Cap at 10 results
                text = row.inner_text()
                # Extract NEQ (10-digit number starting with 11)
                neq_match = re.search(r'\b(11\d{8})\b', text)
                if neq_match:
                    results.append({
                        "neq": neq_match.group(1),
                        "raw_text": text.strip()[:300],
                    })
        except Exception:
            pass

        # Alternative: look for links containing NEQ
        if not results:
            try:
                links = page.locator("a[href*='NEQ']").all()
                for link in links[:10]:
                    href = link.get_attribute("href") or ""
                    text = link.inner_text()
                    neq_match = re.search(r'(11\d{8})', href + text)
                    if neq_match:
                        results.append({
                            "neq": neq_match.group(1),
                            "raw_text": text.strip()[:300],
                        })
            except Exception:
                pass

        return results

    except Exception as e:
        return []


def fetch_enterprise_detail(page, neq: str, timeout_ms: int = 30000) -> Optional[dict]:
    """Fetch detailed enterprise info from REQ by NEQ number.

    Returns a dict with registration_date, officer_name, status, legal_form.
    """
    # Direct URL to enterprise detail page
    detail_url = f"https://www.registreentreprises.gouv.qc.ca/RQEntrepriseGREff/GR/GR03/GR03A2_19A_PIU_RecijNEQ_PC/PageEcran.aspx?NEQ={neq}"

    try:
        page.goto(detail_url, timeout=timeout_ms, wait_until="domcontentloaded")
        time.sleep(random.uniform(2.0, 3.5))

        # Get page text for parsing
        body_text = page.inner_text("body")
        html_content = page.content()

        result = {
            "neq": neq,
            "req_status": None,
            "req_registration_date": None,
            "req_officer_name": None,
            "req_legal_name": None,
            "req_legal_form": None,
            "req_address": None,
        }

        # Extract registration date
        # Look for patterns like "2005-03-15" or "15 mars 2005"
        date_patterns = [
            r"(?:Date[^:]*constitution|Constitu[ée]+ le|Date d'immatriculation)[^\d]*(\d{4}-\d{2}-\d{2})",
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result["req_registration_date"] = match.group(1)
                break

        # Extract status
        status_patterns = [
            r"(Immatriculée|Radiée|Dissoute|En défaut|Fermée|Active)",
        ]
        for pattern in status_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                status = match.group(1)
                # Normalize status
                if status.lower() in ("immatriculée", "active"):
                    result["req_status"] = "Active"
                elif "radié" in status.lower():
                    result["req_status"] = "Radiée"
                elif "dissout" in status.lower():
                    result["req_status"] = "Dissoute"
                else:
                    result["req_status"] = status
                break

        # Extract legal name
        name_patterns = [
            r"Nom de l'entreprise[^\n]*\n\s*([^\n]+)",
            r"Dénomination sociale[^\n]*\n\s*([^\n]+)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result["req_legal_name"] = match.group(1).strip()
                break

        # Extract legal form
        form_patterns = [
            r"(Société par actions|Personne morale|Société en nom collectif|"
            r"Société en commandite|Entreprise individuelle|Coopérative|"
            r"Compagnie|Corporation)",
        ]
        for pattern in form_patterns:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result["req_legal_form"] = match.group(1)
                break

        # Extract officers/administrators - THIS IS THE KEY DATA
        # Look for "Administrateur" or "Dirigeant" sections
        officer_names = []

        # Pattern 1: Look for names after "Administrateur" headers
        admin_section = re.search(
            r"(?:Administrateur|Dirigeant|Actionnaire|Président)[s]?[^\n]*\n((?:[^\n]+\n){1,10})",
            body_text, re.IGNORECASE
        )
        if admin_section:
            section_text = admin_section.group(1)
            # Look for name patterns (First Last or LAST, First)
            name_matches = re.findall(
                r"([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][a-zàâäéèêëïîôùûüç]+(?:\s+[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][a-zàâäéèêëïîôùûüç]+){1,3})",
                section_text
            )
            for name in name_matches:
                # Filter out common false positives
                if len(name) > 5 and name.lower() not in ("québec", "canada", "montréal", "vaudreuil"):
                    officer_names.append(name)
                    if len(officer_names) >= 3:
                        break

        # Pattern 2: Look in table cells
        if not officer_names:
            try:
                cells = page.locator("td").all()
                for cell in cells:
                    text = cell.inner_text().strip()
                    # Check if it looks like a person name (2-4 capitalized words)
                    if re.match(r'^[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][a-zàâäéèêëïîôùûüç]+(\s+[A-ZÀÂÄÉÈÊËÏÎÔÙÛÜÇ][a-zàâäéèêëïîôùûüç]+){1,3}$', text):
                        if len(text) > 5 and text.lower() not in ("québec", "canada"):
                            officer_names.append(text)
                            if len(officer_names) >= 3:
                                break
            except Exception:
                pass

        if officer_names:
            result["req_officer_name"] = officer_names[0]  # Primary officer
            if len(officer_names) > 1:
                result["req_additional_officers"] = officer_names[1:]

        return result

    except Exception as e:
        return None


def lookup_company(page, company_name: str) -> dict:
    """Full lookup: search by name, then fetch detail of best match.

    Returns a dict with REQ data fields, or a dict with empty/None values
    if lookup fails. Never raises exceptions.
    """
    empty_result = {
        "neq": None,
        "req_status": None,
        "req_registration_date": None,
        "req_officer_name": None,
        "req_legal_name": None,
        "req_legal_form": None,
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

    # Use first result (best match by REQ relevance)
    best_neq = results[0]["neq"]

    # Small delay between search and detail fetch
    time.sleep(random.uniform(2.0, 3.5))

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
