# =============================================================================
# Vaudreuil MVP — Pipeline Configuration (v3: All-Sector / Strict Mode)
# =============================================================================

import os
from dotenv import load_dotenv

load_dotenv()

# === API KEYS ===
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "YOUR_KEY_HERE")

# === TARGET GEOGRAPHY ===
TARGET_CITY = "Vaudreuil-Dorion"
TARGET_PROVINCE = "QC"
TARGET_POSTAL_PREFIXES = ["J7V", "J7X", "J7W"]

# Geographic bounds for lat/lng filtering when postal code is unavailable
GEO_BOUNDS = {
    "south": 45.37,
    "north": 45.43,
    "west": -74.11,
    "east": -73.96,
}

# === SECTOR SCOPE (v3: STRICT EXCLUSIONS) ===
# We want "Operating Businesses" (Industrial, Commercial, B2B).
# We DO NOT want "Practices" (Doctors, Lawyers) or "Lifestyle" (Gyms, Salons).

EXCLUDED_SECTOR_KEYWORDS = [
    # --- Retail & B2C ---
    "boutique", "magasin", "store", "shop", "outlet", "mall", "centre commercial",
    "vape", "tabagie", "dépanneur", "depanneur", "convenience", "liquor", "saq",
    "fleuriste", "florist", "gift", "cadeau", "bijouterie", "jewel",
    "supermarche", "supermarché", "grocery", "épicerie", "epicerie", "iga",
    "sqdc",  # Government cannabis retail

    # --- Personal Services (The "Solopreneur" Kill List) ---
    "coiffure", "salon", "barber", "esthetique", "esthétique", "aesthetic", "spa", "massage",
    "ongles", "nails", "tanning", "bronze", "epilation", "épilation", "laser",
    "nettoyeur", "cleaners", "buanderie", "laundry", "couture", "tailor",
    "beauty", "beaute", "beauté",  # Beauty salons

    # --- Health & Medical (Practices, not Businesses) ---
    "dentist", "dentaire", "ortho", "clinic", "clinique", "medical", "médical", "sante", "santé",
    "docteur", "dr.", "dre.", "md", "physio", "chiro", "osteo", "ostéo", "ergo",
    "pharmacie", "pharmacy", "jean coutu", "uniprix", "familiprix", "pharmaprix",
    "veterinaire", "vétérinaire", "vet ", "animal", "hopital", "hôpital", "hospital",

    # --- Real Estate & Financial (Agents/Brokers) ---
    "courtier", "broker", "immobilier", "real estate", "remax", "royal lepage",
    "sutton", "via capitale", "hypotheque", "hypothèque", "mortgage", "bank", "banque",
    "caisse", "desjardins", "assurance", "insurance", "invest", "finance",

    # --- Professional Services (Independent Consultants) ---
    "notaire", "notary", "avocat", "lawyer", "legal", "juridi",
    "comptable", "cpa", "accountant", "accounting", "bookkeep", "impot", "impôt", "tax",
    "consultant", "conseil", "gestion", "management",

    # --- Education & Childcare ---
    "ecole", "école", "school", "college", "collège", "cpe", "garderie", "daycare",
    "centre de la petite enfance",
    "education", "éducation", "tutor", "lecon", "leçon", "lesson", "formation", "training",
    "gym", "yoga", "pilates", "fitness", "crossfit", "martial", "karate", "karaté", "dance", "danse",

    # --- Food Service ---
    "restaurant", "restau", "bistro", "cafe", "café", "coffee", "bar ", " bar", "pub", "club",
    "pizza", "sushi", "burger", "grill", "cantine", "traiteur", "catering",
    "tim hortons", "mcdonald", "subway", "a&w", "wendy", "burger king",
    "bakery", "boulangerie", "patisserie", "pâtisserie", "gateau", "gâteau",  # Bakeries

    # --- Religious & Non-Profit ---
    "church", "église", "eglise", "mosque", "synagogue",
    "non-profit", "sans but lucratif", "osbl", "npo",
    "charity", "organisme communautaire",
    "comité", "comite", "committee",  # Municipal committees

    # --- Known Franchises (not independently acquirable) ---
    "lebeau", "vitres d'autos", "auto glass", "belron",  # Lebeau/Belron franchise
    "speedy", "midas", "meineke", "jiffy lube", "mr. lube",
    "uhaul", "u-haul", "budget", "enterprise", "hertz", "avis",

    # --- Known Subsidiaries / Large Corp Operations ---
    "raylobec", "waste connections",  # Waste Connections Canada subsidiary
    "waste management", "gfl", "terrapure",
]

