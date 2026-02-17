# =============================================================================
# Vaudreuil MVP — Pipeline Configuration (v3: All-Sector)
# =============================================================================
# v3: Expanded from manufacturing-only to all acquirable sectors.
#     Excludes retail stores and restaurants per acquisition mandate.
#     Revenue cap raised to $5M. Scoring recalibrated for cross-sector leads.
#
# Version history:
#   v1: Manufacturing-only, basic 4-factor scoring
#   v2: Manufacturing-only, 6-factor scoring, Hamilton feature port
#   v3: All sectors except retail/restaurants, subsidiary detection,
#       cross-sector scoring, $5M cap
# =============================================================================

import os
from dotenv import load_dotenv

load_dotenv()

# === API KEYS ===
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "YOUR_GOOGLE_PLACES_API_KEY")

# === TARGET GEOGRAPHY ===
TARGET_CITY = "Vaudreuil-Dorion"
TARGET_PROVINCE = "QC"
TARGET_POSTAL_PREFIXES = ["J7V", "J7X", "J7W"]

# === SECTOR SCOPE (v3: ALL sectors, with exclusions) ===
# v2 used TARGET_SIC_RANGE = (2000, 3999) for manufacturing only.
# v3 includes everything. Filtering works by EXCLUDING unwanted types.

# Businesses matching these keywords in name or description are EXCLUDED.
# Two excluded categories: retail stores and restaurants/food service.
EXCLUDED_SECTOR_KEYWORDS = [
    # --- Restaurants, bars, food service ---
    "restaurant", "resto", "cafe", "café", "bistro",
    "bar ", " bar", "pub", "taverne", "lounge",
    "pizzeria", "pizza", "sushi", "souvlaki", "shawarma", "poutine",
    "diner", "grill", "rôtisserie", "rotisserie", "cantine",
    "buffet", "banquet", "food truck",
    "crèmerie", "creamery", "ice cream", "gelato",
    "fast food", "restauration rapide",
    # --- Retail stores and shops ---
    "magasin", "boutique", "shop ", " shop", "retail",
    "grocery", "épicerie", "supermarket", "supermarché",
    "dépanneur", "convenience store",
    "pharmacy", "pharmacie",
    "dollar store", "friperie", "thrift",
    "pet store", "animalerie",
    "liquor store",
    "flower shop", "fleuriste",
    "gift shop",
    "jewel", "bijou",
    "shoe store", "chaussure",
    # --- Other non-acquirable types ---
    "church", "église", "mosque", "synagogue",
    "school", "école", "university", "université", "cegep",
    "daycare", "garderie", "cpe ",
    "hospital", "hôpital",
    "government", "gouvernement",
    "non-profit", "sans but lucratif", "osbl",
    "charity", "organisme communautaire",
]

# Positive sector keywords: used for SCORING (not filtering).
# Businesses matching these get a boost because they represent sectors
# with stronger acquisition characteristics (recurring revenue, contracts,
# skilled workforce, tangible assets, owner-operator structures).
HIGH_VALUE_SECTOR_KEYWORDS = [
    # Manufacturing and fabrication
    "manufactur", "fabricat", "usine", "production",
    "assemblage", "machinage", "usinage", "menuiserie",
    "plastics", "plastique", "metal", "métallurg",
    "wood", "bois", "textile",
    "chemical", "chimique",
    "food processing", "transformation alimentaire",
    "microbrasserie", "microbrewery", "brewery", "brasserie artisanale",
    "printing", "imprimerie",
    "packaging", "emballage",
    # Construction and trades
    "construction", "rénovation", "renovation",
    "plumbing", "plomberie", "plombier",
    "electrical", "électrique", "électricien",
    "hvac", "chauffage", "climatisation", "ventilation",
    "roofing", "toiture", "couvreur",
    "excavation", "excavat",
    "concrete", "béton",
    "masonry", "maçonnerie",
    "welding", "soudure",
    "carpentry", "charpente", "ébénisterie",
    "insulation", "isolation",
    "paving", "pavage", "asphalte",
    "demolition", "démolition",
    "general contractor", "entrepreneur général",
    # Transportation and logistics
    "transport", "trucking", "camionnage",
    "warehouse", "entreposage", "entrepôt",
    "logistics", "logistique",
    "courier", "messagerie", "livraison",
    "moving", "déménagement",
    "freight", "fret",
    # Professional and technical services
    "engineering", "ingénierie", "ingénieur",
    "consulting", "conseil",
    "it service", "informatique",
    "accounting", "comptab",
    "surveying", "arpentage",
    "testing", "laboratory", "laboratoire",
    # Wholesale and distribution
    "wholesale", "gros", "distribution", "distributeur",
    "supply", "fourniture", "fournisseur",
    # Specialized services
    "equipment", "équipement",
    "maintenance", "entretien",
    "cleaning", "nettoyage", "janitorial",
    "landscaping", "aménagement paysager", "paysagiste",
    "security", "sécurité", "gardiennage",
    "pest control", "extermination",
    "waste management", "gestion des déchets",
    "towing", "remorquage",
    "auto repair", "mécanique automobile", "garage",
    "refrigeration", "réfrigération",
    "signage", "enseigne", "affichage",
]

# === FILTERING THRESHOLDS ===
MIN_EMPLOYEES = 5
MAX_EMPLOYEES = 200
MAX_ANNUAL_REVENUE = 5_000_000  # v3: raised from $2M to $5M

