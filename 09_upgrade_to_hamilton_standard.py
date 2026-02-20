
import pandas as pd, requests, re, json, os, time, hashlib
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse, quote_plus

INPUT_FILE  = "data/top_75_for_review.csv"
CACHE_DIR   = "data/cache"
DDG_CACHE   = "data/cache/ddg_verification"
OUTPUT_DIR  = "data/exports"
DATE_STAMP  = datetime.now().strftime("%Y%m%d")

os.makedirs(DDG_CACHE, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
}

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
SKIP_EMAIL_DOMAINS = {"example.com","domain.com","email.com","sentry.io","wixpress.com","squarespace.com","wordpress.com"}
SKIP_EMAIL_PREFIXES = {"noreply","no-reply","donotreply","support","admin","webmaster","postmaster","bounce","unsubscribe"}
TITLE_KEYWORDS = ["président","president","owner","propriétaire","fondateur","founder","directeur général","ceo","gérant","director","principal","manager"]

def load_google_cache():
    index = {}
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CACHE_DIR, fname)) as f:
                entry = json.load(f)
            data = entry.get("data", {})
            name = data.get("name", "")
            if name:
                index[name.lower().strip()] = data
            query = entry.get("query", "")
            if query:
                biz_name = query.split(",")[0].strip().lower()
                if biz_name:
                    index[biz_name] = data
        except Exception:
            continue
    return index

def get_google_data(business_name, cache_index):
    name_lower = business_name.lower().strip()
    if name_lower in cache_index:
        e = cache_index[name_lower]
        return {"google_rating": e.get("rating"), "google_reviews": e.get("user_ratings_total")}
    best_match = None
    best_score = 0
    name_words = set(name_lower.split())
    for cached_name, data in cache_index.items():
        overlap = len(name_words & set(cached_name.split()))
        if overlap > best_score and overlap >= 2:
            best_score = overlap
            best_match = data
    if best_match:
        return {"google_rating": best_match.get("rating"), "google_reviews": best_match.get("user_ratings_total")}
    return {"google_rating": None, "google_reviews": None}

def is_valid_email(email, domain):
    if not email or "@" not in email:
        return False
    local, at_domain = email.lower().split("@", 1)
    return at_domain not in SKIP_EMAIL_DOMAINS and local not in SKIP_EMAIL_PREFIXES

def extract_email_from_page(html, business_domain):
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if is_valid_email(email, business_domain):
                return email
    for email in EMAIL_PATTERN.findall(soup.get_text()):
        if is_valid_email(email, business_domain):
            return email
    return None

def get_business_email(website):
    if not website or str(website).lower() in ("nan","none",""):
        return None
    website = str(website).strip()
    if not website.startswith(("http://","https://")):
        website = "https://" + website
    parsed = urlparse(website)
    domain = parsed.netloc.replace("www.","")
    base = website.rstrip("/")
    for url in [base, base+"/contact", base+"/contactez-nous", base+"/a-propos"]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code == 200:
                email = extract_email_from_page(r.text, domain)
                if email:
                    return email
            time.sleep(0.3)
        except Exception:
            continue
    return None

def extract_owner_title(website, owner_name):
    if not website or not owner_name or owner_name == "Not found":
        return None
    website = str(website).strip()
    if not website.startswith(("http://","https://")):
        website = "https://" + website
    first_name = owner_name.split()[0].lower() if owner_name else ""
    for url in [website.rstrip("/"), website.rstrip("/")+"/about", website.rstrip("/")+"/a-propos"]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script","style","nav"]):
                tag.decompose()
            text = soup.get_text(separator=" ")
            idx = text.lower().find(first_name)
            if idx >= 0:
                context = text[max(0,idx-50):idx+100].lower()
                for kw in TITLE_KEYWORDS:
                    if kw in context:
                        return kw.title()
            time.sleep(0.3)
        except Exception:
            continue
    return None

def ddg_cache_path(business_name):
    key = hashlib.md5(business_name.encode()).hexdigest()[:12]
    return os.path.join(DDG_CACHE, f"{key}.json")

