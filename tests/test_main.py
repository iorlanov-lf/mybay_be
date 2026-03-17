import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from typing import Any, Dict, List, Optional
from main import app
from get_items import (
    _compose_query, _build_price_match, _build_aggregation_pipeline,
    _build_cache_hit_pipeline,
    LLM_SPEC_FIELD_MAP, BEST_GUESS_FIELDS, ANALYSIS_FILTER_FIELDS, LLM_FIELDS,
)


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def _make_item(item_id, price, screen="Good", product_line=None):
    """Build a minimal MongoDB document for integration tests."""
    return {
        "itemId": item_id,
        "details": {"title": f"MacBook {item_id}", "condition": "Used"},
        "derived": {"price": price},
        "llmSpecs": {
            "productLine": [product_line or "MacBook Pro 15\" 2019"],
            "releaseYear": ["2019"],
            "screenSize": [15.4],
            "ramSize": [16],
            "ssdSize": [256],
        },
        "llmDerived": {"screen": screen, "subject": "L"},
    }


SAMPLE_ITEMS = [
    _make_item("item1", 500.0),
    _make_item("item2", 800.0),
    _make_item("item3", 1200.0),
    _make_item("item4", 1800.0),
    _make_item("item5", 2500.0),
]


class FakeAsyncCursor:
    """Async cursor stub that implements Motor's to_list() interface."""

    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, length=None):
        return self._docs if length is None else self._docs[:length]


