import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from models import EbayItemsRequest, EbayItemsResponse, FilterValue, Pagination, PriceBucket, SortSpecRequest, Stats
from stats_cache import filter_hash, get_valid_cache, store_cache, increment_hits

from util import _document_to_ebay_item

router = APIRouter()

STATS_CACHE_MAP: Dict[str, str] = {
    "MacBookPro": "mac_book_pro_stats",
    "MacBookAir": "mac_book_air_stats",
}

# ── Shared field lists ──
# LLM spec filter key → MongoDB llmSpecs path
LLM_SPEC_FIELD_MAP: Dict[str, str] = {
    # productLine excluded: show=True already enforces productLine == collection's product type
    "releaseYear": "llmSpecs.releaseYear",
    "cpuFamily": "llmSpecs.cpuFamily",
    "cpuModel": "llmSpecs.cpuModel",
    "cpuSpeed": "llmSpecs.cpuSpeed",
    "ramSize": "llmSpecs.ramSize",
    "ssdSize": "llmSpecs.ssdSize",
    "screenSize": "llmSpecs.screenSize",
    "color": "llmSpecs.color",
    "modelNumber": "llmSpecs.modelNumber",
    "modelId": "llmSpecs.modelId",
    "partNumber": "llmSpecs.partNumber",
}

# Analysis fields used for filtering (query llmAnalysis.*)
ANALYSIS_FILTER_FIELDS = ["specsCompleteness", "specsConsistency"]

LLM_FIELDS = [
    # subject excluded: show=True already enforces subject == "L"
    "charger", "battery", "screen", "keyboard", "housing",
    "audio", "ports", "functionality", "componentListing",
]

RANK_SORT_MAP = {
    "screen": "llmDerived.screenRank",
    "keyboard": "llmDerived.keyboardRank",
    "housing": "llmDerived.housingRank",
    "audio": "llmDerived.audioRank",
    "ports": "llmDerived.portsRank",
    "battery": "llmDerived.batteryRank",
    "functionality": "llmDerived.functionalityRank",
    "charger": "llmDerived.chargerRank",
    "subject": "llmDerived.subjectRank",
    "condition": "derived.conditionRank",
    "specsCompleteness": "llmAnalysis.specsCompletenessRank",
    "specsConsistency": "llmAnalysis.specsConsistencyRank",
}

# EPN affiliate URL parameters (appended to itemWebUrl)
_EPN_PARAMS = "mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid={campaign_id}&customid=&toolid=10001&mkevt=1"


def _build_epn_url(original_url: str, campaign_id: str) -> str:
    """Return original_url with EPN affiliate query parameters appended."""
    separator = "&" if "?" in original_url else "?"
    return original_url + separator + _EPN_PARAMS.format(campaign_id=campaign_id)


# Fixed $100 bucket boundaries for price histograms (0, 100, ..., 3000)
PRICE_BUCKET_BOUNDARIES = list(range(0, 3100, 100))

# Projection applied after $match and before $facet.
# Only fields consumed by $facet branches (facets, stats, sort) or the frontend
# (EbayItem model) are included. Fields marked "sort only" or "facet only" are
# not in the model but must be in the pipeline for MongoDB to use them.
_PIPELINE_PROJECTION: Dict[str, int] = {
    "_id": 1,
    "itemId": 1,
    "show": 1,
    # details — UI fields only (excludes full eBay API payload)
    "details.title": 1,
    "details.condition": 1,
    "details.image.imageUrl": 1,
    "details.itemWebUrl": 1,
    "details.returnTerms.returnsAccepted": 1,
    "details.returnTerms.returnShippingCostPayer": 1,
    "details.returnTerms.returnPeriod": 1,
    # derived — price: UI + stats/filter; conditionRank: sort only
    "derived.price": 1,
    "derived.conditionRank": 1,
    # llmSpecs — releaseYear..partNumber: UI; productLine: facet only
    "llmSpecs.productLine": 1,
    "llmSpecs.releaseYear": 1,
    "llmSpecs.cpuFamily": 1,
    "llmSpecs.cpuModel": 1,
    "llmSpecs.cpuSpeed": 1,
    "llmSpecs.ramSize": 1,
    "llmSpecs.ssdSize": 1,
    "llmSpecs.screenSize": 1,
    "llmSpecs.color": 1,
    "llmSpecs.modelNumber": 1,
    "llmSpecs.modelId": 1,
    "llmSpecs.partNumber": 1,
    # specsFilter — pre-computed filter values used by facets
    "specsFilter": 1,
    # llmAnalysis — issue/completeness: UI; rank fields: sort only
    "llmAnalysis.specsAnalysis": 1,
    "llmAnalysis.mainSpecsIssueSeverity": 1,
    "llmAnalysis.mainSpecsIssueDescription": 1,
    "llmAnalysis.specsCompleteness": 1,
    "llmAnalysis.specsConsistency": 1,
    "llmAnalysis.specsCompletenessRank": 1,
    "llmAnalysis.specsConsistencyRank": 1,
    # llmDerived — grade fields: UI; componentListing+subject: facets only;
    #              *Rank fields: sort only
    "llmDerived.charger": 1,
    "llmDerived.battery": 1,
    "llmDerived.screen": 1,
    "llmDerived.keyboard": 1,
    "llmDerived.housing": 1,
    "llmDerived.audio": 1,
    "llmDerived.ports": 1,
    "llmDerived.functionality": 1,
    "llmDerived.componentListing": 1,
    "llmDerived.subject": 1,
    "llmDerived.chargerRank": 1,
    "llmDerived.batteryRank": 1,
    "llmDerived.screenRank": 1,
    "llmDerived.keyboardRank": 1,
    "llmDerived.housingRank": 1,
    "llmDerived.audioRank": 1,
    "llmDerived.portsRank": 1,
    "llmDerived.functionalityRank": 1,
    "llmDerived.subjectRank": 1,
}


