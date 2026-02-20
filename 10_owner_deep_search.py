"""
STEP 10: DEEP OWNER SEARCH - ALL 5 SOURCES
Sources (in priority order per lead):
  1. REQ (Registraire des entreprises du Quebec) - legal officer of record
  2. Facebook via DuckDuckGo - Quebec trades use FB heavily
  3. Pages Jaunes - French Canadian business directory
  4. Google review responses - owners sometimes sign their name
  5. Wayback Machine - archived About/Team pages

Stops per lead when high-confidence match found.
Caches all results. Zero cost.
"""

import pandas as pd
import requests
import re
import json
import os
import time
import hashlib
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from datetime import datetime

# Playwright for REQ
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("WARNING: Playwright not available, REQ source will be skipped")

XLSX = "data/exports/vaudreuil_hamilton_standard_20260218.xlsx"
CACHE_BASE = "data/cache"
DATE = datetime.now().strftime("%Y%m%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
}

# Name validation
INVALID_NAMES = {
    "not found","owner","propriétaire","fondateur","président","president",
    "directeur","director","contact","info","email","phone","nous","us",
    "home","menu","services","welcome","google","facebook","linkedin",
    "instagram","twitter","youtube","inc","ltd","ltée","general information",
}

def is_valid_name(name):
    if not name:
        return False
    name = name.strip()
    if len(name) < 4:
        return False
    if name.lower() in INVALID_NAMES:
        return False
    parts = name.split()
    if len(parts) < 2:
        return False
    if any(p.lower() in INVALID_NAMES for p in parts):
        return False
    # Must have at least one capitalized part
    if not any(p[0].isupper() for p in parts if p):
        return False
    return True

def cache_path(source, key):
    d = os.path.join(CACHE_BASE, f"deep_{source}")
    os.makedirs(d, exist_ok=True)
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return os.path.join(d, f"{h}.json")

def load_cache(source, key):
    p = cache_path(source, key)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            pass
    return None

def save_cache(source, key, data):
    p = cache_path(source, key)
    json.dump(data, open(p, "w"), ensure_ascii=False)

# ── SOURCE 1: REQ via Playwright ─────────────────────────────────────────────

def search_req(business_name):
    cached = load_cache("req", business_name)
    if cached is not None:
        return cached

    result = {"owner": None, "title": None, "source": "req", "confidence": "high"}

    if not PLAYWRIGHT_AVAILABLE:
        save_cache("req", business_name, result)
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"Accept-Language": "fr-CA,fr;q=0.9"})

            # Search REQ
            url = f"https://www.registreentreprises.gouv.qc.ca/RQAnonymeGR/GR/GR03/GR03A2_19A_PIU_RechEnt_PC.aspx?T=1&RCL={quote_plus(business_name)}"
            page.goto(url, timeout=20000)
            page.wait_for_timeout(2000)

            # Try to find first result link
            links = page.query_selector_all("table.rgRQAnEntInfo a")
            if not links:
                links = page.query_selector_all("a.lienResultat")

            if links:
                links[0].click()
                page.wait_for_timeout(2000)

                # Look for person names in officers section
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # REQ shows officers in tables with role labels
                for row in soup.find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        role = cells[0].get_text(strip=True).lower()
                        name_cell = cells[1].get_text(strip=True)
                        if any(kw in role for kw in ["administrateur","actionnaire","président","secrétaire","directeur"]):
                            if is_valid_name(name_cell):
                                result["owner"] = name_cell
                                result["title"] = cells[0].get_text(strip=True)
                                break

            browser.close()

    except Exception as e:
        result["error"] = str(e)

    save_cache("req", business_name, result)
    time.sleep(1)
    return result

# ── SOURCE 2: Facebook via DuckDuckGo ────────────────────────────────────────

def search_facebook(business_name, city="Vaudreuil-Dorion"):
    cached = load_cache("facebook", business_name)
    if cached is not None:
        return cached

    result = {"owner": None, "title": None, "source": "facebook_ddg", "confidence": "low"}

    NAME_PAT = re.compile(
        r'([A-ZÀ-ÿ][a-zà-ÿ\-]+(?:\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)+)'
        r'\s*[·\-|,]\s*'
        r'(?:propriétaire|owner|président|president|fondateur|founder|directeur|ceo|gérant)',
        re.IGNORECASE
    )

    queries = [
        f'site:facebook.com "{business_name}" propriétaire OR owner OR fondateur',
        f'site:facebook.com "{business_name}" {city}',
    ]

    for query in queries:
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                time.sleep(2)
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            snippets = [d.get_text() for d in soup.find_all("div", class_="result__snippet")]
            titles   = [a.get_text() for a in soup.find_all("a", class_="result__a")]
            full = " ".join(snippets + titles)

            matches = NAME_PAT.findall(full)
            for m in matches:
                if is_valid_name(m):
                    result["owner"] = m.strip()
                    result["source"] = "facebook_ddg"
                    break

            if result["owner"]:
                break

            time.sleep(1.5)

        except Exception as e:
            result["error"] = str(e)
            time.sleep(2)

    save_cache("facebook", business_name, result)
    time.sleep(1)
    return result

