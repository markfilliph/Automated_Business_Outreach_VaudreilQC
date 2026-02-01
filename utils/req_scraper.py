"""
REQ (Registraire des entreprises du Québec) — page interaction logic.

This module handles ONLY the Playwright page interactions:
  - Navigating to the search form
  - Submitting a company name
  - Parsing the results page for NEQ, registration date, status

It does NOT manage the browser lifecycle or retry logic.
The calling script (pipeline/04_enrich_req.py) owns the browser session
and retry loop. This keeps a single browser open across all 200 companies
instead of launching one per request.

IMPORTANT: REQ is a hostile target. Selectors WILL break when they update
their site. When that happens, open REQ in a browser, inspect the HTML,
and update the selectors in scrape_page() accordingly.
"""

import re
import time


def scrape_page(page, company_name: str) -> dict | None:
    """
    Search REQ for a company using an active Playwright page.

    Args:
        page: An active Playwright page object (caller manages lifecycle).
        company_name: The business name to search for.

    Returns:
        dict with keys: neq, registration_date, status
        None if the company is not found in REQ.

    Raises:
        RuntimeError if something unexpected happens (caller should retry).
    """
    try:
        # ── Navigate to search ──────────────────────────────────────────
        page.goto(f"https://www.registraire.gouv.qc.ca/en/recherche-entreprise/")
        page.wait_for_load_state("networkidle")

        # ── Fill search form ────────────────────────────────────────────
        # NOTE: Update this selector if REQ changes their form structure.
        search_input = page.locator('input[name="nom"]')
        if search_input.count() == 0:
            # Fallback: grab the first visible text input
            search_input = page.locator('input[type="text"]:visible').first

        search_input.wait_for(state="visible")
        search_input.clear()
        search_input.fill(company_name)

        # ── Submit ──────────────────────────────────────────────────────
        submit_btn = page.locator('button[type="submit"]')
        submit_btn.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)  # Buffer for dynamic content rendering

        # ── Check for no results ────────────────────────────────────────
        page_text = page.text_content("body") or ""
        if "Aucun résultat" in page_text or "No results" in page_text:
            return None

        # ── Parse results table ─────────────────────────────────────────
        # NOTE: Update selectors if REQ changes their results layout.
        results_rows = page.locator("table.results-table tr")
        if results_rows.count() <= 1:
            # 0 or only header row = no results
            return None

        # Click the first data row to open the detail page
        results_rows.nth(1).click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # ── Extract detail fields ───────────────────────────────────────
        detail_text = page.text_content("body") or ""

        neq = _extract_neq(detail_text)
        reg_date = _extract_field(page, "date_inscription", "Date d'inscription", "Date of registration")
        status = _extract_field(page, "statut", "Statut", "Status")

        return {
            "neq": neq,
            "registration_date": reg_date,
            "status": status,
        }

    except Exception as e:
        raise RuntimeError(f"REQ scrape failed for '{company_name}': {e}")


def _extract_neq(page_text: str) -> str | None:
    """
    Find the NEQ number in the page text.
    NEQ is always a 10-digit number. We search for it as a regex pattern
    as a fallback if structured selectors fail.
    """
    match = re.search(r"\b(\d{10})\b", page_text)
    return match.group(1) if match else None


def _extract_field(page, data_field_name: str, fr_label: str, en_label: str) -> str | None:
    """
    Try multiple selector strategies to extract a field from the REQ detail page.
    Falls back gracefully — returns None if nothing works.
    """
    # Strategy 1: data attribute selector
    el = page.locator(f'[data-field="{data_field_name}"]')
    if el.count() > 0:
        text = el.first.text_content()
        if text and text.strip():
            return text.strip()

    # Strategy 2: look for a table cell next to the label
    for label in [fr_label, en_label]:
        # Find the label, then grab the next sibling <td>
        label_el = page.locator(f'td:has-text("{label}")')
        if label_el.count() > 0:
            # The value is typically in the next <td> in the same <tr>
            row = label_el.first.locator("xpath=./following-sibling::td[1]")
            if row.count() > 0:
                text = row.first.text_content()
                if text and text.strip():
                    return text.strip()

    return None
