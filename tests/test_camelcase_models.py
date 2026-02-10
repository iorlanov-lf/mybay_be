"""Tests verifying Pydantic models and API helpers use camelCase field names."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from models import (
    DerivedData, LlmDerived, EbayItem, EbayItemsRequest,
    EbayItemsResponse, EbayFilterValuesResponse, VariantSpec,
    ItemDetails, Stats, ErrorDetail, ErrorEnvelope, ErrorResponse,
    SortSpecRequest,
)
from main import _compose_query, _compose_sort_specs, _available_filter_values


def _ss(field: str, direction: int = 1) -> SortSpecRequest:
    """Shorthand to build a SortSpecRequest for tests."""
    return SortSpecRequest(field=field, direction=direction)


# ── Model serialization tests ──

def test_derived_data_json_keys_are_camelcase():
    """DerivedData model_dump keys should be camelCase."""
    d = DerivedData(
        laptopModel=["MacBook Pro"],
        releaseYear=["2017"],
        screenSize=[15.4],
        ramSize=[16],
        ssdSize=[512],
        cpuModel=["i7-7820HQ"],
        cpuFamily=["i7"],
        cpuSpeed=[2.9],
        modelNumber=["A1707"],
        modelId=["MacBookPro14,3"],
        partNumber=["MPTR2LL/A"],
        color=["Space Gray"],
        specsConflict=False,
        minDistance=0.0,
        specsQuality="single match",
    )
    data = d.model_dump()
    for key in data:
        if key in {"description", "color", "variants", "missing", "price"}:
            continue
        assert "_" not in key, f"DerivedData key '{key}' is not camelCase"


def test_llm_derived_json_keys():
    """LlmDerived should have componentListing field."""
    llm = LlmDerived(
        charger="Y", battery="G", screen="G",
        keyboard="G", housing="G", audio="G",
        ports="G", functionality="L",
        componentListing="N",
    )
    data = llm.model_dump()
    assert "componentListing" in data
    assert "component_listing" not in data


def test_llm_derived_return_alias():
    """LlmDerived 'return' field via alias works."""
    llm = LlmDerived(**{"return": "Y"})
    data = llm.model_dump(by_alias=True)
    assert "return" in data
    assert data["return"] == "Y"


def test_ebay_item_camelcase_fields():
    """EbayItem top-level fields should be camelCase."""
    now = datetime.now(timezone.utc)
    item = EbayItem(
        itemId="123",
        details=ItemDetails(title="Test"),
        insertedAt=now,
        updatedAt=now,
        processedAt=now,
        derived=DerivedData(),
        llmDerived=LlmDerived(),
    )
    data = item.model_dump()
    assert "insertedAt" in data
    assert "updatedAt" in data
    assert "processedAt" in data
    assert "llmDerived" in data
    assert "inserted_at" not in data
    assert "updated_at" not in data
    assert "processed_at" not in data
    assert "llm_derived" not in data


def test_ebay_items_request_sort_specs():
    """EbayItemsRequest should use sortSpecs."""
    req = EbayItemsRequest(name="MacBookPro", sortSpecs=[{"field": "price", "direction": 1}])
    data = req.model_dump()
    assert "sortSpecs" in data
    assert "sort_specs" not in data


def test_ebay_items_response_available_filters():
    """EbayItemsResponse should use availableFilters."""
    resp = EbayItemsResponse(
        items=[],
        stats=Stats(),
        availableFilters={"releaseYear": [{"value": "2017", "count": 5}]},
    )
    data = resp.model_dump()
    assert "availableFilters" in data
    assert "available_filters" not in data


def test_ebay_filter_values_response_available_filters():
    """EbayFilterValuesResponse should use availableFilters."""
    resp = EbayFilterValuesResponse(availableFilters=None)
    data = resp.model_dump()
    assert "availableFilters" in data
    assert "available_filters" not in data


def test_variant_spec_camelcase():
    """VariantSpec fields should be camelCase."""
    v = VariantSpec(
        releaseYear="2017",
        modelName="MacBook Pro (15-inch, 2017)",
        modelId="MacBookPro14,3",
        modelNumber="A1707",
        screenSize=15.4,
        partNumber="MPTR2LL/A",
        cpuCores=4,
        cpuModel="i7-7700HQ",
        cpuSpeed=2.8,
        ssdSize=[256, 512],
        ramSize=[16],
    )
    data = v.model_dump()
    for key in data:
        if key == "color":
            continue
        assert "_" not in key, f"VariantSpec key '{key}' is not camelCase"


# ── Query/filter helper tests ──

def test_compose_query_uses_camelcase_derived_paths():
    """_compose_query should use derived.releaseYear etc. paths."""
    query = _compose_query({"releaseYear": ["2017"]})
    query_str = str(query)
    assert "derived.releaseYear" in query_str
    assert "derived.release_year" not in query_str


def test_compose_query_uses_llmDerived_path():
    """_compose_query should use llmDerived.* paths."""
    query = _compose_query({"componentListing": ["N"]})
    query_str = str(query)
    assert "llmDerived.componentListing" in query_str
    assert "llm_derived" not in query_str


def test_compose_sort_specs_derived_path():
    """_compose_sort_specs should produce derived.releaseYear paths."""
    specs = _compose_sort_specs([_ss("releaseYear", -1)])
    assert specs == [("derived.releaseYear", -1)]


def test_compose_sort_specs_llm_path():
    """_compose_sort_specs should produce rank paths for categorical LLM fields."""
    specs = _compose_sort_specs([_ss("componentListing")])
    assert specs == [("llmDerived.componentListingRank", 1)]


def test_available_filter_values_uses_camelcase_keys():
    """_available_filter_values should return camelCase field names as keys."""
    docs = [
        {
            "derived": {
                "releaseYear": ["2017"],
                "laptopModel": ["MacBook Pro"],
                "color": ["Silver"],
                "variants": [],
            },
            "llmDerived": {"componentListing": "N", "charger": "Y"},
            "details": {"condition": "Good - Refurbished"},
        }
    ]
    result = _available_filter_values(docs)
    # camelCase keys should be present
    assert "releaseYear" in result
    assert "laptopModel" in result
    assert "componentListing" in result
    # snake_case keys should NOT be present
    assert "release_year" not in result
    assert "laptop_model" not in result
    assert "component_listing" not in result


# ── Rank sort field tests (Story 1.9) ──

def test_compose_sort_specs_condition_uses_rank():
    """Sorting by condition should use derived.conditionRank."""
    specs = _compose_sort_specs([_ss("condition")])
    assert specs == [("derived.conditionRank", 1)]


def test_compose_sort_specs_battery_uses_rank():
    """Sorting by battery should use llmDerived.batteryRank."""
    specs = _compose_sort_specs([_ss("battery", -1)])
    assert specs == [("llmDerived.batteryRank", -1)]


def test_compose_sort_specs_screen_uses_rank():
    """Sorting by screen should use llmDerived.screenRank."""
    specs = _compose_sort_specs([_ss("screen")])
    assert specs == [("llmDerived.screenRank", 1)]


def test_compose_sort_specs_specs_quality_uses_rank():
    """Sorting by specsQuality should use derived.specsQualityRank."""
    specs = _compose_sort_specs([_ss("specsQuality")])
    assert specs == [("derived.specsQualityRank", 1)]


def test_compose_sort_specs_numeric_field_no_rank():
    """Numeric fields like price should NOT use rank paths."""
    specs = _compose_sort_specs([_ss("price")])
    assert specs == [("derived.price", 1)]


def test_compose_sort_specs_all_llm_rank_fields():
    """All 9 LLM categorical fields should map to rank paths."""
    llm_rank_fields = {
        "screen": "llmDerived.screenRank",
        "keyboard": "llmDerived.keyboardRank",
        "housing": "llmDerived.housingRank",
        "audio": "llmDerived.audioRank",
        "ports": "llmDerived.portsRank",
        "battery": "llmDerived.batteryRank",
        "functionality": "llmDerived.functionalityRank",
        "charger": "llmDerived.chargerRank",
        "componentListing": "llmDerived.componentListingRank",
    }
    for field, expected_path in llm_rank_fields.items():
        specs = _compose_sort_specs([_ss(field)])
        assert specs == [(expected_path, 1)], f"Field '{field}' should sort on '{expected_path}'"


# ── Sort functionality tests (Story 1.6) ──

def test_compose_sort_specs_default_none():
    """None sort_specs should default to price ascending."""
    specs = _compose_sort_specs(None)
    assert specs == [("derived.price", 1)]


def test_compose_sort_specs_default_empty_list():
    """Empty sort_specs list should default to price ascending."""
    specs = _compose_sort_specs([])
    assert specs == [("derived.price", 1)]


def test_compose_sort_specs_multiple_specs():
    """Multiple sort specs should produce a multi-field MongoDB sort list."""
    specs = _compose_sort_specs([_ss("price"), _ss("condition", -1)])
    assert specs == [("derived.price", 1), ("derived.conditionRank", -1)]


def test_compose_sort_specs_details_returnable():
    """Sorting by returnable should map to details.returnTerms.returnsAccepted."""
    specs = _compose_sort_specs([_ss("returnable")])
    assert specs == [("details.returnTerms.returnsAccepted", 1)]


def test_compose_sort_specs_unknown_field_fallback():
    """Unknown field should be ignored; if no valid fields, fall back to default."""
    specs = _compose_sort_specs([_ss("nonexistent")])
    assert specs == [("derived.price", 1)]


def test_compose_sort_specs_price_descending():
    """Price descending should produce derived.price with direction -1."""
    specs = _compose_sort_specs([_ss("price", -1)])
    assert specs == [("derived.price", -1)]


def test_derived_data_excludes_rank_fields():
    """DerivedData with extra=ignore should strip rank fields from API output."""
    d = DerivedData.model_validate({
        "price": 499.99,
        "specsQuality": "single match",
        "conditionRank": 8,
        "specsQualityRank": 1,
    })
    dumped = d.model_dump()
    assert "price" in dumped
    assert "specsQuality" in dumped
    assert "conditionRank" not in dumped
    assert "specsQualityRank" not in dumped


def test_llm_derived_excludes_rank_fields():
    """LlmDerived with extra=ignore should strip rank fields from API output."""
    d = LlmDerived.model_validate({
        "screen": "G",
        "battery": "F",
        "screenRank": 1,
        "batteryRank": 2,
    })
    dumped = d.model_dump()
    assert "screen" in dumped
    assert "battery" in dumped
    assert "screenRank" not in dumped
    assert "batteryRank" not in dumped


# ── Story 1.3: API envelope format tests ──

def test_ebay_items_response_stats_optional():
    """EbayItemsResponse should accept stats=None (page 2+ responses)."""
    resp = EbayItemsResponse(items=[], stats=None, availableFilters=None)
    data = resp.model_dump()
    assert data["stats"] is None
    assert data["availableFilters"] is None


def test_ebay_items_response_stats_present():
    """EbayItemsResponse should include stats when provided (page 1)."""
    resp = EbayItemsResponse(
        items=[],
        stats=Stats(min=100, max=500, median=300, mean=290, count=10),
        availableFilters={"releaseYear": [{"value": "2017", "count": 5}]},
    )
    data = resp.model_dump()
    assert data["stats"] is not None
    assert data["stats"]["count"] == 10
    assert data["availableFilters"] is not None


def test_error_response_validation_format():
    """ErrorResponse should serialize to { error: { code, message, details } }."""
    resp = ErrorResponse(
        error=ErrorEnvelope(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=[
                ErrorDetail(loc=["body", "name"], msg="Field required", type="missing"),
            ],
        )
    )
    data = resp.model_dump()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Request validation failed"
    assert len(data["error"]["details"]) == 1
    assert data["error"]["details"][0]["msg"] == "Field required"


def test_error_response_http_format():
    """ErrorResponse for HTTP errors should have code and message, no details."""
    resp = ErrorResponse(
        error=ErrorEnvelope(
            code="HTTP_404",
            message="Model collection not found",
        )
    )
    data = resp.model_dump()
    assert data["error"]["code"] == "HTTP_404"
    assert data["error"]["details"] is None


# ── Story 1.5: Price range filter tests ──

def test_compose_query_price_range_both():
    """_compose_query with minPrice and maxPrice produces $gte/$lte range."""
    query = _compose_query({"minPrice": 500, "maxPrice": 1000})
    assert query is not None
    price_cond = query["$and"][0]
    assert price_cond == {"derived.price": {"$gte": 500, "$lte": 1000}}


def test_compose_query_price_range_min_only():
    """_compose_query with minPrice only produces $gte without $lte."""
    query = _compose_query({"minPrice": 500})
    assert query is not None
    price_cond = query["$and"][0]
    assert price_cond == {"derived.price": {"$gte": 500}}
    assert "$lte" not in price_cond["derived.price"]


def test_compose_query_price_range_max_only():
    """_compose_query with maxPrice only produces $lte without $gte."""
    query = _compose_query({"maxPrice": 1000})
    assert query is not None
    price_cond = query["$and"][0]
    assert price_cond == {"derived.price": {"$lte": 1000}}
    assert "$gte" not in price_cond["derived.price"]


def test_compose_query_price_range_none():
    """_compose_query with both None produces no price condition."""
    query = _compose_query({"minPrice": None, "maxPrice": None})
    assert query is None
