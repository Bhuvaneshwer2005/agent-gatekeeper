# Tests for the catalog service and the /catalog endpoint.

from fastapi.testclient import TestClient

from app.catalog.catalog_service import get_catalog
from app.main import app

client = TestClient(app)

EXPECTED_FIELDS = {"sku", "name", "price", "category", "stock", "upsell_eligible"}


def test_get_catalog_returns_validated_products():
    products = get_catalog()
    assert 3 <= len(products) <= 4
    assert all(product.price > 0 for product in products)
    assert all(product.stock >= 0 for product in products)


def test_catalog_skus_are_unique():
    products = get_catalog()
    skus = [product.sku for product in products]
    assert len(skus) == len(set(skus))


def test_catalog_endpoint_returns_expected_fields():
    response = client.get("/catalog")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 3
    assert set(body[0].keys()) == EXPECTED_FIELDS


def test_catalog_endpoint_includes_at_least_one_upsell_eligible_item():
    response = client.get("/catalog")
    body = response.json()
    assert any(item["upsell_eligible"] for item in body)