def _fake_filter_value_facet(docs: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Build {_id, count} list for a filter key from docs (mirrors MongoDB facet output)."""
    counts: Dict[Any, int] = {}
    for doc in docs:
        llm_specs = doc.get("llmSpecs") or {}
        llm_analysis = doc.get("llmAnalysis") or {}
        llm_derived = doc.get("llmDerived") or {}
        details = doc.get("details") or {}
        values: set = set()
        if key in BEST_GUESS_FIELDS:
            mongo_field = LLM_SPEC_FIELD_MAP[key].split(".")[-1]
            spec_vals = llm_specs.get(mongo_field) or []
            bg_vals = ((llm_analysis.get("specsAnalysis") or {}).get(key) or {}).get("bestGuess") or []
            for v in (spec_vals if isinstance(spec_vals, list) else [spec_vals]):
                if v is not None:
                    values.add(v)
            for v in (bg_vals if isinstance(bg_vals, list) else [bg_vals]):
                if v is not None:
                    values.add(v)
        elif key in LLM_SPEC_FIELD_MAP:
            mongo_field = LLM_SPEC_FIELD_MAP[key].split(".")[-1]
            spec_vals = llm_specs.get(mongo_field) or []
            for v in (spec_vals if isinstance(spec_vals, list) else [spec_vals]):
                if v is not None:
                    values.add(v)
        elif key in ANALYSIS_FILTER_FIELDS:
            v = llm_analysis.get(key)
            if v is not None:
                values.add(v)
        elif key in LLM_FIELDS:
            v = llm_derived.get(key)
            if v is not None:
                values.add(v)
        elif key == "returnable":
            v = (details.get("returnTerms") or {}).get("returnsAccepted")
            if v is not None:
                values.add(v)
        elif key == "returnShippingCostPayer":
            v = (details.get("returnTerms") or {}).get("returnShippingCostPayer")
            if v is not None:
                values.add(v)
        elif key == "condition":
            v = details.get("condition")
            if v is not None:
                values.add(v)
        for v in values:
            counts[v] = counts.get(v, 0) + 1
    return [{"_id": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: (isinstance(x[0], str), x[0]))]


class FakeStatsCollection:
    """Fake stats cache collection for testing."""

    def __init__(self):
        self._cached_doc: Optional[Dict[str, Any]] = None
        self._find_one_calls: int = 0
        self._update_one_calls: list = []

    async def find_one(self, query):
        self._find_one_calls += 1
        if self._cached_doc is not None and query.get("valid") is True:
            return self._cached_doc
        return None

    async def update_one(self, filter_, update, upsert=False):
        self._update_one_calls.append((filter_, update))


class FakeDB(dict):
    """Dict-like fake database that auto-creates FakeStatsCollection for _stats keys."""

    def __missing__(self, key):
        if key.endswith("_stats"):
            col = FakeStatsCollection()
            self[key] = col
            return col
        raise KeyError(key)


class FakeCollection:
    """In-memory MongoDB collection fake for integration tests."""

    def __init__(self, docs):
        self._docs = list(docs)

    def find(self, query=None, *args, **kwargs):
        return FakeAsyncCursor(self._docs)

    def aggregate(self, pipeline):
        facet_stage = next((s["$facet"] for s in pipeline if "$facet" in s), None)

        # Flat pipeline (cache-hit path): no $facet, just skip/limit
        if facet_stage is None:
            skip = next((s["$skip"] for s in pipeline if "$skip" in s), 0)
            limit = next((s["$limit"] for s in pipeline if "$limit" in s), 10)
            return FakeAsyncCursor(self._docs[skip:skip + limit])

        items_pipe = facet_stage.get("items", [])
        skip = next((s["$skip"] for s in items_pipe if "$skip" in s), 0)
        limit = next((s["$limit"] for s in items_pipe if "$limit" in s), 10)
        docs = self._docs
        result: Dict[str, Any] = {}

        result["totalCount"] = [{"n": len(docs)}]
        result["items"] = docs[skip:skip + limit]

        if "stats" in facet_stage or "baseStats" in facet_stage:
            prices = sorted([float(d["derived"]["price"]) for d in docs if d.get("derived", {}).get("price") is not None])
            if prices:
                n = len(prices)
                med = prices[n // 2] if n % 2 == 1 else (prices[n // 2 - 1] + prices[n // 2]) / 2
                stats_doc = [{"_id": None, "min": prices[0], "max": prices[-1], "mean": sum(prices) / n, "median": med, "count": n}]
            else:
                stats_doc = []
            if "stats" in facet_stage:
                result["stats"] = stats_doc
            if "baseStats" in facet_stage:
                result["baseStats"] = stats_doc

        if "priceBins" in facet_stage or "basePriceBins" in facet_stage:
            prices = [float(d["derived"]["price"]) for d in docs if d.get("derived", {}).get("price") is not None]
            bins: Dict[int, int] = {}
            for p in prices:
                bk = (int(p) // 100) * 100
                bins[bk] = bins.get(bk, 0) + 1
            bins_docs = [{"_id": k, "count": v} for k, v in sorted(bins.items())]
            if "priceBins" in facet_stage:
                result["priceBins"] = bins_docs
            if "basePriceBins" in facet_stage:
                result["basePriceBins"] = bins_docs

        known = {"totalCount", "items", "stats", "baseStats", "priceBins", "basePriceBins"}
        for key in facet_stage:
            if key not in known:
                result[key] = _fake_filter_value_facet(docs, key)

        return FakeAsyncCursor([result])


@pytest.fixture
def mock_db():
    """Patch AsyncIOMotorClient so the lifespan injects FakeCollection for all DB access."""
    fake_col = FakeCollection(SAMPLE_ITEMS)
    fake_db = FakeDB({"mac_book_pro": fake_col})
    mock_motor_client = MagicMock()
    mock_motor_client.get_database.return_value = fake_db
    with patch("main.AsyncIOMotorClient", return_value=mock_motor_client):
        yield fake_db


def test_home_route(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello"}


def test_about_route(client):
    response = client.get("/about")
    assert response.status_code == 200
    assert response.json() == {"message": "This is the about page."}


def test_validation_error_returns_structured_envelope(client):
    """POST /ebay/items with invalid body returns structured error envelope."""
    response = client.post("/ebay/items", json={})
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Request validation failed"
    assert isinstance(data["error"]["details"], list)
    assert len(data["error"]["details"]) > 0


def test_http_exception_returns_structured_envelope(client):
    """POST /ebay/items with unknown model returns structured error envelope."""
    response = client.post("/ebay/items", json={"name": "UnknownModel"})
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"
    assert "not found" in data["error"]["message"].lower()


def test_invalid_sort_direction_returns_validation_error():
    """Invalid sort direction (not 1 or -1) returns structured validation error."""
    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.post("/ebay/items", json={
            "name": "MacBookPro",
            "sortSpecs": [{"field": "price", "direction": 10}],
        })
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"


# ── Integration tests: Story 2.1 ──


def test_ebay_items_page1_has_stats_and_pagination(mock_db, client):
    """AC1/AC4: Page 1 returns items, stats, and pagination."""
    response = client.post("/ebay/items", json={"name": "MacBookPro", "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "stats" in data
    assert "pagination" in data
    assert data["stats"] is not None
    assert data["stats"]["count"] == 5
    assert data["stats"]["min"] == 500.0
    assert data["stats"]["max"] == 2500.0
    assert data["pagination"]["skip"] == 0
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["total"] == 5
    assert len(data["items"]) == 2


def test_ebay_items_page2_omits_stats(mock_db, client):
    """AC5: Page 2+ (skip > 0) omits stats and availableFilters."""
    response = client.post("/ebay/items", json={"name": "MacBookPro", "skip": 2, "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["stats"] is None
    assert data["availableFilters"] is None
    assert data["pagination"]["skip"] == 2
    assert data["pagination"]["total"] == 5
    assert len(data["items"]) == 2


def test_ebay_items_page1_has_price_buckets(mock_db, client):
    """AC2: Page 1 stats include priceBuckets."""
    response = client.post("/ebay/items", json={"name": "MacBookPro"})
    data = response.json()
    assert data["stats"]["priceBuckets"] is not None
    assert len(data["stats"]["priceBuckets"]) > 0
    for bucket in data["stats"]["priceBuckets"]:
        assert "rangeMin" in bucket
        assert "rangeMax" in bucket
        assert "count" in bucket


def test_ebay_items_page1_has_available_filters(mock_db, client):
    """Page 1 returns availableFilters with value counts sourced from llmSpecs."""
    response = client.post("/ebay/items", json={"name": "MacBookPro"})
    data = response.json()
    assert data["availableFilters"] is not None
    # ramSize should be populated from llmSpecs.ramSize
    assert "ramSize" in data["availableFilters"]
    assert any(f["value"] == 16 for f in data["availableFilters"]["ramSize"])


# ── Unit tests: filter query generation ──


def test_compose_query_spec_filter_routes_to_llm_specs():
    """Spec filter keys route to llmSpecs.* MongoDB paths."""
    query = _compose_query({"ramSize": [16]})
    assert query is not None
    clauses = query["$and"]
    # ramSize with bestGuess fallback → $or clause
    or_clause = next((c for c in clauses if "$or" in c), None)
    assert or_clause is not None
    or_arms = or_clause["$or"]
    assert any("llmSpecs.ramSize" in arm for arm in or_arms)
    assert any("llmAnalysis.specsAnalysis.ramSize.bestGuess" in arm for arm in or_arms)


def test_compose_query_product_line_routes_to_llm_specs():
    """productLine filter routes to llmSpecs.productLine (no bestGuess fallback)."""
    query = _compose_query({"productLine": ["MacBook Pro"]})
    assert query is not None
    clauses = query["$and"]
    assert {"llmSpecs.productLine": {"$in": ["MacBook Pro"]}} in clauses


def test_compose_query_analysis_routes_to_llm_analysis():
    """specsCompleteness filter routes to llmAnalysis.specsCompleteness."""
    query = _compose_query({"specsCompleteness": ["Good"]})
    assert query is not None
    clauses = query["$and"]
    assert {"llmAnalysis.specsCompleteness": {"$in": ["Good"]}} in clauses


def test_compose_query_subject_routes_to_llm_derived():
    """subject filter routes to llmDerived.subject."""
    query = _compose_query({"subject": ["L"]})
    assert query is not None
    clauses = query["$and"]
    assert {"llmDerived.subject": {"$in": ["L"]}} in clauses


def test_compose_query_screen_size_has_bestguess_fallback():
    """screenSize filter includes bestGuess fallback from llmAnalysis.specsAnalysis.screenSize."""
    query = _compose_query({"screenSize": [15.4]})
    assert query is not None
    or_clause = next((c for c in query["$and"] if "$or" in c), None)
    assert or_clause is not None
    paths = [list(arm.keys())[0] for arm in or_clause["$or"]]
    assert "llmSpecs.screenSize" in paths
    assert "llmAnalysis.specsAnalysis.screenSize.bestGuess" in paths


def test_compose_query_no_derived_fields_queried():
    """No query clause should reference derived.* spec fields."""
    query = _compose_query({
        "ramSize": [16], "ssdSize": [256], "screenSize": [15.4],
        "releaseYear": ["2019"], "cpuFamily": ["M1"],
    })
    import json
    query_str = json.dumps(query)
    # derived.price is still used for price, but no spec fields
    assert "derived.ramSize" not in query_str
    assert "derived.ssdSize" not in query_str
    assert "derived.screenSize" not in query_str
    assert "derived.releaseYear" not in query_str
    assert "analysis.specsAnalysis" not in query_str


# ── Unit tests: pipeline building helpers ──


def test_build_price_match_with_price_filter():
    """_build_price_match extracts price range as MongoDB condition."""
    result = _build_price_match({"minPrice": 500, "maxPrice": 1500})
    assert result == {"derived.price": {"$gte": 500, "$lte": 1500}}


def test_build_price_match_without_price_filter():
    """_build_price_match returns None when no price range in filter."""
    assert _build_price_match(None) is None
    assert _build_price_match({}) is None
    assert _build_price_match({"ramSize": [16]}) is None


def test_build_aggregation_pipeline_has_project_before_facet():
    """$project stage is always present and immediately precedes $facet."""
    for match_query in [None, {"$and": [{"derived.price": {"$lt": 3000}}]}]:
        pipeline = _build_aggregation_pipeline(
            match_query=match_query, sort_specs=[("derived.price", 1)],
            skip=0, limit=10, is_first_page=True, price_match=None,
        )
        stage_types = [list(s.keys())[0] for s in pipeline]
        assert "$project" in stage_types
        project_idx = stage_types.index("$project")
        facet_idx = stage_types.index("$facet")
        assert facet_idx == project_idx + 1, "$project must immediately precede $facet"
        project_fields = pipeline[project_idx]["$project"]
        for field in ("itemId", "details.title", "details.condition", "derived.price",
                      "llmSpecs.ramSize", "llmAnalysis.specsCompleteness", "llmDerived.screen"):
            assert field in project_fields, f"{field} missing from $project"


def test_build_aggregation_pipeline_page1_has_all_facets():
    """Page 1 pipeline includes stats, priceBins, and filter value facets."""
    pipeline = _build_aggregation_pipeline(
        match_query=None, sort_specs=[("derived.price", 1)],
        skip=0, limit=10, is_first_page=True, price_match=None,
    )
    facet_stage = next(s["$facet"] for s in pipeline if "$facet" in s)
    assert "totalCount" in facet_stage
    assert "items" in facet_stage
    assert "stats" in facet_stage
    assert "priceBins" in facet_stage
    assert "ramSize" in facet_stage
    assert "screen" in facet_stage


def test_build_aggregation_pipeline_page2_has_only_count_and_items():
    """Page 2+ pipeline contains only totalCount and items facets."""
    pipeline = _build_aggregation_pipeline(
        match_query=None, sort_specs=[("derived.price", 1)],
        skip=10, limit=10, is_first_page=False, price_match=None,
    )
    facet_stage = next(s["$facet"] for s in pipeline if "$facet" in s)
    assert "totalCount" in facet_stage
    assert "items" in facet_stage
    assert "stats" not in facet_stage
    assert "priceBins" not in facet_stage
    assert "ramSize" not in facet_stage


def test_build_aggregation_pipeline_with_price_filter_has_base_facets():
    """Page 1 with price filter includes baseStats and basePriceBins."""
    price_match = {"derived.price": {"$gte": 500, "$lte": 1500}}
    pipeline = _build_aggregation_pipeline(
        match_query=None, sort_specs=[("derived.price", 1)],
        skip=0, limit=10, is_first_page=True, price_match=price_match,
    )
    facet_stage = next(s["$facet"] for s in pipeline if "$facet" in s)
    assert "baseStats" in facet_stage
    assert "basePriceBins" in facet_stage
    assert "stats" in facet_stage
    assert "priceBins" not in facet_stage


# ── Integration tests: Search Templates ──


def test_search_templates_returns_matching_docs(client):
    """GET /ebay/search-templates returns docs matching productName."""
    fake_docs = [
        {"productName": "MacBook Pro", "templateName": "Budget", "templateDescription": "Under $500", "filters": {"maxPrice": 500}},
        {"productName": "MacBook Pro", "templateName": "RAM", "templateDescription": "32GB+", "filters": {"ram": "32"}},
    ]
    fake_col = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.to_list = AsyncMock(return_value=[dict(d, _id="fake") for d in fake_docs])
    fake_col.find.return_value = fake_cursor
    fake_db = {"search_templates": fake_col, "mac_book_pro": FakeCollection(SAMPLE_ITEMS)}
    app.state.db = fake_db
    response = client.get("/ebay/search-templates", params={"productName": "MacBook Pro"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["templateName"] == "Budget"
    fake_col.find.assert_called_once_with({"productName": "MacBook Pro"}, {"_id": 0})


def test_search_templates_missing_param_returns_422(client):
    """GET /ebay/search-templates without productName returns 422."""
    response = client.get("/ebay/search-templates")
    assert response.status_code == 422


# ── Integration tests: MacBookAir routing ──


def test_ebay_items_macbook_air_routes_to_air_collection(client):
    """POST /ebay/items with name=MacBookAir uses mac_book_air collection."""
    air_items = SAMPLE_ITEMS[:2]
    fake_db = FakeDB({
        "mac_book_pro": FakeCollection([]),
        "mac_book_air": FakeCollection(air_items),
    })
    app.state.db = fake_db
    response = client.post("/ebay/items", json={"name": "MacBookAir", "limit": 10})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2


def test_ebay_items_by_ids_macbook_air_routes_to_air_collection(client):
    """POST /ebay/items/by-ids with name=MacBookAir uses mac_book_air collection."""
    item_id = SAMPLE_ITEMS[0]["itemId"]
    fake_db = {
        "mac_book_pro": FakeCollection([]),
        "mac_book_air": FakeCollection(SAMPLE_ITEMS[:1]),
    }
    app.state.db = fake_db
    response = client.post("/ebay/items/by-ids", json={"name": "MacBookAir", "itemIds": [item_id]})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["itemId"] == item_id


# ── Auth tests: Story 5.2 ──


def test_verify_turnstile_dev_mode(client):
    """POST /auth/verify with no TURNSTILE_SECRET_KEY returns 200 and session_token."""
    response = client.post("/auth/verify", json={"token": "any-token"})
    assert response.status_code == 200
    data = response.json()
    assert "session_token" in data
    assert "." in data["session_token"]


def test_verify_turnstile_success():
    """POST /auth/verify with TURNSTILE_SECRET_KEY set and Cloudflare success returns session_token."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True}
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("auth.TURNSTILE_SECRET_KEY", "test-secret"):
        with patch("auth.httpx.AsyncClient", return_value=mock_client):
            with TestClient(app) as c:
                response = c.post("/auth/verify", json={"token": "valid-token"})
    assert response.status_code == 200
    assert "session_token" in response.json()


def test_verify_turnstile_failure():
    """POST /auth/verify with Cloudflare failure returns 403."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": False}
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("auth.TURNSTILE_SECRET_KEY", "test-secret"):
        with patch("auth.httpx.AsyncClient", return_value=mock_client):
            with TestClient(app) as c:
                response = c.post("/auth/verify", json={"token": "bad-token"})
    assert response.status_code == 403


def test_ebay_items_no_token_dev_mode(mock_db, client):
    """Without TURNSTILE_SECRET_KEY, /ebay/items passes through (no auth required)."""
    response = client.post("/ebay/items", json={"name": "MacBookPro"})
    assert response.status_code == 200


def test_ebay_items_valid_session_token(mock_db):
    """Valid X-Session-Token header → 200."""
    import auth as auth_mod
    jwt_key = "test-jwt"
    with patch("auth.JWT_SECRET_KEY", jwt_key):
        token = auth_mod._create_session_token()
    with patch("auth.TURNSTILE_SECRET_KEY", "test-secret"):
        with patch("auth.JWT_SECRET_KEY", jwt_key):
            with TestClient(app) as c:
                response = c.post(
                    "/ebay/items",
                    json={"name": "MacBookPro"},
                    headers={"X-Session-Token": token},
                )
    assert response.status_code == 200


def test_ebay_items_invalid_session_token():
    """Invalid X-Session-Token header → 401."""
    with patch("auth.TURNSTILE_SECRET_KEY", "test-secret"):
        with TestClient(app) as c:
            response = c.post(
                "/ebay/items",
                json={"name": "MacBookPro"},
                headers={"X-Session-Token": "invalid.token"},
            )
    assert response.status_code == 401


def test_ebay_items_expired_session_token():
    """Expired X-Session-Token → 401."""
    import time
    import hashlib
    import hmac as _hmac
    jwt_key = "test-jwt"
    exp = int(time.time()) - 10  # already expired
    sig = _hmac.new(jwt_key.encode(), str(exp).encode(), hashlib.sha256).hexdigest()
    expired_token = f"{exp}.{sig}"

    with patch("auth.TURNSTILE_SECRET_KEY", "test-secret"):
        with patch("auth.JWT_SECRET_KEY", jwt_key):
            with TestClient(app) as c:
                response = c.post(
                    "/ebay/items",
                    json={"name": "MacBookPro"},
                    headers={"X-Session-Token": expired_token},
                )
    assert response.status_code == 401


def test_ebay_items_api_key_bypass(mock_db):
    """Valid X-Api-Key header bypasses session token check → 200."""
    bypass_key = "my-secret-bypass"
    with patch("auth.TURNSTILE_SECRET_KEY", "test-secret"):
        with patch("auth.API_BYPASS_KEY", bypass_key):
            with TestClient(app) as c:
                response = c.post(
                    "/ebay/items",
                    json={"name": "MacBookPro"},
                    headers={"X-Api-Key": bypass_key},
                )
    assert response.status_code == 200


# ── Cache tests: Story 6.5 ──


def test_first_page_cache_miss_stores_cache(mock_db, client):
    """First page with no valid cache: full pipeline runs, result stored in cache."""
    stats_col = mock_db["mac_book_pro_stats"]  # trigger FakeDB creation

    response = client.post("/ebay/items", json={"name": "MacBookPro"})

    assert response.status_code == 200
    data = response.json()
    assert data["stats"] is not None
    assert data["availableFilters"] is not None
    # store_cache called update_one with $set + $setOnInsert
    assert len(stats_col._update_one_calls) == 1
    _, update = stats_col._update_one_calls[0]
    assert "$set" in update
    assert update["$set"]["valid"] is True
    assert update["$set"]["productName"] == "MacBookPro"


def test_first_page_cache_hit_uses_cached_stats(client):
    """First page with valid cache: cached stats/filters returned without running full pipeline."""
    cached_doc = {
        "_id": "deadbeef",
        "filter": {},
        "productName": "MacBookPro",
        "valid": True,
        "hits": 5,
        "totalCount": 99,
        "stats": {
            "min": 111.0, "max": 999.0, "median": 500.0, "mean": 500.0,
            "count": 3, "priceBuckets": None,
        },
        "baseStats": None,
        "availableFilters": {"ramSize": [{"value": 16, "count": 3}]},
    }
    fake_stats_col = FakeStatsCollection()
    fake_stats_col._cached_doc = cached_doc
    fake_db = FakeDB({
        "mac_book_pro": FakeCollection(SAMPLE_ITEMS),
        "mac_book_pro_stats": fake_stats_col,
    })
    app.state.db = fake_db

    response = client.post("/ebay/items", json={"name": "MacBookPro"})

    assert response.status_code == 200
    data = response.json()
    # Stats served from cache
    assert data["stats"]["min"] == 111.0
    assert data["stats"]["max"] == 999.0
    assert data["stats"]["count"] == 3
    assert "ramSize" in data["availableFilters"]
    assert data["availableFilters"]["ramSize"][0]["value"] == 16
    # increment_hits was called (update_one with $inc)
    assert any("$inc" in str(call[1]) for call in fake_stats_col._update_one_calls)


def test_cache_hit_pipeline_is_flat():
    """Cache-hit pipeline has no $facet: $match → $sort → $skip → $limit → $project."""
    match_query = {"$and": [{"llmSpecs.productLine": {"$in": ["MacBook Pro"]}}, {"derived.price": {"$lt": 3000}}]}
    price_match = {"derived.price": {"$gte": 500, "$lte": 1500}}
    pipeline = _build_cache_hit_pipeline(match_query, price_match, 3000, [("derived.price", 1), ("_id", 1)], 0, 10)
    stage_types = [list(s.keys())[0] for s in pipeline]
    assert "$facet" not in stage_types
    assert stage_types == ["$match", "$sort", "$skip", "$limit", "$project"]
    # Single price condition (user's maxPrice, no separate cap)
    match_doc = pipeline[0]["$match"]
    price_conds = [c.get("derived.price") for c in match_doc.get("$and", [match_doc]) if "derived.price" in c]
    assert len(price_conds) == 1
    assert price_conds[0] == {"$gte": 500, "$lte": 1500}
    assert "$project" in pipeline[-1]


def test_cache_hit_pipeline_uses_cap_when_no_max_price():
    """When user has no maxPrice, cap is used as upper bound."""
    match_query = {"$and": [{"derived.price": {"$lt": 3000}}]}
    # minPrice only, no maxPrice
    price_match = {"derived.price": {"$gte": 200}}
    pipeline = _build_cache_hit_pipeline(match_query, price_match, 3000, [("derived.price", 1), ("_id", 1)], 0, 10)
    match_doc = pipeline[0]["$match"]
    price_cond = match_doc.get("derived.price") or next(
        c["derived.price"] for c in match_doc.get("$and", []) if "derived.price" in c
    )
    assert price_cond == {"$gte": 200, "$lt": 3000}


def test_cache_hit_pipeline_no_price_filter_uses_cap_only():
    """No user price filter: only the cap condition appears in $match."""
    match_query = {"$and": [{"derived.price": {"$lt": 3000}}]}
    pipeline = _build_cache_hit_pipeline(match_query, None, 3000, [("derived.price", 1), ("_id", 1)], 0, 10)
    match_doc = pipeline[0]["$match"]
    assert match_doc == {"derived.price": {"$lt": 3000}}


def test_second_page_skips_cache_lookup(mock_db, client):
    """Page 2+ does not look up the stats cache."""
    with patch("get_items.get_valid_cache", new_callable=AsyncMock) as mock_cache:
        response = client.post("/ebay/items", json={"name": "MacBookPro", "skip": 10})
    assert response.status_code == 200
    mock_cache.assert_not_called()