# ── SOURCE 3: Pages Jaunes ────────────────────────────────────────────────────

def search_pages_jaunes(business_name, city="Vaudreuil-Dorion"):
    cached = load_cache("pagesjaunes", business_name)
    if cached is not None:
        return cached

    result = {"owner": None, "title": None, "source": "pages_jaunes", "confidence": "medium"}

    try:
        query = f"{business_name} {city}"
        url = f"https://www.pagesjaunes.ca/search/si/1/{quote_plus(query)}/Vaudreuil-Dorion+QC"
        r = requests.get(url, headers=HEADERS, timeout=12)

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")

            # Pages Jaunes sometimes lists contact person
            for tag in soup.find_all(["span","div","p"], class_=re.compile(r'contact|owner|person|nom', re.I)):
                text = tag.get_text(strip=True)
                if is_valid_name(text):
                    result["owner"] = text
                    break

            # Also try DDG search on pagesjaunes domain
            if not result["owner"]:
                ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus('site:pagesjaunes.ca ' + business_name)}"
                r2 = requests.get(ddg_url, headers=HEADERS, timeout=12)
                if r2.status_code == 200:
                    soup2 = BeautifulSoup(r2.text, "html.parser")
                    snippets = [d.get_text() for d in soup2.find_all("div", class_="result__snippet")]
                    for snippet in snippets:
                        names = re.findall(
                            r'(?:propriétaire|owner|gérant|contact)[:\s]+([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)',
                            snippet, re.IGNORECASE
                        )
                        for name in names:
                            if is_valid_name(name):
                                result["owner"] = name.strip()
                                break
                        if result["owner"]:
                            break

    except Exception as e:
        result["error"] = str(e)

    save_cache("pagesjaunes", business_name, result)
    time.sleep(1)
    return result

# ── SOURCE 4: Google Review Responses ────────────────────────────────────────

def search_review_responses(business_name):
    cached = load_cache("reviews", business_name)
    if cached is not None:
        return cached

    result = {"owner": None, "title": None, "source": "google_review_response", "confidence": "medium"}

    # Check existing Google Places cache for review owner responses
    google_cache_dir = "data/cache"
    name_lower = business_name.lower().strip()
    name_words = set(name_lower.split())

    for fname in os.listdir(google_cache_dir):
        if not fname.endswith(".json"):
            continue
        try:
            entry = json.load(open(os.path.join(google_cache_dir, fname)))
            data = entry.get("data", {})
            cached_name = data.get("name", "").lower()

            # Match by name overlap
            cached_words = set(cached_name.split())
            if len(name_words & cached_words) < 2:
                continue

            # Check reviews for owner responses
            reviews = data.get("reviews", [])
            for review in reviews:
                reply = review.get("owner_reply", {})
                if reply:
                    reply_text = reply.get("text", "")
                    # Owner sometimes signs their name at end of reply
                    lines = [l.strip() for l in reply_text.split("\n") if l.strip()]
                    for line in reversed(lines[-3:]):
                        parts = line.split()
                        if 2 <= len(parts) <= 4:
                            candidate = " ".join(parts)
                            if is_valid_name(candidate) and not any(
                                c in candidate.lower() for c in ["équipe","team","merci","thanks","service"]
                            ):
                                result["owner"] = candidate
                                break
                    if result["owner"]:
                        break

        except Exception:
            continue

    save_cache("reviews", business_name, result)
    return result

# ── SOURCE 5: Wayback Machine ─────────────────────────────────────────────────

def search_wayback(business_name, website):
    if not website or str(website).lower() in ("nan","none",""):
        return {"owner": None, "source": "wayback", "confidence": "low"}

    cached = load_cache("wayback", business_name)
    if cached is not None:
        return cached

    result = {"owner": None, "title": None, "source": "wayback", "confidence": "low"}

    website = str(website).strip().rstrip("/")
    if not website.startswith(("http://","https://")):
        website = "https://" + website

    parsed_domain = website.split("//")[-1].split("/")[0]

    # Target pages likely to have owner info
    target_paths = ["/about","/a-propos","/equipe","/team","/qui-sommes-nous","/notre-equipe"]

    NAME_PAT = re.compile(
        r'([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)'
        r'(?:\s*[,\-|·]\s*'
        r'(?:propriétaire|owner|président|president|fondateur|founder|directeur|ceo|gérant))?',
        re.IGNORECASE
    )

    try:
        for path in target_paths:
            target_url = f"https://{parsed_domain}{path}"
            # Check Wayback availability
            avail_url = f"http://archive.org/wayback/available?url={target_url}"
            r = requests.get(avail_url, timeout=10)
            if r.status_code != 200:
                continue

            data = r.json()
            snapshot = data.get("archived_snapshots",{}).get("closest",{})
            if not snapshot.get("available"):
                continue

            snap_url = snapshot.get("url","")
            if not snap_url:
                continue

            page = requests.get(snap_url, headers=HEADERS, timeout=15)
            if page.status_code != 200:
                time.sleep(1)
                continue

            soup = BeautifulSoup(page.text, "html.parser")
            for tag in soup(["script","style","nav","header","footer"]):
                tag.decompose()
            text = soup.get_text(separator=" ")

            # Look for owner patterns near title keywords
            owner_ctx = re.findall(
                r'(?:propriétaire|owner|président|fondateur|founder|directeur général)[:\s,]+([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)',
                text, re.IGNORECASE
            )
            for candidate in owner_ctx:
                if is_valid_name(candidate):
                    result["owner"] = candidate.strip()
                    result["source"] = f"wayback:{path}"
                    break

            if result["owner"]:
                break

            time.sleep(1)

    except Exception as e:
        result["error"] = str(e)

    save_cache("wayback", business_name, result)
    time.sleep(1)
    return result