def ddg_verify_owner(business_name, existing_owner):
    cache_path = ddg_cache_path(business_name)
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    result = {"ddg_owner": None, "ddg_confirmed": False, "ddg_source": None}
    try:
        query = f'"{business_name}" propriétaire OR owner OR fondateur OR président'
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            snippets = [d.get_text() for d in soup.find_all("div", class_="result__snippet")]
            full_text = " ".join(snippets)
            if existing_owner and existing_owner != "Not found":
                last_name = existing_owner.split()[-1].lower()
                if last_name and last_name in full_text.lower():
                    result["ddg_confirmed"] = True
                    result["ddg_source"] = "duckduckgo_search"
            if not existing_owner or existing_owner == "Not found":
                pattern = re.compile(r'(?:owner|propriétaire|fondateur|président|president)[:\s,]+([A-ZÀ-ÿ][a-zà-ÿ\-]+\s+[A-ZÀ-ÿ][a-zà-ÿ\-]+)', re.IGNORECASE)
                matches = pattern.findall(full_text)
                if matches:
                    result["ddg_owner"] = matches[0].strip()
                    result["ddg_source"] = "duckduckgo_search"
        time.sleep(1.5)
    except Exception as e:
        result["error"] = str(e)
    with open(cache_path, "w") as f:
        json.dump(result, f)
    return result

def calculate_confidence_score(row, ddg_result):
    score = 0.0
    owner = str(row.get("owner_name","")).strip()
    has_owner = owner and owner != "Not found"
    if has_owner and ddg_result.get("ddg_confirmed"):
        score += 0.35
    elif has_owner:
        score += 0.20
    if row.get("phone") and str(row.get("phone","")).strip() not in ("","nan"):
        score += 0.15
    if row.get("website") and str(row.get("website","")).strip() not in ("","nan"):
        score += 0.10
    if row.get("google_reviews") and str(row.get("google_reviews","")) not in ("","nan","None"):
        score += 0.10
    try:
        if row.get("google_rating") and float(row.get("google_rating")) >= 4.0:
            score += 0.05
    except Exception:
        pass
    if row.get("owner_email") and str(row.get("owner_email","")).strip() not in ("","nan"):
        score += 0.10
    age = str(row.get("age_range_estimate",""))
    if "30+" in age:
        score += 0.10
    elif "20" in age or "15" in age:
        score += 0.05
    return round(min(score, 1.0), 2)

def build_notes(row, ddg_result):
    parts = []
    owner = str(row.get("owner_name","")).strip()
    if owner and owner != "Not found":
        source = str(row.get("owner_source","")).strip()
        ddg_tag = " (confirmed via web search)" if ddg_result.get("ddg_confirmed") else ""
        parts.append(f"Owner identified: {owner} via {source}{ddg_tag}.")
    else:
        ddg_owner = ddg_result.get("ddg_owner")
        if ddg_owner:
            parts.append(f"Potential owner via web search: {ddg_owner} (unverified; manual confirmation required).")
        else:
            parts.append("Owner not publicly listed; manual LinkedIn research required.")
    rating = row.get("google_rating")
    reviews = row.get("google_reviews")
    if rating or reviews:
        g = "Google:"
        if rating: g += f" {rating} stars"
        if reviews: g += f", {reviews} reviews"
        parts.append(g + ".")
    age = str(row.get("age_range_estimate","")).strip()
    if age and age != "nan":
        parts.append(f"Est. {age} in operation.")
    cat = str(row.get("category_standardized","")).strip()
    if cat:
        parts.append(f"Sector: {cat}.")
    if "Strong independent ownership" in str(row.get("important_notes","")):
        parts.append("Strong independent ownership signals.")
    return " ".join(parts)

