import copy
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from models import EbayFilterValuesRequest, EbayFilterValuesResponse, EbayItem, EbayItemsRequest, EbayItemsResponse, Stats
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

# MongoDB connection setup
client = MongoClient("mongodb://localhost:27017/")
db = client["mybaydb"]
researches_collection = db["researches"]


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

def _compose_query(filter_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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
    for derived_field in [
        "release_year",
        "laptop_model",
        "model_number",
        "model_id",
        "part_number",
        "cpu_model",
        "cpu_family",
        "cpu_speed",
        "ssd_size",
        "screen_size",
        "ram_size",
        "color",
        "specs_conflict"
    ]:
        if value := filter_data.get(derived_field):
            _append_derived_or_variant_filter(derived_field, value)
    
    # llm_derived fields
    for llm_field in [
        "charger",
        "battery",
        "screen",
        "keyboard",
        "housing",
        "audio",
        "ports",
        "functionality",
        "component_listing"
    ]:
        if value := filter_data.get(llm_field):
            query["$and"].append({f"llm_derived.{llm_field}": {"$in": value if isinstance(value, list) else [value]}})

    # details fields
    if value := filter_data.get("returnable"):
        query["$and"].append({"details.returnTerms.returnsAccepted": {"$in": value}})
        
    if value := filter_data.get("condition"):
        query["$and"].append({"details.condition": {"$in": value}})
    
    return query if query["$and"] else None

def _available_filter_values(docs: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    derived_fields = [
        "release_year",
        "laptop_model",
        "model_number",
        "model_id",
        "part_number",
        "cpu_model",
        "cpu_family",
        "cpu_speed",
        "ssd_size",
        "screen_size",
        "ram_size",
        "color",
        "specs_conflict"
    ]
    llm_fields = [
        "charger",
        "battery",
        "screen",
        "keyboard",
        "housing",
        "audio",
        "ports",
        "functionality",
        "component_listing"
    ]
    details_fields = [
        "returnable",
        "condition"
    ]
    target_fields = derived_fields + llm_fields + details_fields
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
        llm_derived = doc.get("llm_derived") or {}
        details = doc.get("details") or {}
        for field in derived_fields:
            _collect(field, derived.get(field))
        for field in llm_fields:
            _collect(field, llm_derived.get(field))
        _collect("returnable", details.get("returnTerms", {}).get("returnsAccepted"))
        _collect("condition", details.get("condition"))
        
        for variant_entry in derived.get("variants") or []:
            if variant_entry["distance"] > 1:
                continue
            variant_data = variant_entry.get("variant")
            if isinstance(variant_data, dict):
                for field in derived_fields:
                    if not derived.get(field):
                        _collect(field, variant_data.get(field))

        for field, counts in value_counts.items():
            for val in doc_values[field]:
                counts[val] = counts.get(val, 0) + 1

    return {
        field: [
            {"value": val, "count": count}
            for val, count in sorted(counts.items(), key=lambda item: str(item[0]))
        ]
        for field, counts in value_counts.items()
        if counts
    }

def _compose_sort_specs(sort_specs: Optional[List[Dict[str, Any]]]) -> List[tuple[str, int]]:
    
    derived_fields = [
        "price",
        "release_year",
        "laptop_model",
        "model_number",
        "model_id",
        "part_number",
        "cpu_model",
        "cpu_family",
        "cpu_speed",
        "ssd_size",
        "screen_size",
        "ram_size",
        "color",
        "specs_conflict"
    ]
    llm_fields = [
        "charger",
        "battery",
        "screen",
        "keyboard",
        "housing",
        "audio",
        "ports",
        "functionality",
        "component_listing"
    ]
    details_fields = [
        "returnable",
        "condition"
    ]
    
    default = [("derived.price", 1)]
    mongo_sort_specs = []
    for spec in sort_specs:
        field = spec.get("field")
        if field in derived_fields:
            mongo_sort_specs.append((f"derived.{field}", spec.get("direction", 1)))
        elif field in llm_fields:
            mongo_sort_specs.append((f"llm_derived.{field}", spec.get("direction", 1)))
        elif field in details_fields:
            if field == "returnable":
                mongo_sort_specs.append((f"details.returnTerms.returnsAccepted", spec.get("direction", 1)))
            else:
                mongo_sort_specs.append((f"details.{field}", spec.get("direction", 1)))
    if mongo_sort_specs:
        return mongo_sort_specs
    else:
        return default

@app.post("/ebay/items", response_model=EbayItemsResponse)
def ebay_items(request: EbayItemsRequest):
    try:
        collection = None
        if request.name == "MacBookPro":
            collection = db["mac_book_pro"]
        if collection is None:
            raise HTTPException(status_code=404, detail="Model collection not found")
       
        all_items = []
        mongo_sort_specs = _compose_sort_specs(request.sort_specs)
        if not request.filter:
            for doc in collection.find().sort(mongo_sort_specs):
                all_items.append(doc)
        else:
            query = _compose_query(request.filter) or {}
            for doc in collection.find(query).sort(mongo_sort_specs):
                all_items.append(doc)
        
        # Sort and paginate
        #all_items = sorted(all_items, key=lambda x: x.get("itemId"))
        available_filters = _available_filter_values(all_items)
        skip = max(request.skip, 0)
        limit = min(max(request.limit, 1), 100)
        paginated_items = all_items[skip:skip+limit]
        items = [_document_to_ebay_item(item) for item in paginated_items]
        
        prices = [item["derived"]["price"] for item in all_items if item["derived"] and item["derived"]["price"] is not None]
        stats = Stats(
            min=min(prices) if prices else None,
            max=max(prices) if prices else None,
            median=(sorted(prices)[len(prices)//2] if len(prices) % 2 == 1 else
                    (sorted(prices)[len(prices)//2 - 1] + sorted(prices)[len(prices)//2]) / 2) if prices else None,
            mean=(sum(prices) / len(prices)) if prices else None,
            count=len(prices) if prices else None,
        )
        
        return EbayItemsResponse(
            items=items,
            stats=stats,
            available_filters=available_filters or None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ebay/filter_values", response_model=EbayFilterValuesResponse)
def ebay_filter_values(request: EbayFilterValuesRequest):
    try:
        collection = None
        if request.name == "MacBookPro":
            collection = db["mac_book_pro"]
        if collection is None:
            raise HTTPException(status_code=404, detail="Model collection not found")
       
        all_items = []
        
        for doc in collection.find():
            all_items.append(doc)
        
        available_filters = _available_filter_values(all_items)
        
        return EbayFilterValuesResponse(
            available_filters=available_filters or None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