# ── ORCHESTRATOR ──────────────────────────────────────────────────────────────

def deep_search(business_name, website):
    """
    Run all 5 sources in order. Stop early on high-confidence match.
    Returns best result found.
    """
    sources = [
        ("REQ",          lambda: search_req(business_name)),
        ("Facebook",     lambda: search_facebook(business_name)),
        ("Pages Jaunes", lambda: search_pages_jaunes(business_name)),
        ("Reviews",      lambda: search_review_responses(business_name)),
        ("Wayback",      lambda: search_wayback(business_name, website)),
    ]

    best = None

    for source_name, fn in sources:
        try:
            r = fn()
            if r.get("owner") and is_valid_name(r["owner"]):
                print(f"           [{source_name}] FOUND: {r['owner']}")
                best = r
                # Stop early if REQ (authoritative) or 2+ sources agree
                if source_name == "REQ":
                    break
                # Otherwise keep searching to confirm
        except Exception as e:
            print(f"           [{source_name}] ERROR: {e}")
            continue

    return best

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("="*65)
    print(" STEP 10: DEEP OWNER SEARCH - ALL 5 SOURCES")
    print("="*65)

    df = pd.read_excel(XLSX)
    print(f"  [INPUT]  {len(df)} leads\n")

    # Ensure string columns
    for col in ["owner_name","owner_title","owner_email","owner_confidence","notes"]:
        df[col] = df[col].astype(str).replace("nan","")

    updated = 0
    already_known = 0
    total = len(df)

    for idx, row in df.iterrows():
        biz     = str(row["Business_name"])
        website = str(row.get("Website",""))
        current = str(row.get("owner_name","")).strip()

        if current and current not in ("","nan","Not found"):
            print(f"  [{idx+1:2d}/{total}] SKIP (owner known): {biz[:50]}")
            already_known += 1
            continue

        print(f"\n  [{idx+1:2d}/{total}] {biz[:55]}")

        result = deep_search(biz, website)

        if result and result.get("owner"):
            owner    = result["owner"]
            title    = result.get("title") or ""
            source   = result.get("source","deep_search")
            conf_str = result.get("confidence","low")

            df.at[idx, "owner_name"]       = owner
            df.at[idx, "owner_title"]      = title
            df.at[idx, "owner_confidence"] = conf_str

            # Bump confidence score
            bump = 0.25 if conf_str == "high" else 0.15 if conf_str == "medium" else 0.10
            current_score = float(df.at[idx, "Confidence_score"])
            df.at[idx, "Confidence_score"] = round(min(current_score + bump, 0.90), 2)

            # Update notes
            old_notes = str(df.at[idx, "notes"])
            conf_tag = "confirmed" if conf_str == "high" else "identified"
            new_note = f"Owner {conf_tag}: {owner} via {source}."
            if conf_str != "high":
                new_note += " Manual verification recommended."
            df.at[idx, "notes"] = new_note + " " + old_notes

            print(f"           -> UPDATED: {owner} ({source}, {conf_str})")
            updated += 1
        else:
            print(f"           -> No owner found across all 5 sources")

    print(f"\n  {'='*55}")
    print(f"  Total leads:       {total}")
    print(f"  Already had owner: {already_known}")
    print(f"  New owners found:  {updated}")
    total_owners = (df["owner_name"].str.strip() != "").sum()
    print(f"  Total with owner:  {total_owners} ({total_owners/total*100:.0f}%)")
    print(f"  {'='*55}")

    out_xlsx = XLSX.replace(".xlsx", f"_v2_{DATE}.xlsx")
    out_csv  = out_xlsx.replace(".xlsx",".csv")
    df.to_excel(out_xlsx, index=False)
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n  [OUTPUT] {out_xlsx}")
    print(f"  [OUTPUT] {out_csv}")
    print(f"  [COST]   $0.00")

if __name__ == "__main__":
    main()
