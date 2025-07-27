"""
TDD tests for Advanced Search & Filtering API.
Following TDD: Write comprehensive tests first (RED), then implement functionality (GREEN), then optimize (REFACTOR).

This iteration adds advanced search capabilities to our price tracking system:
- Complex product search with multiple filters
- Price range and historical price filtering
- Category-based filtering and faceted search
- Full-text search with relevance scoring
- Search result pagination and sorting
- Search analytics and query optimization
"""

from datetime import datetime, timedelta

import pytest
from app.database import get_session
from app.main import app
from app.models import PriceRecord, Product, Provider
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine

# Use the same test engine setup as existing tests
TEST_DATABASE_URL = "sqlite:///test_advanced_search.db"
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
def sample_search_data(test_db):
    """Create comprehensive sample data for search testing."""
    # Create providers
    providers = [
        Provider(
            name="Amazon",
            base_url="https://api.amazon.com",
            rate_limit=1000,
            is_active=True,
        ),
        Provider(
            name="BestBuy",
            base_url="https://api.bestbuy.com",
            rate_limit=500,
            is_active=True,
        ),
        Provider(
            name="Walmart",
            base_url="https://api.walmart.com",
            rate_limit=750,
            is_active=True,
        ),
    ]

    for provider in providers:
        test_db.add(provider)
    test_db.commit()

    for provider in providers:
        test_db.refresh(provider)

    # Create diverse products for search testing
    products = [
        Product(
            name="iPhone 15 Pro Max",
            url="https://apple.com/iphone-15-pro-max",
            description="Latest premium iPhone with advanced camera system",
            category="Electronics",
            status="ACTIVE",
        ),
        Product(
            name="Samsung Galaxy S24 Ultra",
            url="https://samsung.com/galaxy-s24-ultra",
            description="Premium Android smartphone with S Pen",
            category="Electronics",
            status="ACTIVE",
        ),
        Product(
            name="MacBook Pro 16-inch",
            url="https://apple.com/macbook-pro-16",
            description="Professional laptop for creative work",
            category="Computers",
            status="ACTIVE",
        ),
        Product(
            name="Dell XPS 13",
            url="https://dell.com/xps-13",
            description="Ultrabook for business and productivity",
            category="Computers",
            status="ACTIVE",
        ),
        Product(
            name="Sony WH-1000XM5",
            url="https://sony.com/wh-1000xm5",
            description="Premium noise-canceling headphones",
            category="Audio",
            status="ACTIVE",
        ),
        Product(
            name="AirPods Pro 2nd Gen",
            url="https://apple.com/airpods-pro",
            description="Wireless earbuds with active noise cancellation",
            category="Audio",
            status="ACTIVE",
        ),
        Product(
            name="Nintendo Switch OLED",
            url="https://nintendo.com/switch-oled",
            description="Portable gaming console with OLED screen",
            category="Gaming",
            status="ACTIVE",
        ),
        Product(
            name="PlayStation 5",
            url="https://playstation.com/ps5",
            description="Next-generation gaming console",
            category="Gaming",
            status="DISCONTINUED",  # Different status for filtering
        ),
    ]

    for product in products:
        test_db.add(product)
    test_db.commit()

    for product in products:
        test_db.refresh(product)

    # Create price records with historical data and varying prices
    base_prices = [1199, 1399, 2499, 999, 399, 249, 349, 499]

    for i, (product, base_price) in enumerate(zip(products, base_prices)):
        # Create price history over last 30 days
        for days_ago in range(30, 0, -3):  # Every 3 days
            price_variation = base_price * (
                0.9 + (days_ago % 10) * 0.02
            )  # ±10% variation

            for provider in providers:
                price_record = PriceRecord(
                    product_id=product.id,
                    provider_id=provider.id,
                    price=round(
                        price_variation + (provider.id * 10), 2
                    ),  # Small provider variance
                    currency="USD",
                    is_available=True,
                    recorded_at=datetime.utcnow() - timedelta(days=days_ago),
                )
                test_db.add(price_record)

    test_db.commit()

    return {
        "products": products,
        "providers": providers,
        "categories": ["Electronics", "Computers", "Audio", "Gaming"],
        "price_ranges": [(200, 500), (500, 1000), (1000, 1500), (1500, 3000)],
    }


