import copy
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from models import EbayItem, EbayItemsByIdsRequest, EbayItemsByIdsResponse, EbayItemsRequest, EbayItemsResponse, Pagination, PriceBucket, SortSpecRequest, Stats, ErrorDetail, ErrorEnvelope, ErrorResponse
from pymongo import MongoClient

app = FastAPI()
# Add CORS middleware to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        ErrorDetail(
            loc=list(err.get("loc", [])),
            msg=err.get("msg", ""),
            type=err.get("type", ""),
        )
        for err in exc.errors()
    ]
    body = ErrorResponse(
        error=ErrorEnvelope(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=details,
        )
    )
    return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    body = ErrorResponse(
        error=ErrorEnvelope(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
        )
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    body = ErrorResponse(
        error=ErrorEnvelope(
            code="INTERNAL_ERROR",
            message=str(exc),
        )
    )
    return JSONResponse(status_code=500, content=body.model_dump())


# MongoDB connection setup
client = MongoClient("mongodb://localhost:27017/")
db = client["mybaydb"]

# ── Shared field lists ──
# Base derived fields used for filtering
DERIVED_FILTER_FIELDS = [
    "releaseYear", "laptopModel", "modelNumber", "modelId", "partNumber",
    "cpuModel", "cpuFamily", "cpuSpeed", "ssdSize", "screenSize", "ramSize",
    "color", "specsConflict", "specsQuality",
]
# Sort/available-filter adds price and minDistance
DERIVED_SORT_FIELDS = DERIVED_FILTER_FIELDS + ["price", "minDistance"]

LLM_FIELDS = [
    "charger", "battery", "screen", "keyboard", "housing",
    "audio", "ports", "functionality", "componentListing",
]

DETAILS_FIELDS = ["returnable", "condition"]

RANK_SORT_MAP = {
    "screen": "llmDerived.screenRank",
    "keyboard": "llmDerived.keyboardRank",
    "housing": "llmDerived.housingRank",
    "audio": "llmDerived.audioRank",
    "ports": "llmDerived.portsRank",
    "battery": "llmDerived.batteryRank",
    "functionality": "llmDerived.functionalityRank",
    "charger": "llmDerived.chargerRank",
    "componentListing": "llmDerived.componentListingRank",
    "condition": "derived.conditionRank",
    "specsQuality": "derived.specsQualityRank",
}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Hello"}


# About page route
@app.get("/about")
def about() -> dict[str, str]:
    return {"message": "This is the about page."}

def _document_to_ebay_item(doc: dict[str, Any]) -> EbayItem:
    model_fields = getattr(EbayItem, "model_fields", None)
    allowed_fields = set(model_fields.keys()) if model_fields else set(getattr(EbayItem, "__fields__", {}).keys())
    merged = doc
    payload = merged if not allowed_fields else {k: v for k, v in merged.items() if k in allowed_fields}
    
    try:
        ebay_item = EbayItem.model_validate(payload)
    except ValidationError as e:
        error_details = e.errors()
        missing_fields = []
        for error in error_details:
            # Check if the error type is 'value_error.missing'
            if error['type'] == 'value_error.missing' or error['msg'] == 'Field required':
                # The location ('loc') is a tuple, the last element is the field name
                field_name = error['loc'][-1]
                missing_fields.append(field_name)

        print(f"Missing fields: {missing_fields}")
        raise HTTPException(status_code=400, detail=str(e))
    return ebay_item

def _compose_query(filter_data: Optional[Dict[str, Any]], exclude_price: bool = False) -> Optional[Dict[str, Any]]:
    if not filter_data:
        return None
    query: Dict[str, Any] = {"$and": []}

    def _append_derived_or_variant_filter(field_name: str, raw_value: Any) -> None:
        values = (
            list(raw_value)
            if isinstance(raw_value, Iterable) and not isinstance(raw_value, (str, bytes, bytearray))
            else [raw_value]
        )
        query["$and"].append(
            {
                "$or": [
                    {f"derived.{field_name}": {"$in": values}},
                    {
                        "$and": [
                            {f"derived.{field_name}": {"$nin": values}},
                            {
                                "derived.variants": {
                                    "$elemMatch": {
                                        "distance": {"$lte": 1},
                                        f"variant.{field_name}": {"$in": values},
                                    }
                                }
                            },
                        ]
                    },
                ]
            }
        )

    # derived and variant fields
    for derived_field in DERIVED_FILTER_FIELDS:
        value = filter_data.get(derived_field)
        if value is not None and value != []:
            _append_derived_or_variant_filter(derived_field, value)

    # llmDerived fields
    for llm_field in LLM_FIELDS:
        value = filter_data.get(llm_field)
        if value is not None and value != []:
            query["$and"].append({f"llmDerived.{llm_field}": {"$in": value if isinstance(value, list) else [value]}})

    # details fields
    value = filter_data.get("returnable")
    if value is not None and value != []:
        query["$and"].append({"details.returnTerms.returnsAccepted": {"$in": value}})

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

def _compute_stats(prices: List[float], price_buckets: Optional[List[PriceBucket]] = None) -> Optional[Stats]:
    if not prices:
        return None
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    median = sorted_prices[n // 2] if n % 2 == 1 else (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2
    return Stats(
        min=sorted_prices[0],
        max=sorted_prices[-1],
        median=median,
        mean=sum(sorted_prices) / n,
        count=n,
        priceBuckets=price_buckets,
    )

def _compute_price_buckets(prices: List[float]) -> Optional[List[PriceBucket]]:
    if len(prices) < 3:
        return None
    import math
    price_max = max(prices)
    # Fixed $100 buckets: $1-$100, $101-$200, etc.
    num_buckets = math.ceil(price_max / 100)
    buckets = []
    for i in range(num_buckets):
        range_min = i * 100 + 1 if i > 0 else 1
        range_max = (i + 1) * 100
        count = sum(1 for p in prices if range_min <= p <= range_max)
        buckets.append(PriceBucket(rangeMin=range_min, rangeMax=range_max, count=count))
    return buckets

def _available_filter_values(docs: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    target_fields = DERIVED_SORT_FIELDS + LLM_FIELDS + DETAILS_FIELDS
    value_counts: Dict[str, Dict[Any, int]] = {field: {} for field in target_fields}

    for doc in docs:
        doc_values: Dict[str, set[Any]] = {field: set() for field in target_fields}

        def _collect(field: str, raw_value: Any) -> None:
            if raw_value is None:
                return

            def _add(val: Any) -> None:
                if val is not None:
                    doc_values[field].add(val)

            if isinstance(raw_value, Iterable) and not isinstance(raw_value, (str, bytes, bytearray)):
                for item in raw_value:
                    _add(item)
            else:
                _add(raw_value)

        derived = doc.get("derived") or {}
        llmDerived = doc.get("llmDerived") or {}
        details = doc.get("details") or {}
        for field in DERIVED_SORT_FIELDS:
            _collect(field, derived.get(field))
        for field in LLM_FIELDS:
            _collect(field, llmDerived.get(field))
        _collect("returnable", details.get("returnTerms", {}).get("returnsAccepted"))
        _collect("condition", details.get("condition"))

        for variant_entry in derived.get("variants") or []:
            if variant_entry["distance"] > 1:
                continue
            variant_data = variant_entry.get("variant")
            if isinstance(variant_data, dict):
                for field in DERIVED_SORT_FIELDS:
                    if not derived.get(field):
                        _collect(field, variant_data.get(field))

        for field, counts in value_counts.items():
            for val in doc_values[field]:
                counts[val] = counts.get(val, 0) + 1

    return {
        field: [
            {"value": val, "count": count}
            for val, count in sorted(counts.items(), key=lambda item: (isinstance(item[0], str), item[0]))
        ]
        for field, counts in value_counts.items()
        if counts
    }

def _compose_sort_specs(sort_specs: Optional[List[SortSpecRequest]]) -> List[tuple[str, int]]:
    default = [("derived.price", 1)]
    if not sort_specs:
        return default
    mongo_sort_specs = []
    for spec in sort_specs:
        field = spec.field
        direction = spec.direction
        if field in RANK_SORT_MAP:
            mongo_sort_specs.append((RANK_SORT_MAP[field], direction))
        elif field in DERIVED_SORT_FIELDS:
            mongo_sort_specs.append((f"derived.{field}", direction))
        elif field in LLM_FIELDS:
            mongo_sort_specs.append((f"llmDerived.{field}", direction))
        elif field in DETAILS_FIELDS:
            if field == "returnable":
                mongo_sort_specs.append(("details.returnTerms.returnsAccepted", direction))
            else:
                mongo_sort_specs.append((f"details.{field}", direction))
    if mongo_sort_specs:
        return mongo_sort_specs
    else:
        return default

# Hard price cap per product — items above this price are excluded from all results
PRICE_CAP = {
    "MacBookPro": 3000,
}


@app.get("/ebay/search-templates")
def get_search_templates(productName: str = Query(...)):
    collection = db["search_templates"]
    docs = list(collection.find({"productName": productName}, {"_id": 0}))
    return docs


@app.post("/ebay/items", response_model=EbayItemsResponse)
def ebay_items(request: EbayItemsRequest):
    collection = None
    if request.name == "MacBookPro":
        collection = db["mac_book_pro"]
    if collection is None:
        raise HTTPException(status_code=404, detail="Model collection not found")

    mongo_sort_specs = _compose_sort_specs(request.sortSpecs)

    # Build query with all filters (including price) for items/stats/availableFilters
    query = _compose_query(request.filter) if request.filter else None

    # Apply per-product price cap globally
    price_cap = PRICE_CAP.get(request.name)
    if price_cap is not None:
        cap_condition = {"derived.price": {"$lte": price_cap}}
        if query and "$and" in query:
            query["$and"].append(cap_condition)
        else:
            query = {"$and": [cap_condition]} if query is None else {"$and": [query, cap_condition]}

    all_items = list(collection.find(query or {}).sort(mongo_sort_specs))

    skip = max(request.skip, 0)
    limit = min(max(request.limit, 1), 100)
    paginated_items = all_items[skip:skip+limit]
    items = [_document_to_ebay_item(item) for item in paginated_items]

    # Only compute stats, availableFilters, and priceBuckets for page 1 (skip == 0)
    if skip == 0:
        available_filters = _available_filter_values(all_items)
        prices = [float(item["derived"]["price"]) for item in all_items if item.get("derived") and item["derived"].get("price") is not None]

        # Dual filter pass: priceBuckets and baseStats from non-price-filtered items
        has_price_filter = request.filter and (request.filter.get("minPrice") is not None or request.filter.get("maxPrice") is not None)
        if has_price_filter:
            non_price_query = _compose_query(request.filter, exclude_price=True)
            # Apply price cap to non-price query too
            if price_cap is not None:
                cap_condition = {"derived.price": {"$lte": price_cap}}
                if non_price_query and "$and" in non_price_query:
                    non_price_query["$and"].append(cap_condition)
                else:
                    non_price_query = {"$and": [cap_condition]} if non_price_query is None else {"$and": [non_price_query, cap_condition]}
            non_price_items = list(collection.find(non_price_query or {}))
        else:
            non_price_items = all_items

        non_price_prices = [
            float(item["derived"]["price"])
            for item in non_price_items
            if item.get("derived") and item["derived"].get("price") is not None
        ]

        price_buckets = _compute_price_buckets(non_price_prices) if non_price_prices else None
        stats = _compute_stats(prices, price_buckets)

        # baseStats: pre-price-filter stats for price color coding
        if has_price_filter:
            base_stats = _compute_stats(non_price_prices)
        else:
            base_stats = None
    else:
        available_filters = None
        stats = None
        base_stats = None

    return EbayItemsResponse(
        items=items,
        stats=stats,
        baseStats=base_stats,
        availableFilters=available_filters or None,
        pagination=Pagination(skip=skip, limit=limit, total=len(all_items)),
    )


@app.post("/ebay/items/by-ids", response_model=EbayItemsByIdsResponse)
def ebay_items_by_ids(request: EbayItemsByIdsRequest):
    collection = None
    if request.name == "MacBookPro":
        collection = db["mac_book_pro"]
    if collection is None:
        raise HTTPException(status_code=404, detail="Model collection not found")

    if not request.itemIds:
        return EbayItemsByIdsResponse(items=[])

    docs = list(collection.find({"itemId": {"$in": request.itemIds}}))
    items = [_document_to_ebay_item(doc) for doc in docs]
    return EbayItemsByIdsResponse(items=items)