HIGH_VALUE_SECTOR_KEYWORDS = [
    "manufactur", "usinage", "machining", "welding", "soudure",
    "industriel", "industrial", "fabrication", "acier", "steel",
    "distribution", "wholesale", "grossiste", "entrepot", "warehouse",
    "logistique", "logistics", "transport", "camionnage", "trucking",
    "construction", "contractor", "entrepreneur", "excavation", "pavage",
    "mecanique", "mechanic", "garage", "automotive", "carrosserie",
    "imprimerie", "printing", "sign", "enseigne",
    "hvac", "climatisation", "plomberie", "plumbing", "electric",
    "paysagement", "landscaping", "neige", "snow",
]

# === SCORING WEIGHTS (v3) ===
WEIGHT_YEARS_IN_BUSINESS = 0.25
WEIGHT_REVIEW_COUNT = 0.10
WEIGHT_SECTOR_SIGNAL = 0.15
WEIGHT_EMPLOYEE_COUNT = 0.15
WEIGHT_DATA_QUALITY = 0.15
WEIGHT_WEBSITE_PRESENCE = 0.10
WEIGHT_LOCATION_BONUS = 0.05
WEIGHT_OWNERSHIP_SIGNAL = 0.05

# === THRESHOLDS ===
MIN_EMPLOYEES = 3
MAX_EMPLOYEES = 200
MAX_ANNUAL_REVENUE = 5_000_000
QUALIFICATION_THRESHOLD = 40
UNVERIFIED_PENALTY = 10
FUZZY_NAME_THRESHOLD = 85  # Minimum similarity score for fuzzy name matching
TARGET_FINAL_LEADS = 75  # Number of leads to export

# Industry margin estimates for SDE calculation
INDUSTRY_MARGINS = {
    "default": 0.15,
    "manufacturing": 0.12,
    "construction": 0.10,
    "transport": 0.08,
    "wholesale": 0.06,
    "services": 0.20,
}

# Review count thresholds for scoring
REVIEW_THRESHOLDS = {
    "very_low": 2,
    "low": 5,
    "moderate": 15,
    "good": 30,
    "excellent": 50,
}

# Revenue estimation parameters
REVENUE_ESTIMATION = {
    "base_range": (500_000, 2_500_000),  # Base revenue estimate range
    "confidence_margin": 0.35,  # +/- 35% for low/high estimates
    "per_employee_low": 80_000,
    "per_employee_mid": 120_000,
    "per_employee_high": 180_000,
}

# === FILE PATHS ===
CHECKPOINT_RAW = "data/raw_candidates.csv"
CHECKPOINT_FILTERED = "data/filtered_candidates.csv"
CHECKPOINT_GOOGLE = "data/google_enriched.csv"
CHECKPOINT_DEDUPED = "data/deduped_candidates.csv"
CHECKPOINT_REQ = "data/req_enriched.csv"
CHECKPOINT_SCORED = "data/scored_candidates.csv"
OUTPUT_FINAL = "data/top_75_for_review.csv"
OUTPUT_EXCEL = "data/Vaudreuil_Acquisition_Leads.xlsx"

# === TOGGLES ===
CHAIN_FILTER_ENABLED = True
SUBSIDIARY_FILTER_ENABLED = True
WEBSITE_VALIDATION_ENABLED = True

# === REQ SCRAPER CONFIG ===
REQ_MAX_RETRIES = 3

# === GOOGLE PLACES CONFIG ===
GOOGLE_DELAY_SECONDS = 0.5
CACHE_ENABLED = True

# === GRID SEARCH CONFIG ===
GRID_CELL_SIZE_M = 500
SEARCH_RADIUS_M = 400