# === SCORING WEIGHTS (must sum to 1.0) ===
# v3: rebalanced for cross-sector leads.
WEIGHT_YEARS_IN_BUSINESS = 0.25
WEIGHT_REVIEW_COUNT = 0.10       # Reduced: reviews are biased toward B2C
WEIGHT_SECTOR_SIGNAL = 0.15      # Renamed from SECTOR_FIT; broader matching
WEIGHT_EMPLOYEE_COUNT = 0.15     # Increased: employee count matters everywhere
WEIGHT_DATA_QUALITY = 0.15
WEIGHT_WEBSITE_PRESENCE = 0.10
WEIGHT_LOCATION_BONUS = 0.05
WEIGHT_OWNERSHIP_SIGNAL = 0.05   # NEW: independent ownership indicators

# Verification penalty for unverified leads
UNVERIFIED_PENALTY = 0.90

# Score threshold for qualification
QUALIFICATION_THRESHOLD = 40  # Lowered from 45: broader sweep, looser gate

# === REVENUE ESTIMATION PARAMETERS ===
REVENUE_ESTIMATION = {
    "base_range": (500_000, 2_500_000),  # Wider for mixed sectors
    "review_adjustment": 0.15,
    "years_adjustment": 0.15,
    "website_adjustment": 0.10,
    "confidence_margin": 0.15,           # Wider band cross-sector
}

REVIEW_THRESHOLDS = {
    "very_low": 2,
    "low": 5,
    "moderate": 10,
    "good": 20,
    "excellent": 50,
}

INDUSTRY_MARGINS = {
    "manufacturing": 0.15,
    "printing": 0.18,
    "wholesale": 0.17,
    "professional_services": 0.30,
    "construction": 0.18,
    "trades": 0.22,
    "transportation": 0.15,
    "equipment_rental": 0.25,
    "food_processing": 0.12,
    "cleaning_services": 0.20,
    "landscaping": 0.22,
    "it_services": 0.35,
    "default": 0.18,
}

# === CHAIN/FRANCHISE FILTERING ===
CHAIN_FILTER_ENABLED = True

# === SUBSIDIARY DETECTION ===
SUBSIDIARY_FILTER_ENABLED = True  # NEW v3

# === API CACHING ===
CACHE_ENABLED = True
CACHE_TTL_HOURS = 168

# === WEBSITE VALIDATION ===
WEBSITE_VALIDATION_ENABLED = True
WEBSITE_TIMEOUT_SECONDS = 10
MAX_WEBSITE_CHECKS_PER_RUN = 300  # Raised: more companies in scope

# === FUZZY MATCHING ===
FUZZY_NAME_THRESHOLD = 85

# === PIPELINE TARGET NUMBERS ===
TARGET_FINAL_LEADS = 75  # Raised from 50: broader scope

# === FILE PATHS ===
RAW_ICRIC_FILE = "data/raw/icric_export.csv"
RAW_YELLOWPAGES_FILE = "data/raw/yellowpages_export.csv"

CHECKPOINT_RAW = "data/raw_candidates.csv"
CHECKPOINT_FILTERED = "data/filtered_candidates.csv"
CHECKPOINT_GOOGLE = "data/google_enriched.csv"
CHECKPOINT_DEDUPED = "data/deduped_candidates.csv"
CHECKPOINT_REQ = "data/req_enriched.csv"
CHECKPOINT_SCORED = "data/scored_candidates.csv"
OUTPUT_FINAL = "data/top_75_for_review.csv"
OUTPUT_EXCEL = "data/Vaudreuil_Acquisition_Leads.xlsx"

# === REQ SCRAPER ===
REQ_BASE_URL = "https://www.registraire.gouv.qc.ca"
REQ_MAX_RETRIES = 3
REQ_TIMEOUT_MS = 30000

# === GOOGLE PLACES ===
GOOGLE_DELAY_SECONDS = 0.5

# === GEOGRAPHIC BOUNDS (Vaudreuil-Dorion + immediate surroundings) ===
# Bounding box covers Vaudreuil-Dorion, Dorion, Ile-Perrot, Pincourt
# so we capture industrial parks and businesses that straddle municipal lines.
GEO_BOUNDS = {
    "south": 45.370,   # Southern limit (below A-20)
    "north": 45.430,   # Northern limit (above A-40)
    "west": -74.110,   # Western limit (beyond Cite-des-Jeunes)
    "east": -73.960,   # Eastern limit (Ile-Perrot bridge area)
}

# Grid search parameters
# Each cell is ~500m x 500m. Google nearbySearch has a 50,000m max radius
# but returns better results with small radii in dense areas.
GRID_CELL_SIZE_M = 500       # meters per grid cell
GRID_SEARCH_RADIUS_M = 400   # radius per query (slightly less than cell to avoid gaps)
GRID_MAX_RESULTS_PER_CELL = 60  # Google Places returns max 60 per query (3 pages of 20)

# === ACQUISITION SEARCH KEYWORDS (v3: All-Sector) ===
# Two strategies run in sequence:
# 1. Geographic grid: type=establishment, no keyword (catches everything)
# 2. Keyword supplement: targeted queries for specific sectors that may
#    not appear in type=establishment results.

ACQUISITION_KEYWORDS_FR = [
    "entreprise",
    "industriel",
    "usine",
    "fabrication",
    "construction",
    "rénovation",
    "transport",
    "camionnage",
    "entreposage",
    "distribution",
    "service commercial",
    "plomberie",
    "électricien",
    "climatisation",
    "mécanique",
    "paysagement",
    "nettoyage commercial",
    "ingénierie",
    "informatique",
    "comptabilité",
    "soudure",
    "excavation",
    "béton",
    "toiture",
    "imprimerie",
]

ACQUISITION_KEYWORDS_EN = [
    "company",
    "industrial",
    "manufacturing",
    "contractor",
    "trucking",
    "warehouse",
    "wholesale",
    "equipment",
    "maintenance",
    "engineering",
    "consulting",
    "cleaning service",
    "landscaping",
    "printing",
]
