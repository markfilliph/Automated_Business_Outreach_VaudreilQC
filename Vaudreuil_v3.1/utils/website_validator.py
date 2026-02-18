"""
Website validation for business leads.

Ported from Hamilton MVP's website verification system.
Checks whether a business URL actually resolves and looks legitimate.

This is SYNCHRONOUS per Vaudreuil build rules. Uses requests, not aiohttp.
"""

import re
import requests
from urllib.parse import urlparse
from typing import Tuple, Optional


# Timeout for website checks (seconds)
WEBSITE_TIMEOUT = 10

# Known parking/placeholder page indicators
PARKING_INDICATORS = [
    "this domain is for sale",
    "domain is parked",
    "buy this domain",
    "under construction",
    "coming soon",
    "godaddy",
    "wix.com/site-not-found",
    "squarespace/expired",
    "page not found",
    "403 forbidden",
]

# Social media domains that are NOT a company website
SOCIAL_DOMAINS = [
    "facebook.com", "fb.com",
    "instagram.com",
    "twitter.com", "x.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "yelp.com",
    "google.com/maps",
]


def normalize_url(url: str) -> Optional[str]:
    """
    Normalize a URL string. Returns None if unusable.
    Adds https:// if no protocol specified.
    """
    if not url or str(url).lower() in ("nan", "none", ""):
        return None

    url = str(url).strip()

    # Skip social media links
    for domain in SOCIAL_DOMAINS:
        if domain in url.lower():
            return None

    # Add protocol if missing
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        parsed = urlparse(url)
        if parsed.netloc and "." in parsed.netloc:
            return url
    except Exception:
        pass

    return None


def validate_website(url: str) -> Tuple[bool, str, Optional[int]]:
    """
    Validate that a website URL is reachable and not a parked domain.

    Returns:
        Tuple of (is_valid, status_message, http_status_code)

    Examples:
        (True, "OK", 200)
        (False, "Timeout", None)
        (False, "Parked domain", 200)
    """
    normalized = normalize_url(url)
    if not normalized:
        return False, "Invalid or social media URL", None

    try:
        response = requests.get(
            normalized,
            timeout=WEBSITE_TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )

        status_code = response.status_code

        # Check HTTP status
        if status_code >= 400:
            return False, f"HTTP {status_code}", status_code

        # Check for parked/placeholder pages
        body_lower = response.text[:5000].lower()
        for indicator in PARKING_INDICATORS:
            if indicator in body_lower:
                return False, f"Parked domain ({indicator})", status_code

        # Check if SSL is valid (https)
        has_ssl = response.url.startswith("https://")

        return True, "OK" if has_ssl else "OK (no SSL)", status_code

    except requests.exceptions.Timeout:
        return False, "Timeout", None
    except requests.exceptions.ConnectionError:
        return False, "Connection failed", None
    except requests.exceptions.TooManyRedirects:
        return False, "Too many redirects", None
    except Exception as e:
        return False, f"Error: {str(e)[:50]}", None


def batch_validate(df, website_col: str = "website", max_checks: int = 200):
    """
    Validate websites for a DataFrame of leads.
    Adds columns: website_valid, website_status, website_http_code

    Args:
        df: DataFrame with a website column
        website_col: Name of the website column
        max_checks: Safety limit on number of HTTP requests

    Returns:
        DataFrame with validation columns added
    """
    import pandas as pd
    import time

    results = []
    checked = 0

    for _, row in df.iterrows():
        url = row.get(website_col, "")

        if not url or str(url).lower() in ("nan", "none", "", "unknown"):
            results.append({"website_valid": False, "website_status": "No URL", "website_http_code": None})
            continue

        if checked >= max_checks:
            results.append({"website_valid": None, "website_status": "Skipped (limit)", "website_http_code": None})
            continue

        is_valid, status, code = validate_website(str(url))
        results.append({"website_valid": is_valid, "website_status": status, "website_http_code": code})
        checked += 1

        # Polite delay
        time.sleep(0.3)

    result_df = pd.DataFrame(results, index=df.index)
    return pd.concat([df, result_df], axis=1)
