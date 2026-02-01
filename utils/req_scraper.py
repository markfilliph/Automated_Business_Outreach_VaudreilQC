"""
REQ (Registraire des entreprises du Québec) — page interaction logic.

This module handles ONLY the Playwright page interactions:
  - Navigating to the search form
  - Submitting a company name
  - Parsing the results page for NEQ, registration date, status

It does NOT manage the browser lifecycle or retry logic.
The calling script (05_enrich_req.py) owns the browser session
and retry loop. This keeps a single browser open across all companies
instead of launching one per request.

IMPORTANT: REQ is a hostile target. Selectors WILL break when they update
their site. When that happens, open REQ in a browser, inspect the HTML,
and update the selectors in scrape_page() accordingly.
"""

import re
import time


# ─── Selector fallback lists ─────────────────────────────────────────────────
# Multiple selectors tried in order. Add new ones at the top when REQ changes.

SEARCH_INPUT_SELECTORS = [
    'input[name="nom"]',
    'input[name="searchTerm"]',
    'input[name="q"]',
    'input[id*="search"]',
    'input[id*="nom"]',
    'input[placeholder*="nom"]',
    'input[placeholder*="name"]',
    'input[type="search"]',
    'input[type="text"]:visible',
]

SUBMIT_BUTTON_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Rechercher")',
    'button:has-text("Search")',
    'button:has-text("Chercher")',
    '.search-button',
    '#search-button',
]

RESULTS_TABLE_SELECTORS = [
    "table.results-table tr",
    "table.search-results tr",
    "table[class*='result'] tr",
    ".results-list a",
    ".search-results a",
    "table tr:has(td)",
]


def _find_element(page, selectors: list, description: str):
    """Try multiple selectors, return first match or raise."""
    for selector in selectors:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                return el
        except Exception:
            continue
    raise RuntimeError(f"Could not find {description} with any known selector")


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
        page.goto("https://www.registraire.gouv.qc.ca/en/recherche-entreprise/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)  # Extra buffer for JS rendering

        # ── Fill search form ────────────────────────────────────────────
        search_input = _find_element(page, SEARCH_INPUT_SELECTORS, "search input")
        search_input.first.wait_for(state="visible", timeout=10000)
        search_input.first.clear()
        search_input.first.fill(company_name)

        # ── Submit ──────────────────────────────────────────────────────
        submit_btn = _find_element(page, SUBMIT_BUTTON_SELECTORS, "submit button")
        submit_btn.first.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)  # Buffer for dynamic content rendering

        # ── Check for no results ────────────────────────────────────────
        page_text = page.text_content("body") or ""
        no_results_phrases = [
            "Aucun résultat",
            "No results",
            "aucune entreprise",
            "no business found",
            "0 résultat",
            "0 result",
        ]
        if any(phrase.lower() in page_text.lower() for phrase in no_results_phrases):
            return None

        # ── Parse results table ─────────────────────────────────────────
        results_found = False
        for selector in RESULTS_TABLE_SELECTORS:
            try:
                results = page.locator(selector)
                if results.count() > 1:  # More than just header
                    results.nth(1).click()
                    results_found = True
                    break
            except Exception:
                continue

        if not results_found:
            # Maybe we're already on the detail page (single result auto-redirect)
            if _extract_neq(page_text):
                pass  # Already on detail page
            else:
                return None

        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # ── Extract detail fields ───────────────────────────────────────
        detail_text = page.text_content("body") or ""

        neq = _extract_neq(detail_text)
        reg_date = _extract_date(page, detail_text)
        status = _extract_status(page, detail_text)

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
    NEQ is always a 10-digit number starting with 1 (Quebec format).
    """
    # Look for NEQ pattern: 10 digits, typically starting with 1
    patterns = [
        r"NEQ[:\s]*(\d{10})",           # "NEQ: 1234567890"
        r"NEQ[:\s]*(\d{4}\s?\d{3}\s?\d{3})",  # "NEQ: 1234 567 890"
        r"\b(1\d{9})\b",                # 10 digits starting with 1
        r"\b(\d{10})\b",                # Any 10 digits (fallback)
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            # Remove spaces from formatted NEQ
            return re.sub(r"\s", "", match.group(1))
    return None


def _extract_date(page, page_text: str) -> str | None:
    """
    Extract registration date using multiple strategies.
    """
    # Strategy 1: Structured selectors
    date_labels = [
        "Date d'inscription",
        "Date of registration",
        "Date d'immatriculation",
        "Date de constitution",
        "Incorporation date",
    ]

    for label in date_labels:
        result = _extract_field_by_label(page, label)
        if result:
            return result

    # Strategy 2: Regex patterns in page text
    date_patterns = [
        r"(?:inscription|registration|constitution)[:\s]*(\d{4}-\d{2}-\d{2})",
        r"(?:inscription|registration|constitution)[:\s]*(\d{2}/\d{2}/\d{4})",
        r"(?:inscription|registration|constitution)[:\s]*(\d{2}-\d{2}-\d{4})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def _extract_status(page, page_text: str) -> str | None:
    """
    Extract business status using multiple strategies.
    """
    # Strategy 1: Structured selectors
    status_labels = ["Statut", "Status", "État", "State"]

    for label in status_labels:
        result = _extract_field_by_label(page, label)
        if result:
            return result

    # Strategy 2: Look for common status keywords in text
    status_keywords = {
        "Immatriculée": "Active",
        "Registered": "Active",
        "Active": "Active",
        "Radiée": "Dissolved",
        "Dissolved": "Dissolved",
        "Inactive": "Inactive",
    }
    for keyword, normalized in status_keywords.items():
        if keyword.lower() in page_text.lower():
            return normalized

    return None


def _extract_field_by_label(page, label: str) -> str | None:
    """
    Try multiple selector strategies to extract a field value by its label.
    """
    try:
        # Strategy 1: data attribute
        for attr in ["data-field", "data-label", "id"]:
            el = page.locator(f'[{attr}*="{label.lower().replace(" ", "")}"]')
            if el.count() > 0:
                text = el.first.text_content()
                if text and text.strip():
                    return text.strip()

        # Strategy 2: table cell next to label (th/td pattern)
        for tag in ["th", "td", "dt", "label", "span"]:
            label_el = page.locator(f'{tag}:has-text("{label}")')
            if label_el.count() > 0:
                # Try next sibling
                for sibling in ["td", "dd", "span", "div"]:
                    row = label_el.first.locator(f"xpath=./following-sibling::{sibling}[1]")
                    if row.count() > 0:
                        text = row.first.text_content()
                        if text and text.strip():
                            return text.strip()
                # Try parent's next child
                parent = label_el.first.locator("xpath=..")
                if parent.count() > 0:
                    children = parent.locator(":scope > *")
                    for i in range(children.count()):
                        if label in (children.nth(i).text_content() or ""):
                            if i + 1 < children.count():
                                text = children.nth(i + 1).text_content()
                                if text and text.strip():
                                    return text.strip()
    except Exception:
        pass

    return None
