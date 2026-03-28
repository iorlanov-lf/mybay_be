"""Tests verifying Pydantic models and API helpers use camelCase field names."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from models import (
    DerivedData, AnalysisData, LlmDerived, EbayItem, EbayItemsRequest,
    EbayItemsResponse,
    Pagination, VariantSpec,
    ItemDetails, PriceBucket, Stats, ErrorDetail, ErrorEnvelope, ErrorResponse,
    SortSpecRequest,
)
from get_items import _compose_query, _compose_sort_specs


def _ss(field: str, direction: int = 1) -> SortSpecRequest:
    """Shorthand to build a SortSpecRequest for tests."""
    return SortSpecRequest(field=field, direction=direction)


# ── Model serialization tests ──

def test_derived_data_json_keys_are_camelcase():
    """DerivedData model_dump keys should be camelCase (price, conditionRank only)."""
    d = DerivedData(
        price=499.99,
        conditionRank=6,
    )
    data = d.model_dump()
    assert "price" in data
    assert "conditionRank" in data
    for key in data:
        if key in {"price"}:
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
        pagination=Pagination(skip=0, limit=10, total=5),
    )
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
    """_compose_query should use specsFilter.releaseYear paths (not snake_case)."""
    query = _compose_query({"releaseYear": ["2017"]})
    query_str = str(query)
    assert "specsFilter.releaseYear" in query_str
    assert "derived.release_year" not in query_str
    assert "llmSpecs.release_year" not in query_str


def test_compose_query_uses_llmDerived_path():
    """_compose_query should use llmDerived.* paths."""
    query = _compose_query({"componentListing": ["N"]})
    query_str = str(query)
    assert "llmDerived.componentListing" in query_str
    assert "llm_derived" not in query_str


def test_compose_sort_specs_derived_path():
    """_compose_sort_specs should produce llmSpecs.releaseYear paths (not derived.*)."""
    specs = _compose_sort_specs([_ss("releaseYear", -1)])
    assert specs == [("llmSpecs.releaseYear", -1)]


def test_compose_sort_specs_llm_path():
    """_compose_sort_specs should produce rank paths for categorical LLM fields."""
    specs = _compose_sort_specs([_ss("subject")])
    assert specs == [("llmDerived.subjectRank", 1)]


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


def test_compose_sort_specs_specs_completeness_uses_rank():
    """Sorting by specsCompleteness should use llmAnalysis.specsCompletenessRank."""
    specs = _compose_sort_specs([_ss("specsCompleteness")])
    assert specs == [("llmAnalysis.specsCompletenessRank", 1)]


def test_compose_sort_specs_specs_consistency_uses_rank():
    """Sorting by specsConsistency should use llmAnalysis.specsConsistencyRank."""
    specs = _compose_sort_specs([_ss("specsConsistency")])
    assert specs == [("llmAnalysis.specsConsistencyRank", 1)]


def test_compose_sort_specs_numeric_field_no_rank():
    """Numeric fields like price should NOT use rank paths."""
    specs = _compose_sort_specs([_ss("price")])
    assert specs == [("derived.price", 1)]


def test_compose_sort_specs_all_llm_rank_fields():
    """All LLM categorical fields should map to rank paths."""
    llm_rank_fields = {
        "screen": "llmDerived.screenRank",
        "keyboard": "llmDerived.keyboardRank",
        "housing": "llmDerived.housingRank",
        "audio": "llmDerived.audioRank",
        "ports": "llmDerived.portsRank",
        "battery": "llmDerived.batteryRank",
        "functionality": "llmDerived.functionalityRank",
        "charger": "llmDerived.chargerRank",
        "subject": "llmDerived.subjectRank",
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


def test_compose_query_return_shipping_cost_payer():
    """_compose_query should filter on details.returnTerms.returnShippingCostPayer."""
    query = _compose_query({"returnShippingCostPayer": ["SELLER"]})
    query_str = str(query)
    assert "details.returnTerms.returnShippingCostPayer" in query_str


def test_compose_sort_specs_return_shipping_cost_payer():
    """Sorting by returnShippingCostPayer should map to details.returnTerms.returnShippingCostPayer."""
    specs = _compose_sort_specs([_ss("returnShippingCostPayer")])
    assert specs == [("details.returnTerms.returnShippingCostPayer", 1)]


def test_compose_sort_specs_unknown_field_fallback():
    """Unknown field should be ignored; if no valid fields, fall back to default."""
    specs = _compose_sort_specs([_ss("nonexistent")])
    assert specs == [("derived.price", 1)]


def test_compose_sort_specs_price_descending():
    """Price descending should produce derived.price with direction -1."""
    specs = _compose_sort_specs([_ss("price", -1)])
    assert specs == [("derived.price", -1)]


def test_derived_data_includes_rank_fields():
    """DerivedData should include conditionRank (specsRanks moved to LlmAnalysisData)."""
    d = DerivedData.model_validate({
        "price": 499.99,
        "conditionRank": 8,
    })
    dumped = d.model_dump()
    assert "price" in dumped
    assert dumped["conditionRank"] == 8
    # specsCompletenessRank and specsConsistencyRank moved to LlmAnalysisData
    assert "specsCompletenessRank" not in dumped
    assert "specsConsistencyRank" not in dumped


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
    resp = EbayItemsResponse(items=[], stats=None, availableFilters=None, pagination=Pagination(skip=10, limit=10, total=50))
    data = resp.model_dump()
    assert data["stats"] is None
    assert data["availableFilters"] is None
    assert data["pagination"]["skip"] == 10
    assert data["pagination"]["total"] == 50


def test_ebay_items_response_stats_present():
    """EbayItemsResponse should include stats when provided (page 1)."""
    resp = EbayItemsResponse(
        items=[],
        stats=Stats(min=100, max=500, median=300, mean=290, count=10),
        availableFilters={"releaseYear": [{"value": "2017", "count": 5}]},
        pagination=Pagination(skip=0, limit=10, total=10),
    )
    data = resp.model_dump()
    assert data["stats"] is not None
    assert data["stats"]["count"] == 10
    assert data["availableFilters"] is not None
    assert data["pagination"]["skip"] == 0


def test_pagination_model():
    """Pagination model contains skip, limit, total."""
    p = Pagination(skip=0, limit=10, total=100)
    data = p.model_dump()
    assert data == {"skip": 0, "limit": 10, "total": 100}


def test_pagination_always_present_in_response():
    """Pagination is required (not optional) in EbayItemsResponse."""
    import pytest
    with pytest.raises(Exception):
        EbayItemsResponse(items=[], stats=None, availableFilters=None)


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
    assert query["$and"][0] == {"show": True}
    price_cond = query["$and"][-1]
    assert price_cond == {"derived.price": {"$gte": 500, "$lte": 1000}}


def test_compose_query_price_range_min_only():
    """_compose_query with minPrice only produces $gte without $lte."""
    query = _compose_query({"minPrice": 500})
    assert query is not None
    assert query["$and"][0] == {"show": True}
    price_cond = query["$and"][-1]
    assert price_cond == {"derived.price": {"$gte": 500}}
    assert "$lte" not in price_cond["derived.price"]


def test_compose_query_price_range_max_only():
    """_compose_query with maxPrice only produces $lte without $gte."""
    query = _compose_query({"maxPrice": 1000})
    assert query is not None
    assert query["$and"][0] == {"show": True}
    price_cond = query["$and"][-1]
    assert price_cond == {"derived.price": {"$lte": 1000}}
    assert "$gte" not in price_cond["derived.price"]


def test_compose_query_price_range_none():
    """_compose_query with both None produces only the base show condition."""
    query = _compose_query({"minPrice": None, "maxPrice": None})
    assert query == {"$and": [{"show": True}]}


# ── Story 3.2a: Specs Completeness/Consistency and BestGuess tests ──

def test_compose_query_specs_completeness_filter():
    """_compose_query with specsCompleteness produces correct llmAnalysis path."""
    query = _compose_query({"specsCompleteness": ["Good"]})
    query_str = str(query)
    assert "llmAnalysis.specsCompleteness" in query_str
    assert "Good" in query_str


def test_compose_query_specs_consistency_filter():
    """_compose_query with specsConsistency produces correct llmAnalysis path."""
    query = _compose_query({"specsConsistency": ["Good"]})
    query_str = str(query)
    assert "llmAnalysis.specsConsistency" in query_str


def test_compose_query_bestguess_fallback():
    """_compose_query for spec fields uses specsFilter (pre-computed with bestGuess fallback)."""
    query = _compose_query({"releaseYear": ["2017"]})
    query_str = str(query)
    assert "specsFilter.releaseYear" in query_str
    assert "$or" not in query_str


def test_compose_query_non_bestguess_field():
    """_compose_query for all spec fields uses specsFilter (no $or needed)."""
    query = _compose_query({"color": ["Silver"]})
    query_str = str(query)
    assert "specsFilter.color" in query_str
    assert "bestGuess" not in query_str


def test_analysis_data_model():
    """AnalysisData model validates and serializes correctly."""
    a = AnalysisData(
        specsCompleteness="Good",
        specsConsistency="Good",
        variantAnalysis="single match",
        minDistance=0.0,
    )
    dumped = a.model_dump()
    assert dumped["specsCompleteness"] == "Good"
    assert dumped["specsConsistency"] == "Good"
    assert dumped["variantAnalysis"] == "single match"


def test_compute_price_buckets_in_stats_response():
    """Stats model includes priceBuckets field."""
    buckets = [PriceBucket(rangeMin=0, rangeMax=100, count=5)]
    stats = Stats(min=0, max=100, mean=50, median=50, count=5, priceBuckets=buckets)
    assert stats.priceBuckets is not None
    assert len(stats.priceBuckets) == 1
    assert stats.priceBuckets[0].count == 5


# ── Story 2.1: Dual filter pass and price cap tests ──

def test_compose_query_exclude_price_omits_price_filter():
    """_compose_query with exclude_price=True should not include price conditions."""
    filter_data = {"ramSize": [16], "minPrice": 500, "maxPrice": 1000}
    query_with_price = _compose_query(filter_data, exclude_price=False)
    query_without_price = _compose_query(filter_data, exclude_price=True)

    # With price: show + ramSize + price = 3 conditions
    assert len(query_with_price["$and"]) == 3
    # Without price: show + ramSize = 2 conditions
    assert len(query_without_price["$and"]) == 2


def test_compose_query_exclude_price_keeps_other_filters():
    """_compose_query with exclude_price=True should keep all non-price filters."""
    filter_data = {
        "ramSize": [16],
        "screenSize": [15.4],
        "minPrice": 500,
        "maxPrice": 1000,
        "screen": ["G"],
    }
    query = _compose_query(filter_data, exclude_price=True)
    # show + ramSize + screenSize + screen (llm) = 4 conditions, no price
    assert len(query["$and"]) == 4


def test_compose_query_exclude_price_no_price_in_filter():
    """_compose_query with exclude_price=True when no price filter is same as without."""
    filter_data = {"ramSize": [16]}
    q1 = _compose_query(filter_data, exclude_price=False)
    q2 = _compose_query(filter_data, exclude_price=True)
    assert q1 == q2


def test_compose_query_exclude_price_default_false():
    """_compose_query default exclude_price is False (includes price)."""
    filter_data = {"minPrice": 500}
    query = _compose_query(filter_data)
    assert len(query["$and"]) == 2  # show + price
    assert "derived.price" in str(query)


