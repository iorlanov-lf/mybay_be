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
from main import _compose_query, _compose_sort_specs, _available_filter_values, _compute_price_buckets, _compute_stats


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
        conditionRank=6,
        specsCompletenessRank=1,
        specsConsistencyRank=1,
    )
    data = d.model_dump()
    for key in data:
        if key in {"description", "color", "price"}:
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
            },
            "analysis": {
                "specsCompleteness": "Good",
                "specsConsistency": "Good",
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


def test_compose_sort_specs_specs_completeness_uses_rank():
    """Sorting by specsCompleteness should use derived.specsCompletenessRank."""
    specs = _compose_sort_specs([_ss("specsCompleteness")])
    assert specs == [("derived.specsCompletenessRank", 1)]


def test_compose_sort_specs_specs_consistency_uses_rank():
    """Sorting by specsConsistency should use derived.specsConsistencyRank."""
    specs = _compose_sort_specs([_ss("specsConsistency")])
    assert specs == [("derived.specsConsistencyRank", 1)]


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
    """DerivedData should include conditionRank, specsCompletenessRank, specsConsistencyRank."""
    d = DerivedData.model_validate({
        "price": 499.99,
        "conditionRank": 8,
        "specsCompletenessRank": 1,
        "specsConsistencyRank": 1,
    })
    dumped = d.model_dump()
    assert "price" in dumped
    assert dumped["conditionRank"] == 8
    assert dumped["specsCompletenessRank"] == 1
    assert dumped["specsConsistencyRank"] == 1


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


# ── Story 3.2a: Specs Completeness/Consistency and BestGuess tests ──

def test_compose_query_specs_completeness_filter():
    """_compose_query with specsCompleteness produces correct analysis path."""
    query = _compose_query({"specsCompleteness": ["Good"]})
    query_str = str(query)
    assert "analysis.specsCompleteness" in query_str
    assert "Good" in query_str


def test_compose_query_specs_consistency_filter():
    """_compose_query with specsConsistency produces correct analysis path."""
    query = _compose_query({"specsConsistency": ["Good"]})
    query_str = str(query)
    assert "analysis.specsConsistency" in query_str


def test_compose_query_bestguess_fallback():
    """_compose_query for main spec fields includes bestGuess fallback."""
    query = _compose_query({"releaseYear": ["2017"]})
    query_str = str(query)
    assert "derived.releaseYear" in query_str
    assert "analysis.specsAnalysis.releaseYear.bestGuess" in query_str


def test_compose_query_non_bestguess_field():
    """_compose_query for non-main spec fields does NOT include bestGuess fallback."""
    query = _compose_query({"color": ["Silver"]})
    query_str = str(query)
    assert "derived.color" in query_str
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


# ── Story 2.3: Price Distribution Histogram ──

def test_compute_price_buckets_returns_none_for_fewer_than_3():
    """Price buckets returns None when fewer than 3 prices."""
    assert _compute_price_buckets([]) is None
    assert _compute_price_buckets([100.0]) is None
    assert _compute_price_buckets([100.0, 200.0]) is None

def test_compute_price_buckets_returns_buckets():
    """Price buckets returns fixed $100 range buckets."""
    prices = [100.0, 200.0, 300.0, 400.0, 500.0]
    buckets = _compute_price_buckets(prices)
    assert buckets is not None
    # $1-100, $101-200, $201-300, $301-400, $401-500
    assert len(buckets) == 5
    assert buckets[0].rangeMin == 1
    assert buckets[0].rangeMax == 100
    assert buckets[-1].rangeMin == 401
    assert buckets[-1].rangeMax == 500
    total = sum(b.count for b in buckets)
    assert total == 5

def test_compute_price_buckets_all_same_price():
    """Price buckets handles all identical prices in one bucket."""
    prices = [250.0, 250.0, 250.0]
    buckets = _compute_price_buckets(prices)
    assert buckets is not None
    # $1-100 (0), $101-200 (0), $201-300 (3)
    assert len(buckets) == 3
    assert buckets[2].count == 3
    assert buckets[2].rangeMin == 201
    assert buckets[2].rangeMax == 300

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

    # With price: should have 2 conditions (ramSize + price)
    assert len(query_with_price["$and"]) == 2
    # Without price: should have 1 condition (ramSize only)
    assert len(query_without_price["$and"]) == 1


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
    # ramSize + screenSize + screen (llm) = 3 conditions, no price
    assert len(query["$and"]) == 3


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
    assert len(query["$and"]) == 1
    assert "derived.price" in str(query)


def test_compute_price_buckets_respects_price_cap():
    """Price buckets computed from prices capped at product limit."""
    # Simulate: 5 normal prices + 1 bogus price above cap
    prices_under_cap = [100.0, 200.0, 300.0, 400.0, 500.0]
    prices_with_bogus = prices_under_cap + [9999.0]

    buckets_capped = _compute_price_buckets(prices_under_cap)
    buckets_uncapped = _compute_price_buckets(prices_with_bogus)

    # Capped: last bucket is $401-$500; uncapped: extends to $9901-$10000
    assert buckets_capped[-1].rangeMax == 500
    assert buckets_uncapped[-1].rangeMax == 10000
    # Verifies that filtering before calling _compute_price_buckets works
    assert sum(b.count for b in buckets_capped) == 5


def test_compute_stats_returns_correct_values():
    """_compute_stats computes min, max, median, mean, count correctly."""
    prices = [100.0, 200.0, 300.0, 400.0, 500.0]
    stats = _compute_stats(prices)
    assert stats.min == 100.0
    assert stats.max == 500.0
    assert stats.median == 300.0
    assert stats.mean == 300.0
    assert stats.count == 5
    assert stats.priceBuckets is None


def test_compute_stats_even_count_median():
    """_compute_stats computes median correctly for even-length lists."""
    prices = [100.0, 200.0, 300.0, 400.0]
    stats = _compute_stats(prices)
    assert stats.median == 250.0


def test_compute_stats_empty_returns_none():
    """_compute_stats returns None for empty price list."""
    assert _compute_stats([]) is None


def test_compute_stats_with_price_buckets():
    """_compute_stats passes through priceBuckets."""
    buckets = [PriceBucket(rangeMin=100, rangeMax=200, count=3)]
    stats = _compute_stats([100.0, 150.0, 200.0], buckets)
    assert stats.priceBuckets == buckets
