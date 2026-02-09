import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


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


def test_unhandled_error_returns_structured_envelope():
    """Unhandled exceptions (e.g. invalid sort direction) return structured error envelope."""
    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.post("/ebay/items", json={
            "name": "MacBookPro",
            "sortSpecs": [{"field": "price", "direction": 10}],
        })
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert isinstance(data["error"]["message"], str)
