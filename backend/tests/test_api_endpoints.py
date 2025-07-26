"""
TDD tests for Price Tracking API endpoints.
Following TDD: Write tests first, see them fail, then implement.
"""

import pytest
from app.database import get_session
from app.main import app
from app.models import Product
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine

# Create a global test engine that works across threads
TEST_DATABASE_URL = "sqlite:///test.db"
test_engine = create_engine(TEST_DATABASE_URL, echo=True)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Setup test database once for the entire session."""
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def test_db():
    """Create a test database session."""
    # Clear any existing data before each test
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)

    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_db):
    """Create a test client with database dependency override."""

    def get_test_session():
        SessionLocal = sessionmaker(bind=test_engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = get_test_session
    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_products(test_db):
    """Create sample products for testing."""
    products = [
        Product(
            name="iPhone 15",
            url="https://apple.com/iphone-15",
            description="Latest iPhone model",
            category="Electronics",
        ),
        Product(
            name="MacBook Pro",
            url="https://apple.com/macbook-pro",
            description="Professional laptop",
            category="Electronics",
        ),
    ]

    for product in products:
        test_db.add(product)
    test_db.commit()

    for product in products:
        test_db.refresh(product)

    return products


class TestProductAPI:
    """TDD tests for Product API endpoints."""

    def test_create_product_success(self, client):
        """Test creating a product via API."""
        product_data = {
            "name": "iPad Pro",
            "url": "https://apple.com/ipad-pro",
            "description": "Professional tablet",
            "category": "Electronics",
        }

        response = client.post("/api/products/", json=product_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "iPad Pro"
        assert data["category"] == "Electronics"
        assert "id" in data
        assert "created_at" in data

    def test_create_product_invalid_name(self, client):
        """Test creating product with invalid name fails."""
        product_data = {
            "name": "X",  # Too short
            "url": "https://example.com",
            "category": "Electronics",
        }

        response = client.post("/api/products/", json=product_data)

        assert response.status_code == 422
        assert "validation error" in response.json()["detail"]

    def test_get_products_list(self, client, sample_products):
        """Test retrieving list of products."""
        response = client.get("/api/products/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] in ["iPhone 15", "MacBook Pro"]

    def test_get_product_by_id(self, client, sample_products):
        """Test retrieving a specific product by ID."""
        product_id = sample_products[0].id

        response = client.get(f"/api/products/{product_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "iPhone 15"
        assert data["id"] == product_id

    def test_get_product_not_found(self, client):
        """Test retrieving non-existent product returns 404."""
        response = client.get("/api/products/99999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_product(self, client, sample_products):
        """Test updating an existing product."""
        product_id = sample_products[0].id
        update_data = {"name": "iPhone 15 Pro", "description": "Updated iPhone model"}

        response = client.patch(f"/api/products/{product_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "iPhone 15 Pro"
        assert data["description"] == "Updated iPhone model"

    def test_delete_product(self, client, sample_products):
        """Test deleting a product."""
        product_id = sample_products[0].id

        response = client.delete(f"/api/products/{product_id}")

        assert response.status_code == 204

        # Verify it's actually deleted
        get_response = client.get(f"/api/products/{product_id}")
        assert get_response.status_code == 404


class TestProviderAPI:
    """TDD tests for Provider API endpoints."""

    def test_create_provider_success(self, client):
        """Test creating a provider via API."""
        provider_data = {
            "name": "Amazon",
            "base_url": "https://api.amazon.com",
            "rate_limit": 1000,
        }

        response = client.post("/api/providers/", json=provider_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Amazon"
        assert data["rate_limit"] == 1000
        assert data["is_active"] is True

    def test_create_provider_invalid_rate_limit(self, client):
        """Test creating provider with invalid rate limit fails."""
        provider_data = {
            "name": "Invalid Provider",
            "base_url": "https://example.com",
            "rate_limit": 0,  # Invalid
        }

        response = client.post("/api/providers/", json=provider_data)

        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(
            "Rate limit must be greater than 0" in str(error) for error in errors
        )


class TestPriceRecordAPI:
    """TDD tests for Price Record API endpoints."""

    def test_add_price_record(self, client, sample_products):
        """Test adding a price record for a product."""
        # First create a provider
        provider_data = {
            "name": "Amazon",
            "base_url": "https://api.amazon.com",
            "rate_limit": 1000,
        }
        provider_response = client.post("/api/providers/", json=provider_data)
        provider_id = provider_response.json()["id"]

        # Now add price record
        price_data = {
            "product_id": sample_products[0].id,
            "provider_id": provider_id,
            "price": 999.99,
            "currency": "USD",
            "is_available": True,
        }

        response = client.post("/api/price-records/", json=price_data)

        assert response.status_code == 201
        data = response.json()
        assert data["price"] == 999.99
        assert data["currency"] == "USD"
        assert data["is_available"] is True

    def test_get_price_history(self, client, sample_products):
        """Test retrieving price history for a product."""
        product_id = sample_products[0].id

        response = client.get(f"/api/products/{product_id}/price-history")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestHealthAPI:
    """TDD tests for health and status endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
