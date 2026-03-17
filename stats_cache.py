import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def filter_hash(filter_data: Optional[Dict[str, Any]]) -> str:
    """SHA256 of stable JSON serialization of the filter dict."""
    return hashlib.sha256(
        json.dumps(filter_data or {}, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()


async def get_valid_cache(db, cache_col: str, fhash: str) -> Optional[Dict[str, Any]]:
    """Return cache document if it exists and valid=True, else None."""
    return await db[cache_col].find_one({"_id": fhash, "valid": True})


async def store_cache(
    db,
    cache_col: str,
    fhash: str,
    filter_data: Optional[Dict[str, Any]],
    product_name: str,
    total_count: int,
    stats,
    base_stats,
    available_filters,
) -> None:
    """Upsert cache document. Preserves hits counter across re-computations."""
    await db[cache_col].update_one(
        {"_id": fhash},
        {
            "$set": {
                "filter": filter_data or {},
                "productName": product_name,
                "valid": True,
                "cachedAt": datetime.now(timezone.utc),
                "totalCount": total_count,
                "stats": stats.model_dump() if stats else None,
                "baseStats": base_stats.model_dump() if base_stats else None,
                "availableFilters": {
                    k: [fv.model_dump() for fv in vs]
                    for k, vs in (available_filters or {}).items()
                },
            },
            "$setOnInsert": {"hits": 0},
        },
        upsert=True,
    )


async def increment_hits(db, cache_col: str, fhash: str) -> None:
    """Increment the hits counter for a cache entry."""
    await db[cache_col].update_one({"_id": fhash}, {"$inc": {"hits": 1}})