def _compose_query(filter_data: Optional[Dict[str, Any]], exclude_price: bool = False) -> Dict[str, Any]:
    query: Dict[str, Any] = {"$and": [{"show": True}]}

    if not filter_data:
        return query

    # specsFilter fields (pre-computed: llmSpecs if non-empty, else bestGuess fallback)
    for filter_key in LLM_SPEC_FIELD_MAP:
        value = filter_data.get(filter_key)
        if value is not None and value != []:
            values = list(value) if isinstance(value, list) else [value]
            query["$and"].append({f"specsFilter.{filter_key}": {"$in": values}})

    # llmAnalysis fields (specsCompleteness, specsConsistency)
    for analysis_field in ANALYSIS_FILTER_FIELDS:
        value = filter_data.get(analysis_field)
        if value is not None and value != []:
            query["$and"].append({f"llmAnalysis.{analysis_field}": {"$in": value if isinstance(value, list) else [value]}})

    # llmDerived fields
    for llm_field in LLM_FIELDS:
        value = filter_data.get(llm_field)
        if value is not None and value != []:
            query["$and"].append({f"llmDerived.{llm_field}": {"$in": value if isinstance(value, list) else [value]}})

    # details fields
    value = filter_data.get("returnable")
    if value is not None and value != []:
        query["$and"].append({"details.returnTerms.returnsAccepted": {"$in": value}})

    value = filter_data.get("returnShippingCostPayer")
    if value is not None and value != []:
        query["$and"].append({"details.returnTerms.returnShippingCostPayer": {"$in": value}})

    value = filter_data.get("condition")
    if value is not None and value != []:
        query["$and"].append({"details.condition": {"$in": value}})

    # price range filter (skip when building non-price query for priceBuckets)
    if not exclude_price:
        min_price = filter_data.get("minPrice")
        max_price = filter_data.get("maxPrice")
        if min_price is not None and not isinstance(min_price, (int, float)):
            min_price = None
        if max_price is not None and not isinstance(max_price, (int, float)):
            max_price = None
        if min_price is not None or max_price is not None:
            price_condition: Dict[str, Any] = {}
            if min_price is not None:
                price_condition["$gte"] = min_price
            if max_price is not None:
                price_condition["$lte"] = max_price
            query["$and"].append({"derived.price": price_condition})

    return query


def _compose_sort_specs(sort_specs: Optional[List[SortSpecRequest]]) -> List[tuple[str, int]]:
    default = [("derived.price", 1), ("_id", 1)]
    if not sort_specs:
        return default
    mongo_sort_specs = []
    for spec in sort_specs:
        field = spec.field
        direction = spec.direction
        if field in RANK_SORT_MAP:
            mongo_sort_specs.append((RANK_SORT_MAP[field], direction))
        elif field in LLM_SPEC_FIELD_MAP:
            mongo_sort_specs.append((LLM_SPEC_FIELD_MAP[field], direction))
        elif field == "price":
            mongo_sort_specs.append(("derived.price", direction))
        elif field == "returnable":
            mongo_sort_specs.append(("details.returnTerms.returnsAccepted", direction))
        elif field == "returnShippingCostPayer":
            mongo_sort_specs.append(("details.returnTerms.returnShippingCostPayer", direction))
    if mongo_sort_specs:
        return mongo_sort_specs + [("_id", 1)]
    else:
        return default


