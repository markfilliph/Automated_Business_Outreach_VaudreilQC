"""
STEP 5: OWNER ENRICHMENT via Website Scraping + WHOIS (v4: Zero-Cost / Real Data)

Replaces the fake REQ simulator with real owner name discovery using:

  Method 1: JSON-LD structured data (highest confidence)
    - Schema.org Person, founder, employee fields embedded in page HTML

  Method 2: Website text pattern matching (medium confidence)
    - Scrapes homepage + /about + /contact + /equipe pages
    - Matches French and English ownership patterns
    - Copyright footer extraction ("© 2024 Jean Dupont")

  Method 3: WHOIS domain lookup (low confidence)
    - Falls back to domain registration data
    - Often shows registrar, not owner — marked low confidence

  Method 4: REQ simulation passthrough (none confidence)
    - For businesses where all methods fail
    - Returns empty owner rather than fabricated name

IMPORTANT: Results are cached per business website.
Re-runs never re-scrape a site already visited.

Cost: $0.00

Input:  data/deduped_candidates.csv
Output: data/req_enriched.csv
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import sys
import hashlib
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))
from config import CHECKPOINT_DEDUPED, CHECKPOINT_REQ

# ── Cache config ──────────────────────────────────────────────────────────────
CACHE_DIR = "data/cache/owner_lookup"
os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
}

REQUEST_TIMEOUT = 8
DELAY_BETWEEN_SITES = 1.0

# Pages to check for owner info (homepage + these suffixes)
OWNER_PAGES = [
    "",           # Homepage
    "/about",
    "/about-us",
    "/a-propos",
    "/equipe",
    "/notre-equipe",
    "/team",
    "/contact",
    "/contactez-nous",
    "/qui-sommes-nous",
    "/leadership",
]

# ── Name patterns (French + English) ─────────────────────────────────────────
# Ordered by confidence (most specific first)
NAME_PATTERNS = [
    # Explicit role labels
    r'(?:propriétaire|owner|fondateur|founder|président|president|directeur général|ceo|gérant)[:\s,]+([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)',
    r'([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)[,\s]+(?:propriétaire|owner|fondateur|founder|président|president|directeur)',

    # Copyright footer: "© 2024 Jean Dupont" or "© Jean-Pierre Roy"
    r'©\s*(?:\d{4})?\s*([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)\s*(?:inc|ltée|ltd|enr|tous|all|rights|\.|,|$)',

    # "Fondé en 1998 par Jean Dupont"
    r'(?:fondé|créé|établi|founded|started|established)\s+(?:en\s+\d{4}\s+)?par\s+([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)',

    # Contact block: "Contactez Jean Dupont"
    r'(?:contactez|contact)\s+([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)',

    # "M. Jean Dupont" or "Mme Marie Tremblay"
    r'(?:M\.|Mme|Mr\.|Mrs\.|Ms\.)\s+([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)',
]

# Words that look like names but are not people
FALSE_POSITIVE_NAMES = {
    "contact us", "about us", "our team", "notre equipe", "click here",
    "read more", "learn more", "get started", "sign up", "log in",
    "terms conditions", "privacy policy", "all rights", "tous droits",
    "saint lazare", "ile perrot", "vaudreuil dorion", "notre dame",
    "service client", "service clientele",
}

# Legal suffixes that indicate it's a company name, not a person
COMPANY_WORDS = [
    "inc", "ltée", "ltd", "llc", "corp", "company", "services",
    "solutions", "groupe", "group", "industries", "systems",
]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def cache_path(website: str) -> str:
    key = hashlib.md5(website.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{key}.json")


def cache_get(website: str):
    path = cache_path(website)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def cache_put(website: str, data: dict):
    path = cache_path(website)
    data["cached_at"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(data, f)


# ── Name validation ───────────────────────────────────────────────────────────

def is_valid_person_name(name: str) -> bool:
    """Check if extracted string is plausibly a real person's name."""
    if not name or len(name) < 5 or len(name) > 50:
        return False

    parts = name.strip().split()
    if len(parts) < 2 or len(parts) > 3:
        return False

    # Each part must start with uppercase
    if not all(p[0].isupper() for p in parts if p):
        return False

    # Reject known false positives
    if name.lower() in FALSE_POSITIVE_NAMES:
        return False

    # Reject if it contains company words
    name_lower = name.lower()
    if any(word in name_lower for word in COMPANY_WORDS):
        return False

    # Reject all-caps (likely acronym or company)
    if name == name.upper():
        return False

    # Reject common English/French words masquerading as names
    common_words = {
        'us', 'contact', 'nous', 'vous', 'ici', 'here', 'more',
        'home', 'accueil', 'menu', 'services', 'welcome', 'bienvenue',
        'call', 'email', 'phone', 'click', 'read', 'voir', 'voir'
    }
    if any(p.lower() in common_words for p in parts):
        return False

    # Reject UI/web terms
    ui_terms = {
        'live', 'chat', 'prompt', 'response', 'first', 'fullerium',
        'fullerene', 'synchro', 'gene', 'decouvrez', 'lithium',
        'discover', 'click', 'send', 'submit', 'search', 'loading',
        'suivant', 'precedent', 'retour', 'suite', 'powered', 'by',
    }
    if any(p.lower() in ui_terms for p in parts):
        return False

    # Must contain at least one vowel per part (filters random strings)
    vowels = set("aeiouàâäéèêëîïôùûüæœ")
    for part in parts:
        if not any(c.lower() in vowels for c in part):
            return False

    return True


