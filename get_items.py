import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from models import EbayItemsRequest, EbayItemsResponse, FilterValue, Pagination, PriceBucket, SortSpecRequest, Stats

#import mongo
from util import _document_to_ebay_item

router = APIRouter()

# ── Shared field lists ──
# LLM spec filter key → MongoDB llmSpecs path
LLM_SPEC_FIELD_MAP: Dict[str, str] = {
    "productLine": "llmSpecs.productLine",
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
    "charger", "battery", "screen", "keyboard", "housing",
    "audio", "ports", "functionality", "componentListing", "subject",
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

# Spec filter keys that have bestGuess fallback in llmAnalysis.specsAnalysis
BEST_GUESS_FIELDS = [
    "releaseYear", "cpuFamily", "screenSize", "ramSize", "ssdSize",
]

# Hard price cap per product — items above this price are excluded from all results
PRICE_CAP = {
    "MacBookPro": 3000,
    "MacBookAir": 1500,
}

# Fixed $100 bucket boundaries for price histograms (0, 100, ..., 3000)
PRICE_BUCKET_BOUNDARIES = list(range(0, 3100, 100))

# Projection applied after $match and before $facet.
# Only fields consumed by $facet branches (facets, stats, sort) or the frontend
# (EbayItem model) are included. Fields marked "sort only" or "facet only" are
# not in the model but must be in the pipeline for MongoDB to use them.
_PIPELINE_PROJECTION: Dict[str, int] = {
    "_id": 1,
    "itemId": 1,
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


def _compose_query(filter_data: Optional[Dict[str, Any]], exclude_price: bool = False) -> Optional[Dict[str, Any]]:
    if not filter_data:
        return None
    query: Dict[str, Any] = {"$and": []}

    def _append_llm_spec_or_bestguess_filter(filter_key: str, raw_value: Any) -> None:
        values = list(raw_value) if isinstance(raw_value, list) else [raw_value]
        mongo_path = LLM_SPEC_FIELD_MAP[filter_key]
        if filter_key in BEST_GUESS_FIELDS:
            query["$and"].append(
                {
                    "$or": [
                        {mongo_path: {"$in": values}},
                        {f"llmAnalysis.specsAnalysis.{filter_key}.bestGuess": {"$in": values}},
                    ]
                }
            )
        else:
            query["$and"].append({mongo_path: {"$in": values}})

    # llmSpecs fields (with bestGuess fallback from llmAnalysis for main specs)
    for filter_key in LLM_SPEC_FIELD_MAP:
        value = filter_data.get(filter_key)
        if value is not None and value != []:
            _append_llm_spec_or_bestguess_filter(filter_key, value)

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

    return query if query["$and"] else None


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


def _bestguess_array_facet(llm_path: str, guess_path: str, price_match: Optional[Dict[str, Any]] = None) -> List[Dict]:
    steps: List[Dict] = []
    if price_match:
        steps.append({"$match": price_match})
    steps.append({
        "$addFields": {
            "_combined": {
                "$setUnion": [
                    {"$ifNull": [f"${llm_path}", []]},
                    {"$ifNull": [f"${guess_path}", []]},
                ]
            }
        }
    })
    steps.append({"$unwind": "$_combined"})
    steps.append({"$group": {"_id": "$_combined", "count": {"$sum": 1}}})
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
    for field in BEST_GUESS_FIELDS:
        llm_path = LLM_SPEC_FIELD_MAP[field]
        guess_path = f"llmAnalysis.specsAnalysis.{field}.bestGuess"
        facets[field] = _bestguess_array_facet(llm_path, guess_path, price_match)
    for field in LLM_SPEC_FIELD_MAP:
        if field not in BEST_GUESS_FIELDS:
            facets[field] = _array_field_facet(LLM_SPEC_FIELD_MAP[field], price_match)
    for field in ANALYSIS_FILTER_FIELDS:
        facets[field] = _scalar_field_facet(f"llmAnalysis.{field}", price_match)
    for field in LLM_FIELDS:
        facets[field] = _scalar_field_facet(f"llmDerived.{field}", price_match)
    facets["returnable"] = _scalar_field_facet("details.returnTerms.returnsAccepted", price_match)
    facets["returnShippingCostPayer"] = _scalar_field_facet("details.returnTerms.returnShippingCostPayer", price_match)
    facets["condition"] = _scalar_field_facet("details.condition", price_match)
    return facets


def _build_aggregation_pipeline(
    match_query: Optional[Dict[str, Any]],
    sort_specs: List[tuple],
    skip: int,
    limit: int,
    is_first_page: bool,
    price_match: Optional[Dict[str, Any]],
) -> List[Dict]:
    pipeline: List[Dict] = []
    if match_query:
        pipeline.append({"$match": match_query})
    pipeline.append({"$project": _PIPELINE_PROJECTION})
    facet: Dict[str, List[Dict]] = {}
    facet["totalCount"] = _count_facet(price_match)
    facet["items"] = _items_facet(sort_specs, skip, limit, price_match)
    if is_first_page:
        if price_match:
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

    # Outer $match: non-price filters + price cap (NEVER includes user price range)
    match_query = _compose_query(payload.filter, exclude_price=True)
    price_cap = PRICE_CAP.get(payload.name)
    if price_cap is not None:
        cap_condition = {"derived.price": {"$lt": price_cap}}
        if match_query:
            match_query["$and"].append(cap_condition)
        else:
            match_query = {"$and": [cap_condition]}

    # Price range applied within facet branches only
    price_match = _build_price_match(payload.filter)

    pipeline = _build_aggregation_pipeline(match_query, mongo_sort_specs, skip, limit, is_first_page, price_match)
    print("Aggregation pipeline:", json.dumps(pipeline, indent=2))  # Debug log for pipeline
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

    return EbayItemsResponse(
        items=items,
        stats=stats,
        baseStats=base_stats,
        availableFilters=available_filters,
        pagination=Pagination(skip=skip, limit=limit, total=total),
    )
