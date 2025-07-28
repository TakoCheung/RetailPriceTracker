"""
TDD tests for Advanced Search & Filtering API endpoints.
Following TDD: Write tests first, see them fail, then implement.

Search API provides:
- Full-text search across products
- Advanced filtering capabilities
- Sorting and pagination
- Search suggestions and analytics
"""

from datetime import datetime

import pytest
from app.database import get_session
from app.main import app
from app.models import PriceRecord, Product, Provider
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
def search_test_data(test_db):
    """Create comprehensive test data for search functionality."""
    # Create diverse products
    products = [
        Product(
            name="iPhone 15 Pro Max",
            url="https://apple.com/iphone-15-pro-max",
            description="Latest flagship smartphone with advanced camera system and titanium design",
            category="Electronics",
        ),
        Product(
            name="Samsung Galaxy S24 Ultra",
            url="https://samsung.com/galaxy-s24-ultra",
            description="Premium Android smartphone with S Pen and exceptional camera capabilities",
            category="Electronics",
        ),
        Product(
            name="MacBook Pro 16-inch",
            url="https://apple.com/macbook-pro-16",
            description="Professional laptop with M3 Pro chip for developers and creators",
            category="Electronics",
        ),
        Product(
            name="Dell XPS 13 Laptop",
            url="https://dell.com/xps-13",
            description="Ultrabook with stunning display and premium build quality",
            category="Electronics",
        ),
        Product(
            name="Sony WH-1000XM5 Headphones",
            url="https://sony.com/wh-1000xm5",
            description="Industry-leading noise canceling wireless headphones",
            category="Audio",
        ),
        Product(
            name="Apple AirPods Pro",
            url="https://apple.com/airpods-pro",
            description="Premium wireless earbuds with active noise cancellation",
            category="Audio",
        ),
        Product(
            name="Nike Air Max 270",
            url="https://nike.com/air-max-270",
            description="Comfortable running shoes with Air Max technology",
            category="Footwear",
        ),
        Product(
            name="Adidas Ultraboost 22",
            url="https://adidas.com/ultraboost-22",
            description="High-performance running shoes with Boost midsole",
            category="Footwear",
        ),
    ]

    # Create provider
    provider = Provider(
        name="TechStore",
        base_url="https://api.techstore.com",
        rate_limit=1000,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Add all entities
    for product in products:
        test_db.add(product)
    test_db.add(provider)
    test_db.commit()

    # Refresh to get IDs
    for product in products:
        test_db.refresh(product)
    test_db.refresh(provider)

    # Create price records for products
    price_records = [
        # iPhone 15 Pro Max - premium pricing
        PriceRecord(
            product_id=products[0].id,
            provider_id=provider.id,
            price=1199.99,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        ),
        # Samsung Galaxy S24 Ultra - premium pricing
        PriceRecord(
            product_id=products[1].id,
            provider_id=provider.id,
            price=1299.99,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        ),
        # MacBook Pro - high-end pricing
        PriceRecord(
            product_id=products[2].id,
            provider_id=provider.id,
            price=2499.99,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        ),
        # Dell XPS 13 - mid-range pricing
        PriceRecord(
            product_id=products[3].id,
            provider_id=provider.id,
            price=999.99,
            currency="USD",
            is_available=False,  # Out of stock
            recorded_at=datetime.utcnow(),
        ),
        # Sony Headphones - mid-range pricing
        PriceRecord(
            product_id=products[4].id,
            provider_id=provider.id,
            price=399.99,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        ),
        # Apple AirPods Pro - premium accessory
        PriceRecord(
            product_id=products[5].id,
            provider_id=provider.id,
            price=249.99,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        ),
        # Nike Air Max - affordable footwear
        PriceRecord(
            product_id=products[6].id,
            provider_id=provider.id,
            price=130.00,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        ),
        # Adidas Ultraboost - premium footwear
        PriceRecord(
            product_id=products[7].id,
            provider_id=provider.id,
            price=180.00,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        ),
    ]

    for record in price_records:
        test_db.add(record)
    test_db.commit()

    return {
        "products": products,
        "provider": provider,
        "price_records": price_records,
    }


class TestSearchAPI:
    """TDD tests for Search API endpoints."""

    def test_search_products_by_name(self, client, search_test_data):
        """Test searching products by name."""
        response = client.get("/api/search/products?query=iPhone")

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_count" in data
        assert "search_time_ms" in data

        results = data["results"]
        assert len(results) >= 1

        # Should find iPhone products
        iphone_found = any("iPhone" in result["name"] for result in results)
        assert iphone_found

        # Verify result structure
        for result in results:
            assert "id" in result
            assert "name" in result
            assert "description" in result
            assert "category" in result
            assert "current_price" in result
            assert "is_available" in result

    def test_search_products_by_description(self, client, search_test_data):
        """Test searching products by description content."""
        response = client.get("/api/search/products?query=camera")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Should find products with "camera" in description
        camera_found = any(
            "camera" in result["description"].lower() for result in results
        )
        assert camera_found

    def test_search_products_case_insensitive(self, client, search_test_data):
        """Test that search is case insensitive."""
        # Test with different cases
        response_lower = client.get("/api/search/products?query=macbook")
        response_upper = client.get("/api/search/products?query=MACBOOK")
        response_mixed = client.get("/api/search/products?query=MacBook")

        assert response_lower.status_code == 200
        assert response_upper.status_code == 200
        assert response_mixed.status_code == 200

        # All should return same results
        results_lower = response_lower.json()["results"]
        results_upper = response_upper.json()["results"]
        results_mixed = response_mixed.json()["results"]

        assert len(results_lower) == len(results_upper) == len(results_mixed)

    def test_search_products_with_category_filter(self, client, search_test_data):
        """Test searching with category filter."""
        response = client.get("/api/search/products?category=Audio")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # All results should be in Audio category
        for result in results:
            assert result["category"] == "Audio"

        # Should find Audio products
        assert len(results) >= 2  # Sony headphones and AirPods

    def test_search_products_with_price_range_filter(self, client, search_test_data):
        """Test searching with price range filter."""
        response = client.get("/api/search/products?min_price=200&max_price=500")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # All results should be within price range
        for result in results:
            if result["current_price"]:
                assert 200 <= result["current_price"] <= 500

    def test_search_products_availability_filter(self, client, search_test_data):
        """Test filtering by product availability."""
        # Test only available products
        response = client.get("/api/search/products?available_only=true")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # All results should be available
        for result in results:
            assert result["is_available"] is True

    def test_search_products_sorting(self, client, search_test_data):
        """Test product search with sorting options."""
        # Test sorting by price ascending
        response_price_asc = client.get(
            "/api/search/products?sort_by=price&sort_order=asc"
        )

        assert response_price_asc.status_code == 200
        results_asc = response_price_asc.json()["results"]

        # Verify ascending price order
        prices = [r["current_price"] for r in results_asc if r["current_price"]]
        assert prices == sorted(prices)

        # Test sorting by price descending
        response_price_desc = client.get(
            "/api/search/products?sort_by=price&sort_order=desc"
        )

        assert response_price_desc.status_code == 200
        results_desc = response_price_desc.json()["results"]

        prices_desc = [r["current_price"] for r in results_desc if r["current_price"]]
        assert prices_desc == sorted(prices_desc, reverse=True)

    def test_search_products_pagination(self, client, search_test_data):
        """Test search results pagination."""
        # Get first page with limit
        response_page1 = client.get("/api/search/products?limit=3&offset=0")

        assert response_page1.status_code == 200
        data_page1 = response_page1.json()
        assert len(data_page1["results"]) <= 3

        # Get second page
        response_page2 = client.get("/api/search/products?limit=3&offset=3")

        assert response_page2.status_code == 200
        data_page2 = response_page2.json()

        # Results should be different
        page1_ids = {r["id"] for r in data_page1["results"]}
        page2_ids = {r["id"] for r in data_page2["results"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_search_products_empty_query(self, client, search_test_data):
        """Test search with empty query returns all products."""
        response = client.get("/api/search/products")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Should return all products
        assert len(results) >= 8  # We have 8 test products

    def test_search_products_no_results(self, client, search_test_data):
        """Test search with query that has no matches."""
        response = client.get("/api/search/products?query=nonexistentproduct")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["results"]) == 0

    def test_search_suggestions(self, client, search_test_data):
        """Test search suggestions/autocomplete."""
        response = client.get("/api/search/suggestions?q=iph")

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data

        suggestions = data["suggestions"]
        assert isinstance(suggestions, list)

        # Should suggest iPhone-related terms
        iphone_suggestions = [s for s in suggestions if "iphone" in s.lower()]
        assert len(iphone_suggestions) >= 1

    def test_search_facets(self, client, search_test_data):
        """Test search facets for filtering."""
        response = client.get("/api/search/facets")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "price_ranges" in data
        assert "availability" in data

        # Verify category facets
        categories = data["categories"]
        assert isinstance(categories, list)

        for category in categories:
            assert "name" in category
            assert "count" in category
            assert category["count"] > 0

    def test_search_analytics_tracking(self, client, search_test_data):
        """Test that search queries are tracked for analytics."""
        # Perform a search
        response = client.get("/api/search/products?query=iPhone")
        assert response.status_code == 200

        # Check search analytics
        analytics_response = client.get("/api/search/analytics")

        assert analytics_response.status_code == 200
        data = analytics_response.json()
        assert "popular_queries" in data
        assert "search_volume" in data
        assert "top_categories" in data

    def test_advanced_search_filters_combination(self, client, search_test_data):
        """Test combining multiple search filters."""
        response = client.get(
            "/api/search/products?"
            "query=smartphone&"
            "category=Electronics&"
            "min_price=1000&"
            "max_price=1500&"
            "available_only=true&"
            "sort_by=price&"
            "sort_order=asc"
        )

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Verify all filters are applied
        for result in results:
            # Should contain smartphone-related terms or be electronics
            assert (
                "smartphone" in result["name"].lower()
                or "smartphone" in result["description"].lower()
                or result["category"] == "Electronics"
            )
            assert result["category"] == "Electronics"
            if result["current_price"]:
                assert 1000 <= result["current_price"] <= 1500
            assert result["is_available"] is True

    def test_search_performance(self, client, search_test_data):
        """Test search performance metrics."""
        response = client.get("/api/search/products?query=laptop")

        assert response.status_code == 200
        data = response.json()
        assert "search_time_ms" in data

        # Search should be reasonably fast (under 1 second)
        assert data["search_time_ms"] < 1000

    def test_search_error_handling(self, client, search_test_data):
        """Test search API error handling."""
        # Test invalid sort order
        response = client.get("/api/search/products?sort_order=invalid")

        assert response.status_code == 422
        data = response.json()
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0
        error = data["detail"][0]
        assert error["loc"] == ["query", "sort_order"]
        assert "pattern" in error["msg"] or "asc|desc" in error["msg"]

    def test_search_export_results(self, client, search_test_data):
        """Test exporting search results."""
        response = client.get("/api/search/products/export?query=laptop&format=json")

        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "exported_at" in data
        assert "total_count" in data

    def test_search_saved_searches(self, client, search_test_data):
        """Test saving and retrieving search queries."""
        # Save a search
        search_data = {
            "name": "Premium Smartphones",
            "query": "smartphone",
            "filters": {
                "category": "Electronics",
                "min_price": 1000,
                "max_price": 1500,
            },
        }

        save_response = client.post("/api/search/saved", json=search_data)

        assert save_response.status_code == 201
        saved_data = save_response.json()
        assert "id" in saved_data
        assert saved_data["name"] == "Premium Smartphones"

        # Retrieve saved searches
        list_response = client.get("/api/search/saved")

        assert list_response.status_code == 200
        saved_searches = list_response.json()
        assert isinstance(saved_searches, list)
        assert len(saved_searches) >= 1