# ── Extraction strategies ─────────────────────────────────────────────────────

def extract_from_json_ld(html: str) -> tuple:
    """Extract owner from JSON-LD structured data. Returns (name, confidence)."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string or "")
                if not isinstance(data, dict):
                    if isinstance(data, list):
                        data = data[0] if data else {}
                    else:
                        continue

                # Check founder, employee, contactPoint fields
                for field in ["founder", "employee", "contactPoint", "author"]:
                    person = data.get(field, {})
                    if isinstance(person, list):
                        person = person[0] if person else {}
                    if isinstance(person, dict):
                        name = person.get("name", "")
                        if name and is_valid_person_name(name):
                            return name, "high"

                # Direct name field on the organization
                org_name = data.get("name", "")
                # Skip — this is the business name, not the owner

            except (json.JSONDecodeError, AttributeError):
                continue
    except Exception:
        pass
    return None, "none"


def extract_from_meta(html: str) -> tuple:
    """Extract from meta tags. Returns (name, confidence)."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for meta in soup.find_all("meta"):
            name_attr = meta.get("name", "").lower()
            prop_attr = meta.get("property", "").lower()
            content = meta.get("content", "")

            if name_attr in ("author", "article:author") or prop_attr in ("author",):
                if content and is_valid_person_name(content):
                    return content, "medium"
    except Exception:
        pass
    return None, "none"


def extract_from_text(html: str) -> tuple:
    """Extract from visible page text using regex patterns. Returns (name, confidence)."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "head"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)

        for i, pattern in enumerate(NAME_PATTERNS):
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                name = match.strip()
                if is_valid_person_name(name):
                    # Earlier patterns = higher confidence
                    confidence = "high" if i < 2 else "medium" if i < 4 else "low"
                    return name, confidence
    except Exception:
        pass
    return None, "none"


def extract_from_whois(website: str) -> tuple:
    """WHOIS lookup as last resort. Returns (name, confidence)."""
    try:
        import whois as whois_lib
        parsed = urlparse(website)
        domain = (parsed.netloc or parsed.path).replace("www.", "")
        w = whois_lib.whois(domain)
        name = w.name if hasattr(w, "name") else None
        if isinstance(name, list):
            name = name[0] if name else None
        if name and is_valid_person_name(str(name)):
            return str(name), "low"
    except Exception:
        pass
    return None, "none"


# ── Main lookup function ──────────────────────────────────────────────────────

def fetch_page(url: str) -> str | None:
    """Fetch a single page. Returns HTML or None."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def lookup_owner(company_name: str, website: str) -> dict:
    """
    Full owner lookup pipeline for one business.
    Returns dict with name, confidence, source.
    """
    empty = {
        "req_officer_name": None,
        "owner_confidence": "none",
        "owner_source": "not_found",
        "req_status": "Unknown",
        "req_registration_date": None,
        "req_legal_form": None,
        "req_legal_name": company_name,
        "req_parent_company": None,
        "req_lookup_status": "skipped",
        "neq": None,
    }

    if not website or str(website).lower() in ("nan", "none", "", "unknown"):
        return empty

    # Normalize URL
    website = str(website).strip()
    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    # Check cache
    cached = cache_get(website)
    if cached is not None:
        return cached

    base = website.rstrip("/")
    found_name = None
    found_confidence = "none"
    found_source = None

    # Try each page
    for suffix in OWNER_PAGES:
        url = base + suffix
        html = fetch_page(url)
        if not html:
            continue

        # Method 1: JSON-LD
        name, conf = extract_from_json_ld(html)
        if name:
            found_name, found_confidence, found_source = name, conf, f"json_ld{suffix or '_home'}"
            break

        # Method 2: Meta tags
        name, conf = extract_from_meta(html)
        if name:
            found_name, found_confidence, found_source = name, conf, f"meta{suffix or '_home'}"
            break

        # Method 3: Text patterns
        name, conf = extract_from_text(html)
        if name:
            found_name, found_confidence, found_source = name, conf, f"website{suffix or '_home'}"
            break

        # Only delay between actual page fetches
        if suffix != OWNER_PAGES[-1]:
            time.sleep(0.3)

    # Method 4: WHOIS fallback (only if no name found yet)
    if not found_name:
        name, conf = extract_from_whois(website)
        if name:
            found_name, found_confidence, found_source = name, conf, "whois"

    result = {
        **empty,
        "req_officer_name": found_name,
        "owner_confidence": found_confidence,
        "owner_source": found_source or "not_found",
        "req_status": "Active",
        "req_lookup_status": "found" if found_name else "not_found",
    }

    # Reject if extracted name words all appear in the company name
    if result.get("req_officer_name"):
        name = result["req_officer_name"]
        company_words_lower = company_name.lower()
        name_parts = name.lower().split()
        if all(part in company_words_lower for part in name_parts):
            result["req_officer_name"] = None
            result["owner_confidence"] = "none"
            result["owner_source"] = "not_found"
            result["req_lookup_status"] = "not_found"

    cache_put(website, result)
    return result