class TestBasicSearch:
    """Test basic search functionality."""

    def test_search_products_by_name(self, client, sample_search_data):
        """Test searching products by name."""
        response = client.get("/api/search/products?q=iPhone")

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

        # Should find iPhone products
        results = data["results"]
        assert len(results) > 0
        assert any("iPhone" in product["name"] for product in results)

    def test_search_products_case_insensitive(self, client, sample_search_data):
        """Test search is case insensitive."""
        response = client.get("/api/search/products?q=iphone")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) > 0
        assert any("iPhone" in product["name"] for product in results)

    def test_search_products_by_description(self, client, sample_search_data):
        """Test searching products by description."""
        response = client.get("/api/search/products?q=premium")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) > 0
        assert any("premium" in product["description"].lower() for product in results)

    def test_search_products_empty_query(self, client, sample_search_data):
        """Test search with empty query returns all products."""
        response = client.get("/api/search/products")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 8  # All products in sample data
        assert len(data["results"]) <= data["per_page"]

    def test_search_products_no_results(self, client, sample_search_data):
        """Test search with no matching results."""
        response = client.get("/api/search/products?q=nonexistentproduct")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["results"]) == 0


class TestCategoryFiltering:
    """Test category-based filtering."""

    def test_filter_products_by_category(self, client, sample_search_data):
        """Test filtering products by category."""
        response = client.get("/api/search/products?category=Electronics")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) > 0
        assert all(product["category"] == "Electronics" for product in results)

    def test_filter_products_multiple_categories(self, client, sample_search_data):
        """Test filtering by multiple categories."""
        response = client.get("/api/search/products?category=Electronics,Audio")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]
        assert len(results) > 0
        assert all(
            product["category"] in ["Electronics", "Audio"] for product in results
        )

    def test_get_available_categories(self, client, sample_search_data):
        """Test getting list of available categories."""
        response = client.get("/api/search/categories")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        categories = data["categories"]

        expected_categories = ["Electronics", "Computers", "Audio", "Gaming"]
        for category in expected_categories:
            assert any(cat["name"] == category for cat in categories)

        # Each category should have a count
        for category in categories:
            assert "name" in category
            assert "count" in category
            assert category["count"] > 0

    def test_category_facet_counts(self, client, sample_search_data):
        """Test category facet counts with search query."""
        response = client.get("/api/search/products?q=pro&facets=category")

        assert response.status_code == 200
        data = response.json()
        assert "facets" in data
        assert "category" in data["facets"]

        category_facets = data["facets"]["category"]
        assert isinstance(category_facets, list)

        for facet in category_facets:
            assert "value" in facet
            assert "count" in facet
            assert facet["count"] >= 0


class TestPriceFiltering:
    """Test price-based filtering and search."""

    def test_filter_products_by_price_range(self, client, sample_search_data):
        """Test filtering products by price range."""
        response = client.get("/api/search/products?min_price=200&max_price=500")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Each result should have current price info
        for product in results:
            assert "current_price" in product
            if product["current_price"]:
                price = product["current_price"]["price"]
                assert 200 <= price <= 500

    def test_filter_products_by_minimum_price(self, client, sample_search_data):
        """Test filtering by minimum price only."""
        response = client.get("/api/search/products?min_price=1000")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        for product in results:
            if product.get("current_price"):
                assert product["current_price"]["price"] >= 1000

    def test_filter_products_by_maximum_price(self, client, sample_search_data):
        """Test filtering by maximum price only."""
        response = client.get("/api/search/products?max_price=800")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        for product in results:
            if product.get("current_price"):
                assert product["current_price"]["price"] <= 800

    def test_price_range_facets(self, client, sample_search_data):
        """Test price range facets."""
        response = client.get("/api/search/products?facets=price_range")

        assert response.status_code == 200
        data = response.json()
        assert "facets" in data
        assert "price_range" in data["facets"]

        price_facets = data["facets"]["price_range"]
        assert isinstance(price_facets, list)

        for facet in price_facets:
            assert "range" in facet
            assert "count" in facet
            assert "min" in facet["range"]
            assert "max" in facet["range"]

    def test_price_history_search(self, client, sample_search_data):
        """Test searching based on price history."""
        response = client.get("/api/search/products?has_price_drop=true&days=7")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Results should include price change information
        for product in results:
            assert "price_change" in product
            if product["price_change"]:
                assert "percentage" in product["price_change"]
                assert "direction" in product["price_change"]


