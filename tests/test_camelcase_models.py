"""Tests verifying Pydantic models and API helpers use camelCase field names."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from models import (
    DerivedData, LlmDerived, EbayItem, EbayItemsRequest,
    EbayItemsResponse, EbayFilterValuesResponse, VariantSpec,
    ItemDetails, Stats,
)
from main import _compose_query, _compose_sort_specs, _available_filter_values


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
    specs = _compose_sort_specs([{"field": "releaseYear", "direction": -1}])
    assert specs == [("derived.releaseYear", -1)]


def test_compose_sort_specs_llm_path():
    """_compose_sort_specs should produce rank paths for categorical LLM fields."""
    specs = _compose_sort_specs([{"field": "componentListing", "direction": 1}])
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
    specs = _compose_sort_specs([{"field": "condition", "direction": 1}])
    assert specs == [("derived.conditionRank", 1)]


def test_compose_sort_specs_battery_uses_rank():
    """Sorting by battery should use llmDerived.batteryRank."""
    specs = _compose_sort_specs([{"field": "battery", "direction": -1}])
    assert specs == [("llmDerived.batteryRank", -1)]


def test_compose_sort_specs_screen_uses_rank():
    """Sorting by screen should use llmDerived.screenRank."""
    specs = _compose_sort_specs([{"field": "screen", "direction": 1}])
    assert specs == [("llmDerived.screenRank", 1)]


def test_compose_sort_specs_specs_quality_uses_rank():
    """Sorting by specsQuality should use derived.specsQualityRank."""
    specs = _compose_sort_specs([{"field": "specsQuality", "direction": 1}])
    assert specs == [("derived.specsQualityRank", 1)]


def test_compose_sort_specs_numeric_field_no_rank():
    """Numeric fields like price should NOT use rank paths."""
    specs = _compose_sort_specs([{"field": "price", "direction": 1}])
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
        specs = _compose_sort_specs([{"field": field, "direction": 1}])
        assert specs == [(expected_path, 1)], f"Field '{field}' should sort on '{expected_path}'"


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