def main():
    print("="*65)
    print(" STEP 9: UPGRADE TO HAMILTON STANDARD")
    print("="*65)
    df = pd.read_csv(INPUT_FILE)
    print(f"  [INPUT]  {len(df)} leads")
    print("  [1/5] Loading Google cache...")
    google_index = load_google_cache()
    print(f"         Indexed {len(google_index)} cache entries")
    results = []
    total = len(df)
    for idx, row in df.iterrows():
        i = idx + 1
        biz = str(row.get("business_name",""))
        website = str(row.get("website",""))
        owner = str(row.get("owner_name",""))
        print(f"\n  [{i:2d}/{total}] {biz[:50]}")
        gdata = get_google_data(biz, google_index)
        rating = gdata["google_rating"]
        reviews = gdata["google_reviews"]
        print(f"          Google: {rating} stars, {reviews} reviews")
        email = None
        if website and website.lower() not in ("nan","none",""):
            email = get_business_email(website)
            if email: print(f"          Email: {email}")
        title = None
        if owner and owner != "Not found":
            title = extract_owner_title(website, owner)
            if title: print(f"          Title: {title}")
        print(f"          DDG verify...")
        ddg = ddg_verify_owner(biz, owner)
        if ddg.get("ddg_confirmed"): print(f"          DDG: CONFIRMED")
        elif ddg.get("ddg_owner"): print(f"          DDG owner: {ddg['ddg_owner']}")
        final_owner = owner
        final_conf = str(row.get("owner_confidence","none"))
        final_source = str(row.get("owner_source",""))
        if (not owner or owner == "Not found") and ddg.get("ddg_owner"):
            final_owner = ddg["ddg_owner"]
            final_conf = "low"
            final_source = "duckduckgo_search"
        row_dict = row.to_dict()
        row_dict.update({"google_rating": rating, "google_reviews": reviews, "owner_email": email, "owner_name": final_owner, "owner_confidence": final_conf, "owner_source": final_source})
        conf_score = calculate_confidence_score(row_dict, ddg)
        print(f"          Confidence: {conf_score}")
        notes = build_notes(row_dict, ddg)
        results.append({
            "Business_name": biz,
            "Address": row.get("address",""),
            "City": row.get("city",""),
            "Postal_code": row.get("postal_code",""),
            "Phone": row.get("phone",""),
            "Website": website if website.lower() not in ("nan","none") else "",
            "Industry": row.get("industry",""),
            "Category_standardized": row.get("category_standardized",""),
            "Google_review_count": reviews,
            "Google_rating": rating,
            "Employee_range_estimate": row.get("employee_range_estimate",""),
            "SDE_range_estimate (CAD)": row.get("sde_range_estimate",""),
            "Revenue_range_estimate (CAD)": row.get("revenue_range_estimate",""),
            "Age_range_estimate": row.get("age_range_estimate",""),
            "Confidence_score": conf_score,
            "Acquisition_fit_score": row.get("acquisition_fit_score",""),
            "owner_name": final_owner if final_owner != "Not found" else "",
            "owner_title": title or "",
            "owner_email": email or "",
            "owner_confidence": final_conf,
            "notes": notes,
        })
    df_out = pd.DataFrame(results)
    has_owner = (df_out["owner_name"] != "").sum()
    has_email = (df_out["owner_email"] != "").sum()
    has_rating = df_out["Google_rating"].notna().sum()
    avg_conf = df_out["Confidence_score"].mean()
    print(f"\n  {'='*55}")
    print(f"  Leads:          {len(df_out)}")
    print(f"  Owners found:   {has_owner} ({has_owner/len(df_out)*100:.0f}%)")
    print(f"  Emails found:   {has_email} ({has_email/len(df_out)*100:.0f}%)")
    print(f"  Google ratings: {has_rating} ({has_rating/len(df_out)*100:.0f}%)")
    print(f"  Avg confidence: {avg_conf:.2f}")
    xlsx_out = os.path.join(OUTPUT_DIR, f"vaudreuil_hamilton_standard_{DATE_STAMP}.xlsx")
    csv_out  = os.path.join(OUTPUT_DIR, f"vaudreuil_hamilton_standard_{DATE_STAMP}.csv")
    df_out.to_excel(xlsx_out, index=False)
    df_out.to_csv(csv_out, index=False, encoding="utf-8")
    print(f"  [OUTPUT] {xlsx_out}")
    print(f"  [OUTPUT] {csv_out}")

if __name__ == "__main__":
    main()
