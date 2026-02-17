"""
Simple file-based API response cache.

Ported from Hamilton MVP's SQLite caching system, simplified to use JSON files
per the Vaudreuil build rules (no database, no ORM).

Saves Google Places API responses to avoid re-fetching on pipeline re-runs.
Expected savings: 50%+ on API costs when iterating on filtering/scoring logic.

Cache files live in data/cache/ (gitignored).
"""

import json
import hashlib
import os
import time
from typing import Optional, Any


CACHE_DIR = "data/cache"
DEFAULT_TTL_HOURS = 168  # 7 days


def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_key(prefix: str, query: str) -> str:
    """Generate a filesystem-safe cache key from a query string."""
    hash_val = hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]
    return f"{prefix}_{hash_val}"


def _cache_path(key: str) -> str:
    """Full filesystem path for a cache entry."""
    return os.path.join(CACHE_DIR, f"{key}.json")


def get(prefix: str, query: str, ttl_hours: float = DEFAULT_TTL_HOURS) -> Optional[Any]:
    """
    Retrieve a cached API response.

    Args:
        prefix: Cache namespace (e.g. "google_places", "google_details")
        query: The original query string (will be hashed)
        ttl_hours: Maximum age before cache entry expires

    Returns:
        Cached data if found and not expired, None otherwise.
    """
    _ensure_cache_dir()
    key = _cache_key(prefix, query)
    path = _cache_path(key)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)

        # Check TTL
        cached_at = entry.get("cached_at", 0)
        age_hours = (time.time() - cached_at) / 3600

        if age_hours > ttl_hours:
            # Expired; remove stale entry
            os.remove(path)
            return None

        return entry.get("data")

    except (json.JSONDecodeError, KeyError, OSError):
        # Corrupt cache file; remove it
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def put(prefix: str, query: str, data: Any) -> None:
    """
    Store an API response in the cache.

    Args:
        prefix: Cache namespace
        query: The original query string
        data: Response data to cache (must be JSON-serializable)
    """
    _ensure_cache_dir()
    key = _cache_key(prefix, query)
    path = _cache_path(key)

    entry = {
        "query": query,
        "cached_at": time.time(),
        "data": data,
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as e:
        print(f"    [Cache] Warning: could not write cache for {key}: {e}")


def stats() -> dict:
    """Return cache statistics: total entries, disk usage."""
    _ensure_cache_dir()
    entries = [f for f in os.listdir(CACHE_DIR) if f.endswith(".json")]
    total_bytes = sum(
        os.path.getsize(os.path.join(CACHE_DIR, f))
        for f in entries
        if os.path.isfile(os.path.join(CACHE_DIR, f))
    )
    return {
        "entries": len(entries),
        "size_kb": round(total_bytes / 1024, 1),
    }


def clear(prefix: Optional[str] = None) -> int:
    """
    Clear cache entries. If prefix is given, only clear that namespace.
    Returns number of entries removed.
    """
    _ensure_cache_dir()
    removed = 0
    for f in os.listdir(CACHE_DIR):
        if not f.endswith(".json"):
            continue
        if prefix and not f.startswith(prefix):
            continue
        try:
            os.remove(os.path.join(CACHE_DIR, f))
            removed += 1
        except OSError:
            pass
    return removed
