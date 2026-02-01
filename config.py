# =============================================================================
# Vaudreuil MVP — Pipeline Configuration
# =============================================================================
# All constants live here. No YAML. No .env loaders (except API key).
# =============================================================================

import os
from dotenv import load_dotenv

# Load .env file (contains API key - gitignored)
load_dotenv()

# === API KEYS ===
# Loaded from .env file or environment variable
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "YOUR_GOOGLE_PLACES_API_KEY")

# === TARGET GEOGRAPHY ===
TARGET_CITY = "Vaudreuil-Dorion"
TARGET_PROVINCE = "QC"
# Vaudreuil-Dorion area postal code prefixes — expand if needed
TARGET_POSTAL_PREFIXES = ["J7V", "J7X", "J7W"]

# === MANUFACTURING CATEGORY MATCHING ===
# SIC code range for manufacturing (20-39 in the standard classification)
TARGET_SIC_RANGE = (2000, 3999)

# Keyword list for industries — used when SIC code is unavailable
TARGET_KEYWORDS = [
    "manufactur",
    "fabricat",
    "usine",
    "production",
    "assemblage",
    "machinage",
    "menuiserie",
    "plastics",
    "plastique",
    "metal",
    "métallurg",
    "wood",
    "bois",
    "textile",
    "chemical",
    "chimique",
    "food processing",
    "alimentation",
    "printing",
    "imprimerie",
    "packaging",
    "emballage",
]

# === FILTERING THRESHOLDS ===
MIN_EMPLOYEES = 5
MAX_EMPLOYEES = 200  # Sweet spot for small acquisition targets

# === SCORING WEIGHTS (must sum to 1.0) ===
WEIGHT_YEARS_IN_BUSINESS = 0.35
WEIGHT_REVIEW_COUNT = 0.25
WEIGHT_SECTOR_FIT = 0.25
WEIGHT_EMPLOYEE_COUNT = 0.15

# === FUZZY MATCHING ===
FUZZY_NAME_THRESHOLD = 85  # Minimum similarity score (0-100) to consider a match

# === PIPELINE TARGET NUMBERS ===
TARGET_FINAL_LEADS = 50

# === FILE PATHS — checkpoints ===
RAW_ICRIC_FILE = "data/raw/icric_export.csv"
RAW_YELLOWPAGES_FILE = "data/raw/yellowpages_export.csv"

CHECKPOINT_RAW = "data/raw_candidates.csv"
CHECKPOINT_FILTERED = "data/filtered_candidates.csv"
CHECKPOINT_GOOGLE = "data/google_enriched.csv"
CHECKPOINT_REQ = "data/req_enriched.csv"
CHECKPOINT_DEDUPED = "data/deduped_candidates.csv"
CHECKPOINT_SCORED = "data/scored_candidates.csv"
OUTPUT_FINAL = "data/top_50_for_review.csv"

# === REQ SCRAPER ===
REQ_BASE_URL = "https://www.registraire.gouv.qc.ca"
REQ_MAX_RETRIES = 3
REQ_TIMEOUT_MS = 30000  # 30 seconds per page load

# === GOOGLE PLACES ===
GOOGLE_DELAY_SECONDS = 0.5  # Polite delay between API calls