class TestAdvancedFiltering:
    """Test advanced filtering combinations."""

    def test_combined_search_and_filters(self, client, sample_search_data):
        """Test combining search query with filters."""
        response = client.get(
            "/api/search/products?q=pro&category=Electronics&min_price=500&max_price=2000"
        )

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        for product in results:
            # Should match search term
            assert (
                "pro" in product["name"].lower()
                or "pro" in product["description"].lower()
            )
            # Should match category
            assert product["category"] == "Electronics"
            # Should match price range
            if product.get("current_price"):
                price = product["current_price"]["price"]
                assert 500 <= price <= 2000

    def test_filter_by_availability(self, client, sample_search_data):
        """Test filtering by product availability."""
        response = client.get("/api/search/products?available_only=true")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        for product in results:
            assert "is_available" in product
            assert product["is_available"] is True

    def test_filter_by_status(self, client, sample_search_data):
        """Test filtering by product status."""
        response = client.get("/api/search/products?status=ACTIVE")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        for product in results:
            assert product["status"] == "ACTIVE"

    def test_filter_by_provider(self, client, sample_search_data):
        """Test filtering by provider."""
        response = client.get("/api/search/products?provider=Amazon")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Results should only include products available from Amazon
        for product in results:
            assert "providers" in product
            provider_names = [p["name"] for p in product["providers"]]
            assert "Amazon" in provider_names

    def test_exclude_discontinued_products(self, client, sample_search_data):
        """Test excluding discontinued products."""
        response = client.get("/api/search/products?exclude_discontinued=true")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        for product in results:
            assert product["status"] != "DISCONTINUED"