# ── Aggregation pipeline building helpers ──

def _build_price_match(filter_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Extract only the price range condition for within-facet application."""
    if not filter_data:
        return None
    min_price = filter_data.get("minPrice")
    max_price = filter_data.get("maxPrice")
    if min_price is not None and not isinstance(min_price, (int, float)):
        min_price = None
    if max_price is not None and not isinstance(max_price, (int, float)):
        max_price = None
    if min_price is None and max_price is None:
        return None
    condition: Dict[str, Any] = {}
    if min_price is not None:
        condition["$gte"] = min_price
    if max_price is not None:
        condition["$lte"] = max_price
    return {"derived.price": condition}


def _stats_facet(price_match: Optional[Dict[str, Any]] = None) -> List[Dict]:
    steps: List[Dict] = []
    if price_match:
        steps.append({"$match": price_match})
    steps.append({
        "$group": {
            "_id": None,
            "min": {"$min": "$derived.price"},
            "max": {"$max": "$derived.price"},
            "mean": {"$avg": "$derived.price"},
            "median": {"$median": {"input": "$derived.price", "method": "approximate"}},
            "count": {"$sum": 1},
        }
    })
    return steps


def _price_bins_facet(price_match: Optional[Dict[str, Any]] = None) -> List[Dict]:
    steps: List[Dict] = []
    if price_match:
        steps.append({"$match": price_match})
    steps.append({
        "$bucket": {
            "groupBy": "$derived.price",
            "boundaries": PRICE_BUCKET_BOUNDARIES,
            "default": "3000+",
            "output": {"count": {"$sum": 1}},
        }
    })
    return steps


def _count_facet(price_match: Optional[Dict[str, Any]] = None) -> List[Dict]:
    steps: List[Dict] = []
    if price_match:
        steps.append({"$match": price_match})
    steps.append({"$count": "n"})
    return steps


def _items_facet(sort_specs: List[tuple], skip: int, limit: int, price_match: Optional[Dict[str, Any]] = None) -> List[Dict]:
    steps: List[Dict] = []
    if price_match:
        steps.append({"$match": price_match})
    sort_dict: Dict[str, int] = dict(sort_specs)
    steps.append({"$sort": sort_dict})
    steps.append({"$skip": skip})
    steps.append({"$limit": limit})
    return steps


def _array_field_facet(field_path: str, price_match: Optional[Dict[str, Any]] = None) -> List[Dict]:
    steps: List[Dict] = []
    if price_match:
        steps.append({"$match": price_match})
    steps.append({"$unwind": f"${field_path}"})
    steps.append({"$group": {"_id": f"${field_path}", "count": {"$sum": 1}}})
    steps.append({"$sort": {"_id": 1}})
    return steps


def _scalar_field_facet(field_path: str, price_match: Optional[Dict[str, Any]] = None) -> List[Dict]:
    steps: List[Dict] = []
    if price_match:
        steps.append({"$match": price_match})
    steps.append({"$group": {"_id": f"${field_path}", "count": {"$sum": 1}}})
    steps.append({"$sort": {"_id": 1}})
    return steps


def _build_filter_value_facets(price_match: Optional[Dict[str, Any]] = None) -> Dict[str, List[Dict]]:
    facets: Dict[str, List[Dict]] = {}
    for field in LLM_SPEC_FIELD_MAP:
        facets[field] = _array_field_facet(f"specsFilter.{field}", price_match)
    for field in ANALYSIS_FILTER_FIELDS:
        facets[field] = _scalar_field_facet(f"llmAnalysis.{field}", price_match)
    for field in LLM_FIELDS:
        facets[field] = _scalar_field_facet(f"llmDerived.{field}", price_match)
    facets["returnable"] = _scalar_field_facet("details.returnTerms.returnsAccepted", price_match)
    facets["returnShippingCostPayer"] = _scalar_field_facet("details.returnTerms.returnShippingCostPayer", price_match)
    facets["condition"] = _scalar_field_facet("details.condition", price_match)
    return facets


def _build_aggregation_pipeline(
    match_query: Dict[str, Any],
    sort_specs: List[tuple],
    skip: int,
    limit: int,
    is_first_page: bool,
    price_match: Optional[Dict[str, Any]],
) -> List[Dict]:
    pipeline: List[Dict] = []
    pipeline.append({"$match": match_query})
    pipeline.append({"$project": _PIPELINE_PROJECTION})
    facet: Dict[str, List[Dict]] = {}
    facet["totalCount"] = _count_facet(price_match)
    facet["items"] = _items_facet(sort_specs, skip, limit, price_match)
    if is_first_page:
        if price_match:
            # baseStats/basePriceBins: no price filter, but still scoped to show=True
            # documents via the $match earlier in the pipeline (Story 7.7).
            facet["baseStats"] = _stats_facet()
            facet["basePriceBins"] = _price_bins_facet()
            facet["stats"] = _stats_facet(price_match)
        else:
            facet["stats"] = _stats_facet()
            facet["priceBins"] = _price_bins_facet()
        facet.update(_build_filter_value_facets(price_match))
    pipeline.append({"$facet": facet})
    return pipeline


# ── Aggregation result parsing helpers ──

def _parse_price_bins(bins_docs: List[Dict]) -> Optional[List[PriceBucket]]:
    if not bins_docs:
        return None
    buckets = []
    for doc in bins_docs:
        id_val = doc.get("_id")
        if id_val == "3000+" or not isinstance(id_val, (int, float)):
            continue
        range_min = float(id_val)
        range_max = range_min + 100.0
        count = doc.get("count", 0)
        if count > 0:
            buckets.append(PriceBucket(rangeMin=range_min, rangeMax=range_max, count=count))
    return buckets if buckets else None


def _parse_stats_from_facet(stats_docs: List[Dict], price_buckets: Optional[List[PriceBucket]] = None) -> Optional[Stats]:
    if not stats_docs:
        return None
    doc = stats_docs[0]
    return Stats(
        min=doc.get("min"),
        max=doc.get("max"),
        median=doc.get("median"),
        mean=doc.get("mean"),
        count=doc.get("count"),
        priceBuckets=price_buckets,
    )


def _parse_available_filters(
    facet_result: Dict[str, List[Dict]],
    filter_keys: List[str],
) -> Optional[Dict[str, List[FilterValue]]]:
    result: Dict[str, List[FilterValue]] = {}
    for key in filter_keys:
        docs = facet_result.get(key, [])
        values = [FilterValue(value=doc["_id"], count=doc["count"]) for doc in docs if doc.get("_id") is not None]
        if values:
            result[key] = values
    return result if result else None


# ── Cache-hit flat pipeline ──

def _build_cache_hit_pipeline(
    match_query: Optional[Dict[str, Any]],
    price_match: Optional[Dict[str, Any]],
    sort_specs: List[tuple],
    skip: int,
    limit: int,
) -> List[Dict]:
    """Flat pipeline used when stats/filters come from cache.

    Always starts with {show: True}. Appends user price filter if present.
    $project is placed last — it only runs on the final `limit` documents.
    Total count is read from the cache document, not computed here.
    """
    pipeline: List[Dict] = []

    # Collect clauses: base show flag, user filters (excluding price), then price
    match_clauses: List[Dict] = [{"show": True}]
    if match_query:
        match_clauses += [c for c in match_query["$and"] if "derived.price" not in c and c != {"show": True}]

    user_cond = (price_match or {}).get("derived.price", {})
    eff_price: Dict[str, Any] = {}
    if "$gte" in user_cond:
        eff_price["$gte"] = user_cond["$gte"]
    if "$lte" in user_cond:
        eff_price["$lte"] = user_cond["$lte"]
    if eff_price:
        match_clauses.append({"derived.price": eff_price})

    if len(match_clauses) > 1:
        pipeline.append({"$match": {"$and": match_clauses}})
    else:
        pipeline.append({"$match": match_clauses[0]})

    pipeline.append({"$sort": dict(sort_specs)})
    pipeline.append({"$skip": skip})
    pipeline.append({"$limit": limit})
    pipeline.append({"$project": _PIPELINE_PROJECTION})
    return pipeline


# ── Cache reconstruction helpers ──

def _stats_from_cache(cache_doc: Dict[str, Any]) -> Optional[Stats]:
    raw = cache_doc.get("stats")
    return Stats.model_validate(raw) if raw else None


def _base_stats_from_cache(cache_doc: Dict[str, Any]) -> Optional[Stats]:
    raw = cache_doc.get("baseStats")
    return Stats.model_validate(raw) if raw else None


def _filters_from_cache(cache_doc: Dict[str, Any]) -> Optional[Dict[str, List[FilterValue]]]:
    raw = cache_doc.get("availableFilters")
    if not raw:
        return None
    return {
        k: [FilterValue.model_validate(fv) for fv in vs]
        for k, vs in raw.items()
    }


@router.post("/ebay/items", response_model=EbayItemsResponse)
async def ebay_items(request: Request, payload: EbayItemsRequest):
    db = request.app.state.db
    collection = None
    if payload.name == "MacBookPro":
        collection = db["mac_book_pro"]
    elif payload.name == "MacBookAir":
        collection = db["mac_book_air"]
    if collection is None:
        raise HTTPException(status_code=404, detail="Model collection not found")

    skip = max(payload.skip, 0)
    limit = min(max(payload.limit, 1), 100)
    is_first_page = skip == 0
    mongo_sort_specs = _compose_sort_specs(payload.sortSpecs)

    match_query = _compose_query(payload.filter, exclude_price=True)
    #print("Match query:", json.dumps(match_query, indent=2))  # Debug log
    price_match = _build_price_match(payload.filter)

    # ── Stats/filter cache lookup (all pages) ──
    cache_col = STATS_CACHE_MAP.get(payload.name)
    fhash = filter_hash(payload.filter)
    cache_doc = await get_valid_cache(db, cache_col, fhash)

    if cache_doc:
        # ── Cache hit: flat pipeline, no $facet, total from cache ──
        await increment_hits(db, cache_col, fhash)
        pipeline = _build_cache_hit_pipeline(
            match_query, price_match, mongo_sort_specs, skip, limit
        )
        print("Aggregation pipeline (cache hit):", json.dumps(pipeline, indent=2))  # Debug log
        docs = await collection.aggregate(pipeline).to_list(None)
        items = [_document_to_ebay_item(doc) for doc in docs]
        total = cache_doc["totalCount"]
        stats = _stats_from_cache(cache_doc) if is_first_page else None
        base_stats = _base_stats_from_cache(cache_doc) if is_first_page else None
        available_filters = _filters_from_cache(cache_doc) if is_first_page else None
    else:
        # ── Cache miss or page 2+: $facet pipeline ──
        pipeline = _build_aggregation_pipeline(
            match_query, mongo_sort_specs, skip, limit, is_first_page, price_match
        )
        print("Aggregation pipeline:", json.dumps(pipeline, indent=2))  # Debug log
        facet_result = (await collection.aggregate(pipeline).to_list(None))[0]

        total_docs = facet_result.get("totalCount", [])
        total = total_docs[0]["n"] if total_docs else 0
        items = [_document_to_ebay_item(doc) for doc in facet_result.get("items", [])]

        stats = None
        base_stats = None
        available_filters = None
        if is_first_page:
            filter_keys = (
                list(LLM_SPEC_FIELD_MAP.keys()) +
                ANALYSIS_FILTER_FIELDS +
                LLM_FIELDS +
                ["returnable", "returnShippingCostPayer", "condition"]
            )
            available_filters = _parse_available_filters(facet_result, filter_keys)
            if price_match:
                base_price_bins = _parse_price_bins(facet_result.get("basePriceBins", []))
                stats = _parse_stats_from_facet(facet_result.get("stats", []), base_price_bins)
                base_stats = _parse_stats_from_facet(facet_result.get("baseStats", []))
            else:
                price_bins = _parse_price_bins(facet_result.get("priceBins", []))
                stats = _parse_stats_from_facet(facet_result.get("stats", []), price_bins)
            if cache_col and fhash is not None:
                await store_cache(
                    db, cache_col, fhash, payload.filter, payload.name,
                    total, stats, base_stats, available_filters,
                )

    # Look up EPN campaign ID only when items exist (graceful degradation if not found)
    campaign_doc = await db["campaigns"].find_one({"name": payload.name})
    raw_id = campaign_doc.get("campaignId") if campaign_doc else None
    campaign_id: Optional[str] = str(raw_id) if raw_id is not None else None

    if campaign_id:
        for item in items:
            if item.details and item.details.itemWebUrl:
                item.details.itemWebUrl = _build_epn_url(item.details.itemWebUrl, campaign_id)

    return EbayItemsResponse(
        items=items,
        stats=stats,
        baseStats=base_stats,
        availableFilters=available_filters,
        pagination=Pagination(skip=skip, limit=limit, total=total),
    )
