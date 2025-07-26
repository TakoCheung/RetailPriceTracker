"""
TDD tests for Analytics API endpoints.
Following TDD: Write tests first, see them fail, then implement.

Analytics API provides insights into:
- Price trends and historical data
- Product popularity and user engagement
- Provider performance metrics
- Dashboard statistics and reports
"""

from datetime import datetime, timedelta

import pytest
from app.database import get_session
from app.main import app
from app.models import PriceAlert, PriceRecord, Product, Provider, User
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine

# Use the same test engine as main tests
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
def analytics_data(test_db):
    """Create comprehensive test data for analytics."""
    # Create users
    users = [
        User(
            email="user1@example.com",
            name="User One",
            password_hash="hashed_password_1",
            role="ADMIN",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
        User(
            email="user2@example.com",
            name="User Two",
            password_hash="hashed_password_2",
            role="VIEWER",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
    ]

    # Create products
    products = [
        Product(
            name="iPhone 15 Pro",
            url="https://apple.com/iphone-15-pro",
            description="Premium smartphone",
            category="Electronics",
        ),
        Product(
            name="Samsung Galaxy S24",
            url="https://samsung.com/galaxy-s24",
            description="Android flagship",
            category="Electronics",
        ),
        Product(
            name="MacBook Air M3",
            url="https://apple.com/macbook-air",
            description="Lightweight laptop",
            category="Electronics",
        ),
    ]

    # Create providers
    providers = [
        Provider(
            name="Amazon",
            base_url="https://api.amazon.com",
            rate_limit=1000,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
        Provider(
            name="Best Buy",
            base_url="https://api.bestbuy.com",
            rate_limit=500,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
        Provider(
            name="Walmart",
            base_url="https://api.walmart.com",
            rate_limit=750,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
    ]

    # Add all entities
    for entity_list in [users, products, providers]:
        for entity in entity_list:
            test_db.add(entity)
    test_db.commit()

    # Refresh entities to get IDs
    for entity_list in [users, products, providers]:
        for entity in entity_list:
            test_db.refresh(entity)

    # Create price records with historical data (last 30 days)
    price_records = []
    base_date = datetime.utcnow()

    for days_ago in range(30, 0, -1):
        record_date = base_date - timedelta(days=days_ago)

        # iPhone prices declining over time
        iphone_price = 1199.99 - (days_ago * 2)  # $2 decrease per day
        price_records.append(
            PriceRecord(
                product_id=products[0].id,
                provider_id=providers[0].id,  # Amazon
                price=iphone_price,
                currency="USD",
                is_available=True,
                recorded_at=record_date,
            )
        )

        # Samsung prices fluctuating
        samsung_price = 999.99 + (10 * (days_ago % 5))  # Fluctuating pattern
        price_records.append(
            PriceRecord(
                product_id=products[1].id,
                provider_id=providers[1].id,  # Best Buy
                price=samsung_price,
                currency="USD",
                is_available=True,
                recorded_at=record_date,
            )
        )

        # MacBook stable pricing
        macbook_price = 1299.99
        price_records.append(
            PriceRecord(
                product_id=products[2].id,
                provider_id=providers[2].id,  # Walmart
                price=macbook_price,
                currency="USD",
                is_available=days_ago < 5,  # Out of stock for last 5 days
                recorded_at=record_date,
            )
        )

    # Add price records
    for record in price_records:
        test_db.add(record)
    test_db.commit()

    # Create price alerts
    alerts = [
        PriceAlert(
            user_id=users[0].id,
            product_id=products[0].id,
            alert_type="PRICE_DROP",
            threshold_price=1100.00,
            notification_channels=["email"],
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
        PriceAlert(
            user_id=users[1].id,
            product_id=products[1].id,
            alert_type="BACK_IN_STOCK",
            notification_channels=["email"],
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
    ]

    for alert in alerts:
        test_db.add(alert)
    test_db.commit()

    return {
        "users": users,
        "products": products,
        "providers": providers,
        "price_records": price_records,
        "alerts": alerts,
    }


class TestAnalyticsAPI:
    """TDD tests for Analytics API endpoints."""

    def test_get_price_trends_success(self, client, analytics_data):
        """Test retrieving price trends for a product."""
        product_id = analytics_data["products"][0].id  # iPhone

        response = client.get(f"/api/analytics/price-trends/{product_id}")

        assert response.status_code == 200
        data = response.json()
        assert "product_id" in data
        assert "product_name" in data
        assert "trends" in data
        assert "statistics" in data

        # Verify trend data structure
        trends = data["trends"]
        assert isinstance(trends, list)
        assert len(trends) > 0

        # Each trend point should have date and price
        for trend in trends:
            assert "date" in trend
            assert "price" in trend
            assert "is_available" in trend

        # Verify statistics
        stats = data["statistics"]
        assert "current_price" in stats
        assert "average_price" in stats
        assert "min_price" in stats
        assert "max_price" in stats
        assert "price_change_30d" in stats

    def test_get_price_trends_with_date_range(self, client, analytics_data):
        """Test price trends with custom date range."""
        product_id = analytics_data["products"][0].id

        # Get trends for last 7 days
        start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = datetime.utcnow().strftime("%Y-%m-%d")

        response = client.get(
            f"/api/analytics/price-trends/{product_id}?start_date={start_date}&end_date={end_date}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["trends"]) <= 7

    def test_get_price_trends_not_found(self, client):
        """Test price trends for non-existent product."""
        response = client.get("/api/analytics/price-trends/99999")

        assert response.status_code == 404
        data = response.json()
        assert "Product not found" in data["detail"]

    def test_get_popular_products(self, client, analytics_data):
        """Test retrieving most popular products (by alert count)."""
        response = client.get("/api/analytics/popular-products")

        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "total_count" in data

        products = data["products"]
        assert isinstance(products, list)

        for product in products:
            assert "id" in product
            assert "name" in product
            assert "category" in product
            assert "alert_count" in product
            assert "avg_price" in product
            assert "price_records_count" in product

    def test_get_popular_products_with_limit(self, client, analytics_data):
        """Test popular products with limit parameter."""
        response = client.get("/api/analytics/popular-products?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["products"]) <= 2

    def test_get_provider_performance(self, client, analytics_data):
        """Test retrieving provider performance metrics."""
        response = client.get("/api/analytics/provider-performance")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "total_count" in data

        providers = data["providers"]
        assert isinstance(providers, list)

        for provider in providers:
            assert "id" in provider
            assert "name" in provider
            assert "price_records_count" in provider
            assert "avg_price" in provider
            assert "products_tracked" in provider
            assert "last_update" in provider

    def test_get_user_engagement_stats(self, client, analytics_data):
        """Test retrieving user engagement statistics."""
        response = client.get("/api/analytics/user-engagement")

        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "active_users" in data
        assert "total_alerts" in data
        assert "active_alerts" in data
        assert "avg_alerts_per_user" in data
        assert "user_growth" in data

        # User growth should be a list of data points
        assert isinstance(data["user_growth"], list)

    def test_get_dashboard_summary(self, client, analytics_data):
        """Test retrieving dashboard summary statistics."""
        response = client.get("/api/analytics/dashboard")

        assert response.status_code == 200
        data = response.json()

        # Core metrics
        assert "total_products" in data
        assert "total_providers" in data
        assert "total_users" in data
        assert "total_alerts" in data
        assert "total_price_records" in data

        # Recent activity
        assert "recent_price_updates" in data
        assert "recent_alerts" in data

        # Top performers
        assert "top_products" in data
        assert "top_providers" in data

        # Verify structure of recent updates
        recent_updates = data["recent_price_updates"]
        assert isinstance(recent_updates, list)

        for update in recent_updates:
            assert "product_name" in update
            assert "provider_name" in update
            assert "price" in update
            assert "recorded_at" in update

    def test_get_price_comparison(self, client, analytics_data):
        """Test price comparison across providers for a product."""
        product_id = analytics_data["products"][0].id

        response = client.get(f"/api/analytics/price-comparison/{product_id}")

        assert response.status_code == 200
        data = response.json()
        assert "product_id" in data
        assert "product_name" in data
        assert "comparisons" in data
        assert "best_price" in data
        assert "price_spread" in data

        comparisons = data["comparisons"]
        assert isinstance(comparisons, list)

        for comparison in comparisons:
            assert "provider_id" in comparison
            assert "provider_name" in comparison
            assert "current_price" in comparison
            assert "last_updated" in comparison
            assert "is_available" in comparison

    def test_get_availability_trends(self, client, analytics_data):
        """Test product availability trends over time."""
        product_id = analytics_data["products"][2].id  # MacBook (goes out of stock)

        response = client.get(f"/api/analytics/availability-trends/{product_id}")

        assert response.status_code == 200
        data = response.json()
        assert "product_id" in data
        assert "availability_history" in data
        assert "current_availability" in data
        assert "availability_percentage" in data

        history = data["availability_history"]
        assert isinstance(history, list)

        for entry in history:
            assert "date" in entry
            assert "is_available" in entry
            assert "provider_count" in entry

    def test_get_analytics_with_authentication(self, client, analytics_data):
        """Test analytics endpoints require authentication (when implemented)."""
        # For now, this test documents the future authentication requirement
        # When authentication is added to analytics endpoints, this test should be updated

        response = client.get("/api/analytics/dashboard")

        # Currently should work without auth, but this documents the future requirement
        assert response.status_code == 200

    def test_get_price_trends_aggregation_daily(self, client, analytics_data):
        """Test price trends with daily aggregation."""
        product_id = analytics_data["products"][0].id

        response = client.get(
            f"/api/analytics/price-trends/{product_id}?aggregation=daily"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["aggregation"] == "daily"

    def test_get_price_trends_aggregation_weekly(self, client, analytics_data):
        """Test price trends with weekly aggregation."""
        product_id = analytics_data["products"][0].id

        response = client.get(
            f"/api/analytics/price-trends/{product_id}?aggregation=weekly"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["aggregation"] == "weekly"

    def test_analytics_api_error_handling(self, client):
        """Test analytics API error handling."""
        # Test invalid aggregation parameter
        response = client.get("/api/analytics/price-trends/1?aggregation=invalid")

        assert response.status_code == 422
        data = response.json()
        assert "Invalid aggregation" in data["detail"]
