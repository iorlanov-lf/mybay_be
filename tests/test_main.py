import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def _make_item(item_id, price, screen="Good", laptop_model=None):
    """Build a minimal MongoDB document for integration tests."""
    return {
        "itemId": item_id,
        "details": {"title": f"MacBook {item_id}", "condition": "Used"},
        "derived": {
            "price": price,
            "laptopModel": [laptop_model or "MacBook Pro 15\" 2019"],
            "releaseYear": ["2019"],
            "screenSize": [15.4],
            "ramSize": [16],
            "ssdSize": [256],
        },
        "llmDerived": {"screen": screen, "componentListing": "N"},
    }


SAMPLE_ITEMS = [
    _make_item("item1", 500.0),
    _make_item("item2", 800.0),
    _make_item("item3", 1200.0),
    _make_item("item4", 1800.0),
    _make_item("item5", 2500.0),
]


class FakeCursor:
    """Minimal cursor that supports .sort() chaining and iteration."""

    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, keys):
        return self

    def __iter__(self):
        return iter(self._docs)

    def __len__(self):
        return len(self._docs)


class FakeCollection:
    """In-memory MongoDB collection fake for integration tests."""

    def __init__(self, docs):
        self._docs = list(docs)

    def find(self, query=None):
        if not query:
            return FakeCursor(self._docs)
        # Simplified: return all docs (query filtering tested via unit tests)
        return FakeCursor(self._docs)


@pytest.fixture
def mock_db():
    """Patch main.db to use FakeCollection with SAMPLE_ITEMS."""
    fake_col = FakeCollection(SAMPLE_ITEMS)
    fake_db = {"mac_book_pro": fake_col}
    with patch("main.db", fake_db):
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


def test_ebay_items_page1_has_stats_and_pagination(client, mock_db):
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


def test_ebay_items_page2_omits_stats(client, mock_db):
    """AC5: Page 2+ (skip > 0) omits stats and availableFilters."""
    response = client.post("/ebay/items", json={"name": "MacBookPro", "skip": 2, "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["stats"] is None
    assert data["availableFilters"] is None
    assert data["pagination"]["skip"] == 2
    assert data["pagination"]["total"] == 5
    assert len(data["items"]) == 2


def test_ebay_items_page1_has_price_buckets(client, mock_db):
    """AC2: Page 1 stats include priceBuckets."""
    response = client.post("/ebay/items", json={"name": "MacBookPro"})
    data = response.json()
    assert data["stats"]["priceBuckets"] is not None
    assert len(data["stats"]["priceBuckets"]) > 0
    for bucket in data["stats"]["priceBuckets"]:
        assert "rangeMin" in bucket
        assert "rangeMax" in bucket
        assert "count" in bucket


def test_ebay_items_page1_has_available_filters(client, mock_db):
    """Page 1 returns availableFilters with value counts."""
    response = client.post("/ebay/items", json={"name": "MacBookPro"})
    data = response.json()
    assert data["availableFilters"] is not None
    assert "ramSize" in data["availableFilters"]


# ── Integration tests: Search Templates ──


def test_search_templates_returns_matching_docs(client):
    """GET /ebay/search-templates returns docs matching productName."""
    fake_docs = [
        {"productName": "MacBook Pro", "templateName": "Budget", "templateDescription": "Under $500", "filters": {"maxPrice": 500}},
        {"productName": "MacBook Pro", "templateName": "RAM", "templateDescription": "32GB+", "filters": {"ram": "32"}},
    ]
    fake_col = MagicMock()
    fake_col.find.return_value = [dict(d, _id="fake") for d in fake_docs]
    fake_db = {"search_templates": fake_col, "mac_book_pro": FakeCollection(SAMPLE_ITEMS)}
    with patch("main.db", fake_db):
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