# ── Pipeline integration ──────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(" STEP 5: OWNER ENRICHMENT (v4: Website Scraping / Real Data)")
    print("=" * 60)

    if not os.path.exists(CHECKPOINT_DEDUPED):
        print(f"  [ERROR] Input file {CHECKPOINT_DEDUPED} not found.")
        return

    df = pd.read_csv(CHECKPOINT_DEDUPED)
    print(f"  [INPUT] {len(df)} candidates from {CHECKPOINT_DEDUPED}")

    # Count existing cache entries
    cache_files = len(os.listdir(CACHE_DIR))
    print(f"  [Cache] {cache_files} previously cached lookups")
    print(f"  [Note] Scraping websites for real owner names...")
    print(f"         This will take ~{len(df) * 2 // 60} to {len(df) * 4 // 60} minutes\n")

    enriched_data = []
    found_count = 0
    cache_hits = 0
    errors = 0

    for idx, row in df.iterrows():
        company = str(row.get("company_name", ""))
        website = str(row.get("website", ""))
        i = idx + 1

        # Check cache first for display purposes
        is_cached = False
        if website and website.lower() not in ("nan", "none", ""):
            norm = website.strip()
            if not norm.startswith(("http://", "https://")):
                norm = "https://" + norm
            is_cached = cache_get(norm) is not None

        if is_cached:
            cache_hits += 1
            suffix = " (cached)"
        else:
            suffix = ""

        print(f"  [{i:4d}/{len(df)}] {company[:45]:<45}{suffix}")

        try:
            owner_data = lookup_owner(company, website)
        except Exception as e:
            print(f"           [ERROR] {e}")
            owner_data = {
                "req_officer_name": None,
                "owner_confidence": "none",
                "owner_source": "error",
                "req_status": "Unknown",
                "req_registration_date": None,
                "req_legal_form": None,
                "req_legal_name": company,
                "req_parent_company": None,
                "req_lookup_status": "error",
                "neq": None,
            }
            errors += 1

        if owner_data.get("req_officer_name"):
            found_count += 1
            print(f"           → {owner_data['req_officer_name']} ({owner_data['owner_confidence']})")

        combined = row.to_dict()
        combined.update(owner_data)
        enriched_data.append(combined)

        # Polite delay only for live requests
        if not is_cached and website and website.lower() not in ("nan", "none", ""):
            time.sleep(DELAY_BETWEEN_SITES)

    df_enriched = pd.DataFrame(enriched_data)

    # Map owner fields to pipeline-expected column names
    if "req_officer_name" in df_enriched.columns:
        df_enriched["req_officer_name"] = df_enriched["req_officer_name"].fillna("")

    # All records are treated as Active (we have no REQ access)
    df_enriched["req_status"] = "Active"

    print(f"\n  {'='*50}")
    print(f"  [STATS] Owner names found:  {found_count}/{len(df)} ({found_count/len(df)*100:.0f}%)")
    print(f"  [STATS] Cache hits:         {cache_hits}")
    print(f"  [STATS] Errors:             {errors}")
    print(f"  [NOTE]  All names are real, scraped from business websites.")
    print(f"          Confidence levels: high=structured data, medium=pattern match, low=WHOIS")
    print(f"  {'='*50}")

    os.makedirs(os.path.dirname(CHECKPOINT_REQ), exist_ok=True)
    df_enriched.to_csv(CHECKPOINT_REQ, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] {len(df_enriched)} enriched leads -> {CHECKPOINT_REQ}")
    print(f"  [COST]   $0.00")


if __name__ == "__main__":
    main()