class TestSortingAndPagination:
    """Test search result sorting and pagination."""

    def test_sort_by_price_ascending(self, client, sample_search_data):
        """Test sorting results by price (low to high)."""
        response = client.get("/api/search/products?sort=price_asc")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Verify ascending price order (excluding None prices)
        prices = [
            r["current_price"]["price"] for r in results if r.get("current_price")
        ]
        assert prices == sorted(prices)

    def test_sort_by_price_descending(self, client, sample_search_data):
        """Test sorting results by price (high to low)."""
        response = client.get("/api/search/products?sort=price_desc")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Verify descending price order
        prices = [
            r["current_price"]["price"] for r in results if r.get("current_price")
        ]
        assert prices == sorted(prices, reverse=True)

    def test_sort_by_name(self, client, sample_search_data):
        """Test sorting results by name."""
        response = client.get("/api/search/products?sort=name")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        names = [r["name"] for r in results]
        assert names == sorted(names)

    def test_sort_by_newest(self, client, sample_search_data):
        """Test sorting by newest products first."""
        response = client.get("/api/search/products?sort=newest")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Verify descending creation date order
        dates = [r["created_at"] for r in results]
        assert dates == sorted(dates, reverse=True)

    def test_sort_by_relevance(self, client, sample_search_data):
        """Test sorting by search relevance."""
        response = client.get("/api/search/products?q=iPhone&sort=relevance")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Most relevant results should be first
        # iPhone in name should rank higher than iPhone in description
        iphone_in_name_indices = [
            i for i, r in enumerate(results) if "iPhone" in r["name"]
        ]
        iphone_in_desc_indices = [
            i
            for i, r in enumerate(results)
            if "iPhone" not in r["name"] and "iPhone" in r.get("description", "")
        ]

        if iphone_in_name_indices and iphone_in_desc_indices:
            assert min(iphone_in_name_indices) < min(iphone_in_desc_indices)

    def test_pagination_page_size(self, client, sample_search_data):
        """Test pagination with different page sizes."""
        response = client.get("/api/search/products?per_page=3")

        assert response.status_code == 200
        data = response.json()
        assert data["per_page"] == 3
        assert len(data["results"]) <= 3
        assert "page" in data
        assert "total_pages" in data

    def test_pagination_specific_page(self, client, sample_search_data):
        """Test getting specific page of results."""
        # Get first page
        response1 = client.get("/api/search/products?page=1&per_page=3")
        assert response1.status_code == 200
        data1 = response1.json()

        # Get second page
        response2 = client.get("/api/search/products?page=2&per_page=3")
        assert response2.status_code == 200
        data2 = response2.json()

        # Results should be different
        ids1 = {r["id"] for r in data1["results"]}
        ids2 = {r["id"] for r in data2["results"]}
        assert ids1.isdisjoint(ids2)  # No overlap

    def test_pagination_out_of_bounds(self, client, sample_search_data):
        """Test pagination with page number out of bounds."""
        response = client.get("/api/search/products?page=999&per_page=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 0
        assert data["page"] == 999


class TestFullTextSearch:
    """Test advanced full-text search capabilities."""

    def test_search_multiple_terms(self, client, sample_search_data):
        """Test searching with multiple terms."""
        response = client.get("/api/search/products?q=pro max")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Should prioritize results containing both terms
        assert len(results) > 0

        # Check if "iPhone 15 Pro Max" is in results (should match both terms)
        product_names = [r["name"] for r in results]
        assert any("Pro Max" in name for name in product_names)

    def test_search_with_quotes(self, client, sample_search_data):
        """Test exact phrase search with quotes."""
        response = client.get('/api/search/products?q="Pro Max"')

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Should only match exact phrase
        for product in results:
            text_to_search = f"{product['name']} {product.get('description', '')}"
            assert "Pro Max" in text_to_search

    def test_search_with_wildcard(self, client, sample_search_data):
        """Test wildcard search."""
        response = client.get("/api/search/products?q=iP*")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        # Should match iPhone, iPad, etc.
        assert len(results) > 0
        product_names = [r["name"] for r in results]
        assert any(name.startswith("iP") for name in product_names)

    def test_search_relevance_scoring(self, client, sample_search_data):
        """Test that search results include relevance scores."""
        response = client.get("/api/search/products?q=iPhone&include_score=true")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        for product in results:
            assert "relevance_score" in product
            assert isinstance(product["relevance_score"], (int, float))
            assert product["relevance_score"] >= 0

    def test_search_boosting(self, client, sample_search_data):
        """Test search field boosting (name more important than description)."""
        response = client.get("/api/search/products?q=gaming")

        assert response.status_code == 200
        data = response.json()
        results = data["results"]

        if len(results) >= 2:
            # Products with "gaming" in name should rank higher
            name_matches = [r for r in results if "gaming" in r["name"].lower()]
            desc_matches = [
                r
                for r in results
                if "gaming" not in r["name"].lower()
                and "gaming" in r.get("description", "").lower()
            ]

            if name_matches and desc_matches:
                name_positions = [results.index(r) for r in name_matches]
                desc_positions = [results.index(r) for r in desc_matches]
                assert min(name_positions) < min(desc_positions)


class TestSearchAnalytics:
    """Test search analytics and performance."""

    def test_search_suggestions(self, client, sample_search_data):
        """Test search autocomplete suggestions."""
        response = client.get("/api/search/suggestions?q=iph")

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data

        suggestions = data["suggestions"]
        assert isinstance(suggestions, list)

        # Should suggest completions starting with "iph"
        assert any("iPhone" in suggestion for suggestion in suggestions)

    def test_search_spelling_correction(self, client, sample_search_data):
        """Test search spelling correction."""
        response = client.get("/api/search/products?q=ipone")  # Misspelled "iPhone"

        assert response.status_code == 200
        data = response.json()

        # Should suggest spelling correction
        assert "spelling_suggestion" in data
        assert data["spelling_suggestion"] == "iPhone"

    def test_popular_searches(self, client, sample_search_data):
        """Test getting popular search terms."""
        # Perform several searches to generate data
        search_terms = ["iPhone", "Samsung", "laptop", "headphones"]
        for term in search_terms:
            client.get(f"/api/search/products?q={term}")

        response = client.get("/api/search/popular")

        assert response.status_code == 200
        data = response.json()
        assert "popular_searches" in data

        popular = data["popular_searches"]
        assert isinstance(popular, list)

        for search_term in popular:
            assert "term" in search_term
            assert "count" in search_term

    def test_search_performance_metrics(self, client, sample_search_data):
        """Test search performance tracking."""
        response = client.get("/api/search/products?q=iPhone&track_performance=true")

        assert response.status_code == 200
        data = response.json()

        # Should include performance metrics
        assert "performance" in data
        performance = data["performance"]
        assert "search_time_ms" in performance
        assert "total_results" in performance
        assert isinstance(performance["search_time_ms"], (int, float))

    def test_search_filters_summary(self, client, sample_search_data):
        """Test getting summary of applied filters."""
        response = client.get(
            "/api/search/products?category=Electronics&min_price=500&include_filters=true"
        )

        assert response.status_code == 200
        data = response.json()

        assert "applied_filters" in data
        filters = data["applied_filters"]

        assert "category" in filters
        assert filters["category"] == "Electronics"
        assert "price_range" in filters
        assert filters["price_range"]["min"] == 500


class TestSearchAPI:
    """Test search API error handling and edge cases."""

    def test_search_invalid_sort_parameter(self, client, sample_search_data):
        """Test search with invalid sort parameter."""
        response = client.get("/api/search/products?sort=invalid_sort")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "invalid sort" in data["detail"].lower()

    def test_search_invalid_pagination(self, client, sample_search_data):
        """Test search with invalid pagination parameters."""
        response = client.get("/api/search/products?page=0&per_page=-1")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_search_invalid_price_range(self, client, sample_search_data):
        """Test search with invalid price range."""
        response = client.get("/api/search/products?min_price=1000&max_price=500")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert (
            "min_price" in data["detail"].lower()
            and "max_price" in data["detail"].lower()
        )

    def test_search_api_rate_limiting(self, client, sample_search_data):
        """Test search API rate limiting."""
        # Make many rapid requests
        responses = []
        for i in range(50):
            response = client.get(f"/api/search/products?q=test{i}")
            responses.append(response)

        # Should eventually get rate limited (429) or all succeed
        status_codes = [r.status_code for r in responses]
        assert all(code in [200, 429] for code in status_codes)

    def test_search_with_special_characters(self, client, sample_search_data):
        """Test search with special characters."""
        special_queries = ["C++", "C#", "3D-printer", "Wi-Fi", "Bluetooth®"]

        for query in special_queries:
            response = client.get(f"/api/search/products?q={query}")
            assert response.status_code == 200
            # Should handle special characters gracefully

    def test_search_very_long_query(self, client, sample_search_data):
        """Test search with very long query string."""
        long_query = "a" * 1000  # 1000 character query
        response = client.get(f"/api/search/products?q={long_query}")

        # Should either handle gracefully or return appropriate error
        assert response.status_code in [
            200,
            400,
            413,
        ]  # OK, Bad Request, or Payload Too Large
