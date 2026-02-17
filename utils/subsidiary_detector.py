"""
Subsidiary and division detection (NEW in v3).

The single highest-value filter for clean acquisition leads.
Many businesses in Vaudreuil-Dorion's industrial parks are local operations
of large multinationals or publicly traded companies. They appear as
standalone businesses in Google Places and Yellow Pages but are NOT
independently acquirable.

Detection approach (three layers):
  1. Known subsidiaries: manually curated list of confirmed non-acquirable
     operations in Vaudreuil-Dorion and the MRC de Vaudreuil-Soulanges.
  2. Name pattern detection: "Canada Inc", "Ltée" combined with parent
     company indicators. Catches common subsidiary naming patterns.
  3. REQ cross-reference: if the Registraire data shows a parent company
     (société mère) or out-of-province head office, flag it.

IMPORTANT: This filter FLAGS subsidiaries for removal. It does NOT try
to be clever about edge cases. Better to flag a false positive (which
gets caught in human review) than to let a Cascades plant through as
a "qualified acquisition target."
"""

from typing import Tuple, List, Dict
import pandas as pd


# ── Known subsidiaries operating in Vaudreuil-Dorion area ────────────────────
# Manually verified. These are divisions of large corporations confirmed
# to have operations in the J7V/J7X/J7W postal code area.
# Format: lowercase name fragment -> parent company / reason
KNOWN_SUBSIDIARIES = {
    "mersen": "Subsidiary of Mersen SA (Paris, CAC Mid 60, ~EUR 1B)",
    "excelitas": "Division of Excelitas Technologies (US, PE-owned, multi-billion)",
    "winpak": "Subsidiary of Winpak Ltd (TSX: WPK, ~$1B market cap)",
    "cascades": "Division of Cascades Inc (TSX: CAS, ~$5B revenue)",
    "forbo": "Subsidiary of Forbo Group (SIX: FORN, CHF 1.2B Swiss)",
    "fleury michon": "Subsidiary of Fleury Michon SA (EUR ~800M, French)",
    "fedex": "Division of FedEx Corporation (NYSE: FDX)",
    "ericsson": "Division of Telefonaktiebolaget LM Ericsson (global telecom)",
    "immunotec": "Multi-level marketing company, publicly traded",
    "quadra": "Part of Quadra Chemicals / UNIVAR Solutions (large distributor)",
    "purolator": "Subsidiary of Canada Post Corporation",
    "day & ross": "Subsidiary of McCain Foods conglomerate",
    "dicom": "Part of GLS / Royal Mail logistics network",
    # Add more as discovered during pipeline runs
}

# ── Name patterns suggesting subsidiary/division status ──────────────────────
# These are weaker signals; they flag for review rather than auto-exclude.
SUBSIDIARY_NAME_PATTERNS = [
    # Common subsidiary naming: "[Parent] Canada Inc."
    # But careful: many legitimate small businesses are "[Owner Name] Canada Inc."
    "division of", "division de", "filiale de", "filiale",
    "a subsidiary", "une filiale",
    "operated by", "exploité par",
    "a division", "une division",
]

# ── Signals from company descriptions ────────────────────────────────────────
SUBSIDIARY_DESCRIPTION_SIGNALS = [
    "publicly traded", "cotée en bourse",
    "fortune 500", "fortune 1000",
    "global leader", "chef de file mondial",
    "expert mondial", "world leader",
    "offices worldwide", "bureaux à travers le monde",
    "operations in over", "opérations dans plus de",
    "listed on", "inscrite à la bourse",
    "headquartered in", "siège social situé",
    "part of the", "fait partie du groupe",
    "member of the", "membre du groupe",
]


def is_subsidiary(company_name: str, industry_desc: str = "",
                  req_parent: str = "") -> Tuple[bool, str]:
    """
    Check if a business is a subsidiary or division of a larger entity.

    Args:
        company_name: Business name
        industry_desc: Business description (from Google or Yellow Pages)
        req_parent: Parent company field from REQ data (if available)

    Returns:
        Tuple of (is_subsidiary: bool, reason: str)
    """
    name_lower = company_name.lower().strip()
    desc_lower = (industry_desc or "").lower().strip()
    parent_lower = (req_parent or "").lower().strip()

    # Layer 1: Known subsidiaries (strongest signal, auto-exclude)
    for name_fragment, reason in KNOWN_SUBSIDIARIES.items():
        if name_fragment in name_lower:
            return True, reason

    # Layer 2: REQ parent company field
    if parent_lower and parent_lower not in ("", "none", "nan", "n/a"):
        return True, f"REQ lists parent: {req_parent[:50]}"

    # Layer 3: Name patterns
    for pattern in SUBSIDIARY_NAME_PATTERNS:
        if pattern in name_lower or pattern in desc_lower:
            return True, f"Subsidiary pattern: {pattern}"

    # Layer 4: Description signals (weaker, but still flag)
    signal_count = 0
    matched_signals = []
    for signal in SUBSIDIARY_DESCRIPTION_SIGNALS:
        if signal in desc_lower:
            signal_count += 1
            matched_signals.append(signal)

    # Two or more signals in description = likely large company
    if signal_count >= 2:
        return True, f"Description signals: {', '.join(matched_signals[:3])}"

    return False, ""


def flag_subsidiaries(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Apply subsidiary detection to a DataFrame.
    Returns (filtered_df, list_of_flagged_entries).

    Looks for columns: company_name, industry_description, req_parent_company
    """
    flagged = []
    keep_mask = []

    for _, row in df.iterrows():
        name = str(row.get("company_name", ""))
        desc = str(row.get("industry_description", "")) if pd.notna(row.get("industry_description")) else ""
        parent = str(row.get("req_parent_company", "")) if pd.notna(row.get("req_parent_company")) else ""

        is_sub, reason = is_subsidiary(name, desc, parent)
        keep_mask.append(not is_sub)

        if is_sub:
            flagged.append({"company_name": name, "reason": reason})

    result = df[keep_mask].copy()
    return result, flagged
