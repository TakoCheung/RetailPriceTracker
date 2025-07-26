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

    def test_get_providers_list(self, client):
        """Test retrieving list of providers."""
        # First create a provider
        provider_data = {
            "name": "Amazon",
            "base_url": "https://api.amazon.com",
            "rate_limit": 1000,
        }
        client.post("/api/providers/", json=provider_data)

        response = client.get("/api/providers/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] == "Amazon"

    def test_get_provider_by_id(self, client):
        """Test retrieving a provider by ID."""
        # First create a provider
        provider_data = {
            "name": "eBay",
            "base_url": "https://api.ebay.com",
            "rate_limit": 500,
        }
        create_response = client.post("/api/providers/", json=provider_data)
        provider_id = create_response.json()["id"]

        response = client.get(f"/api/providers/{provider_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "eBay"
        assert data["rate_limit"] == 500

    def test_get_provider_not_found(self, client):
        """Test retrieving non-existent provider returns 404."""
        response = client.get("/api/providers/999")
        assert response.status_code == 404

    def test_update_provider(self, client):
        """Test updating a provider."""
        # First create a provider
        provider_data = {
            "name": "Walmart",
            "base_url": "https://api.walmart.com",
            "rate_limit": 300,
        }
        create_response = client.post("/api/providers/", json=provider_data)
        provider_id = create_response.json()["id"]

        # Update the provider
        update_data = {
            "name": "Walmart Updated",
            "rate_limit": 400,
        }
        response = client.patch(f"/api/providers/{provider_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Walmart Updated"
        assert data["rate_limit"] == 400

    def test_delete_provider(self, client):
        """Test deleting a provider."""
        # First create a provider
        provider_data = {
            "name": "Target",
            "base_url": "https://api.target.com",
            "rate_limit": 200,
        }
        create_response = client.post("/api/providers/", json=provider_data)
        provider_id = create_response.json()["id"]

        # Delete the provider
        response = client.delete(f"/api/providers/{provider_id}")
        assert response.status_code == 204

        # Verify it's deleted
        get_response = client.get(f"/api/providers/{provider_id}")
        assert get_response.status_code == 404


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

    def test_get_all_price_records(self, client, sample_products):
        """Test retrieving all price records."""
        # First create a provider and price record
        provider_data = {
            "name": "BestBuy",
            "base_url": "https://api.bestbuy.com",
            "rate_limit": 500,
        }
        provider_response = client.post("/api/providers/", json=provider_data)
        provider_id = provider_response.json()["id"]

        price_data = {
            "product_id": sample_products[0].id,
            "provider_id": provider_id,
            "price": 799.99,
            "currency": "USD",
            "is_available": True,
        }
        client.post("/api/price-records/", json=price_data)

        # Test getting all price records
        response = client.get("/api/price-records/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["price"] == 799.99

    def test_get_price_record_by_id(self, client, sample_products):
        """Test retrieving a specific price record by ID."""
        # First create a provider and price record
        provider_data = {
            "name": "Walmart",
            "base_url": "https://api.walmart.com",
            "rate_limit": 750,
        }
        provider_response = client.post("/api/providers/", json=provider_data)
        provider_id = provider_response.json()["id"]

        price_data = {
            "product_id": sample_products[0].id,
            "provider_id": provider_id,
            "price": 649.99,
            "currency": "USD",
            "is_available": True,
        }
        create_response = client.post("/api/price-records/", json=price_data)
        price_record_id = create_response.json()["id"]

        # Test getting specific price record
        response = client.get(f"/api/price-records/{price_record_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == price_record_id
        assert data["price"] == 649.99
        assert data["currency"] == "USD"

    def test_update_price_record(self, client, sample_products):
        """Test updating an existing price record."""
        # First create a provider and price record
        provider_data = {
            "name": "Target",
            "base_url": "https://api.target.com",
            "rate_limit": 600,
        }
        provider_response = client.post("/api/providers/", json=provider_data)
        provider_id = provider_response.json()["id"]

        price_data = {
            "product_id": sample_products[0].id,
            "provider_id": provider_id,
            "price": 899.99,
            "currency": "USD",
            "is_available": True,
        }
        create_response = client.post("/api/price-records/", json=price_data)
        price_record_id = create_response.json()["id"]

        # Update the price record
        update_data = {
            "price": 799.99,
            "is_available": False,
        }
        response = client.patch(
            f"/api/price-records/{price_record_id}", json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == price_record_id
        assert data["price"] == 799.99
        assert data["is_available"] is False
        assert data["currency"] == "USD"  # Should remain unchanged

    def test_delete_price_record(self, client, sample_products):
        """Test deleting a price record."""
        # First create a provider and price record
        provider_data = {
            "name": "Newegg",
            "base_url": "https://api.newegg.com",
            "rate_limit": 400,
        }
        provider_response = client.post("/api/providers/", json=provider_data)
        provider_id = provider_response.json()["id"]

        price_data = {
            "product_id": sample_products[0].id,
            "provider_id": provider_id,
            "price": 1099.99,
            "currency": "USD",
            "is_available": True,
        }
        create_response = client.post("/api/price-records/", json=price_data)
        price_record_id = create_response.json()["id"]

        # Delete the price record
        response = client.delete(f"/api/price-records/{price_record_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/api/price-records/{price_record_id}")
        assert get_response.status_code == 404

    def test_get_price_record_not_found(self, client):
        """Test getting a non-existent price record."""
        response = client.get("/api/price-records/99999")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestUserAPI:
    """TDD tests for User API endpoints."""

    def test_create_user_success(self, client):
        """Test creating a new user successfully."""
        user_data = {
            "email": "john.doe@example.com",
            "name": "John Doe",
            "role": "admin",
        }

        response = client.post("/api/users/", json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "john.doe@example.com"
        assert data["name"] == "John Doe"
        assert data["role"] == "admin"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_user_invalid_email(self, client):
        """Test creating a user with invalid email."""
        user_data = {
            "email": "invalid-email",
            "name": "John Doe",
            "role": "ADMIN",
        }

        response = client.post("/api/users/", json=user_data)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_get_users_list(self, client):
        """Test retrieving list of users."""
        # First create a user
        user_data = {
            "email": "create.user@example.com",
            "name": "Create User",
            "role": "viewer",
        }
        client.post("/api/users/", json=user_data)

        # Test getting users list
        response = client.get("/api/users/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["email"] == "create.user@example.com"

    def test_get_user_by_id(self, client):
        """Test retrieving a specific user by ID."""
        # First create a user
        user_data = {
            "email": "bob.smith@example.com",
            "name": "Bob Smith",
            "role": "admin",
        }
        create_response = client.post("/api/users/", json=user_data)
        user_id = create_response.json()["id"]

        # Test getting specific user
        response = client.get(f"/api/users/{user_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id
        assert data["email"] == "bob.smith@example.com"
        assert data["name"] == "Bob Smith"
        assert data["role"] == "admin"

    def test_update_user(self, client):
        """Test updating an existing user."""
        # First create a user
        user_data = {
            "email": "alice.brown@example.com",
            "name": "Alice Brown",
            "role": "viewer",
        }
        create_response = client.post("/api/users/", json=user_data)
        user_id = create_response.json()["id"]

        # Update the user
        update_data = {
            "name": "Alice Johnson",
            "role": "admin",
            "is_active": False,
        }
        response = client.patch(f"/api/users/{user_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id
        assert data["name"] == "Alice Johnson"
        assert data["role"] == "admin"
        assert data["is_active"] is False
        assert data["email"] == "alice.brown@example.com"  # Should remain unchanged

    def test_delete_user(self, client):
        """Test deleting a user."""
        # First create a user
        user_data = {
            "email": "charlie.wilson@example.com",
            "name": "Charlie Wilson",
            "role": "admin",
        }
        create_response = client.post("/api/users/", json=user_data)
        user_id = create_response.json()["id"]

        # Delete the user
        response = client.delete(f"/api/users/{user_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/api/users/{user_id}")
        assert get_response.status_code == 404

    def test_get_user_not_found(self, client):
        """Test getting a non-existent user."""
        response = client.get("/api/users/99999")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestAlertAPI:
    """TDD tests for Alert API endpoints."""

    def test_create_alert_success(self, client, sample_products):
        """Test creating a price alert successfully."""
        # First create a user
        user_data = {
            "email": "alert.user@example.com",
            "name": "Alert User",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        # Create the alert
        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "price_drop",
            "threshold_price": 899.99,
            "notification_channels": ["email"],
        }

        response = client.post("/api/alerts/", json=alert_data)

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == user_id
        assert data["product_id"] == sample_products[0].id
        assert data["alert_type"] == "price_drop"
        assert data["threshold_price"] == 899.99
        assert data["notification_channels"] == ["email"]
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data

    def test_create_alert_invalid_type(self, client, sample_products):
        """Test creating alert with invalid alert type."""
        user_data = {
            "email": "test2@example.com",
            "name": "Test User 2",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "invalid_type",
            "threshold_price": 899.99,
        }

        response = client.post("/api/alerts/", json=alert_data)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_create_alert_missing_threshold_for_price_alert(
        self, client, sample_products
    ):
        """Test creating price alert without threshold fails."""
        user_data = {
            "email": "threshold.test@example.com",
            "name": "Threshold Test",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "price_drop",
            # Missing threshold_price
            "notification_channels": ["email"],
        }

        response = client.post("/api/alerts/", json=alert_data)

        assert response.status_code == 422
        data = response.json()
        assert "threshold_price is required" in data["detail"]

    def test_create_alert_invalid_notification_channel(self, client, sample_products):
        """Test creating alert with invalid notification channel."""
        user_data = {
            "email": "channel.test@example.com",
            "name": "Channel Test",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "back_in_stock",
            "notification_channels": ["invalid_channel"],
        }

        response = client.post("/api/alerts/", json=alert_data)

        assert response.status_code == 422
        data = response.json()
        assert "Invalid notification channel" in data["detail"]

    def test_get_alerts_list(self, client, sample_products):
        """Test retrieving list of alerts."""
        # First create a user and alert
        user_data = {
            "email": "list.user@example.com",
            "name": "List User",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "back_in_stock",
            "notification_channels": ["email", "webhook"],
        }
        client.post("/api/alerts/", json=alert_data)

        # Test getting alerts list
        response = client.get("/api/alerts/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["alert_type"] == "back_in_stock"

    def test_get_alerts_filtered_by_user(self, client, sample_products):
        """Test retrieving alerts filtered by user ID."""
        # Create two users
        user1_data = {
            "email": "filter1.user@example.com",
            "name": "Filter User 1",
            "role": "admin",
        }
        user1_response = client.post("/api/users/", json=user1_data)
        user1_id = user1_response.json()["id"]

        user2_data = {
            "email": "filter2.user@example.com",
            "name": "Filter User 2",
            "role": "admin",
        }
        user2_response = client.post("/api/users/", json=user2_data)
        user2_id = user2_response.json()["id"]

        # Create alerts for both users
        alert1_data = {
            "user_id": user1_id,
            "product_id": sample_products[0].id,
            "alert_type": "back_in_stock",
            "notification_channels": ["email"],
        }
        client.post("/api/alerts/", json=alert1_data)

        alert2_data = {
            "user_id": user2_id,
            "product_id": sample_products[0].id,
            "alert_type": "out_of_stock",
            "notification_channels": ["email"],
        }
        client.post("/api/alerts/", json=alert2_data)

        # Test filtering by user1
        response = client.get(f"/api/alerts/?user_id={user1_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        for alert in data:
            assert alert["user_id"] == user1_id

    def test_get_alert_by_id(self, client, sample_products):
        """Test retrieving a specific alert by ID."""
        user_data = {
            "email": "specific.user@example.com",
            "name": "Specific User",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "price_increase",
            "threshold_price": 1200.00,
            "notification_channels": ["sms"],
        }
        create_response = client.post("/api/alerts/", json=alert_data)
        alert_id = create_response.json()["id"]

        # Test getting specific alert
        response = client.get(f"/api/alerts/{alert_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == alert_id
        assert data["alert_type"] == "price_increase"
        assert data["threshold_price"] == 1200.00

    def test_update_alert(self, client, sample_products):
        """Test updating an existing alert."""
        user_data = {
            "email": "update.user@example.com",
            "name": "Update User",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "price_drop",
            "threshold_price": 800.00,
            "notification_channels": ["email"],
        }
        create_response = client.post("/api/alerts/", json=alert_data)
        alert_id = create_response.json()["id"]

        # Update the alert
        update_data = {
            "threshold_price": 750.00,
            "notification_channels": ["email", "webhook"],
            "is_active": False,
        }
        response = client.patch(f"/api/alerts/{alert_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == alert_id
        assert data["threshold_price"] == 750.00
        assert data["notification_channels"] == ["email", "webhook"]
        assert data["is_active"] is False

    def test_delete_alert(self, client, sample_products):
        """Test deleting an alert."""
        user_data = {
            "email": "delete.user@example.com",
            "name": "Delete User",
            "role": "admin",
        }
        user_response = client.post("/api/users/", json=user_data)
        user_id = user_response.json()["id"]

        alert_data = {
            "user_id": user_id,
            "product_id": sample_products[0].id,
            "alert_type": "out_of_stock",
            "notification_channels": ["email"],
        }
        create_response = client.post("/api/alerts/", json=alert_data)
        alert_id = create_response.json()["id"]

        # Delete the alert
        response = client.delete(f"/api/alerts/{alert_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/api/alerts/{alert_id}")
        assert get_response.status_code == 404

    def test_get_alert_not_found(self, client):
        """Test getting a non-existent alert."""
        response = client.get("/api/alerts/99999")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


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
