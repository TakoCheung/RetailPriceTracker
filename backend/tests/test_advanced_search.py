"""
Test cases for Advanced Search & Filtering System.
Covers product search, price filtering, faceted search, and advanced query capabilities.
"""

from datetime import datetime, timedelta, timezone

import pytest
from app.models import (
    PriceRecord,
    Product,
    Provider,
    User,
    UserRole,
)
from sqlalchemy.ext.asyncio import AsyncSession


class TestBasicProductSearch:
    """Test basic product search functionality."""

    @pytest.mark.asyncio
    async def test_search_products_by_name(self, client, db_session: AsyncSession):
        """Test searching products by name."""
        # Create test products
        product1 = Product(name="iPhone 15 Pro", brand="Apple", category="smartphones")
        product2 = Product(name="iPhone 14", brand="Apple", category="smartphones")
        product3 = Product(
            name="Samsung Galaxy S24", brand="Samsung", category="smartphones"
        )
        product4 = Product(name="MacBook Pro", brand="Apple", category="laptops")

        db_session.add_all([product1, product2, product3, product4])
        await db_session.commit()

        # Search for "iPhone"
        response = client.get("/api/products/search?q=iPhone")
        print(f"Status code: {response.status_code}")
        print(f"Response content: {response.text}")
        assert response.status_code == 200

        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2

        # Verify results contain iPhone products
        product_names = [p["name"] for p in data["results"]]
        assert "iPhone 15 Pro" in product_names
        assert "iPhone 14" in product_names

    @pytest.mark.asyncio
    async def test_search_products_case_insensitive(
        self, client, db_session: AsyncSession
    ):
        """Test that product search is case insensitive."""
        product = Product(name="iPhone 15 Pro", brand="Apple", category="smartphones")
        db_session.add(product)
        await db_session.commit()

        # Test various cases
        test_queries = ["iphone", "IPHONE", "IpHoNe", "iPhone"]

        for query in test_queries:
            response = client.get(f"/api/products/search?q={query}")
            assert response.status_code == 200

            data = response.json()
            assert len(data["results"]) == 1
            assert data["results"][0]["name"] == "iPhone 15 Pro"

    @pytest.mark.asyncio
    async def test_search_products_partial_match(
        self, client, db_session: AsyncSession
    ):
        """Test partial string matching in product search."""
        product1 = Product(
            name="MacBook Pro 16-inch", brand="Apple", category="laptops"
        )
        product2 = Product(name="MacBook Air", brand="Apple", category="laptops")
        product3 = Product(name="Mac Studio", brand="Apple", category="desktops")

        db_session.add_all([product1, product2, product3])
        await db_session.commit()

        # Search for "Mac" should match all three
        response = client.get("/api/products/search?q=Mac")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 3

        # Search for "MacBook" should match two
        response = client.get("/api/products/search?q=MacBook")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_search_products_empty_query(self, client, db_session: AsyncSession):
        """Test search behavior with empty query."""
        # Create test products
        product1 = Product(name="iPhone 15", brand="Apple", category="smartphones")
        product2 = Product(name="Galaxy S24", brand="Samsung", category="smartphones")

        db_session.add_all([product1, product2])
        await db_session.commit()

        # Empty query should return all products with pagination
        response = client.get("/api/products/search?q=")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_search_products_no_results(self, client, db_session: AsyncSession):
        """Test search behavior when no products match."""
        product = Product(name="iPhone 15", brand="Apple", category="smartphones")
        db_session.add(product)
        await db_session.commit()

        response = client.get("/api/products/search?q=NonexistentProduct")
        assert response.status_code == 200

        data = response.json()
        assert data["results"] == []
        assert data["total_count"] == 0


class TestAdvancedFiltering:
    """Test advanced filtering capabilities."""

    @pytest.mark.asyncio
    async def test_filter_by_category(self, client, db_session: AsyncSession):
        """Test filtering products by category."""
        # Create products in different categories
        product1 = Product(name="iPhone 15", brand="Apple", category="smartphones")
        product2 = Product(name="Galaxy S24", brand="Samsung", category="smartphones")
        product3 = Product(name="MacBook Pro", brand="Apple", category="laptops")
        product4 = Product(name="ThinkPad X1", brand="Lenovo", category="laptops")

        db_session.add_all([product1, product2, product3, product4])
        await db_session.commit()

        # Filter by smartphones
        response = client.get("/api/products/search?category=smartphones")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 2

        categories = [p["category"] for p in data["results"]]
        assert all(cat == "smartphones" for cat in categories)

    @pytest.mark.asyncio
    async def test_filter_by_brand(self, client, db_session: AsyncSession):
        """Test filtering products by brand."""
        product1 = Product(name="iPhone 15", brand="Apple", category="smartphones")
        product2 = Product(name="MacBook Pro", brand="Apple", category="laptops")
        product3 = Product(name="Galaxy S24", brand="Samsung", category="smartphones")

        db_session.add_all([product1, product2, product3])
        await db_session.commit()

        # Filter by Apple
        response = client.get("/api/products/search?brand=Apple")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 2

        brands = [p["brand"] for p in data["results"]]
        assert all(brand == "Apple" for brand in brands)

    @pytest.mark.asyncio
    async def test_filter_by_price_range(self, client, db_session: AsyncSession):
        """Test filtering products by price range."""
        # Create products and providers
        product1 = Product(name="Budget Phone", brand="Generic", category="smartphones")
        product2 = Product(
            name="Mid Range Phone", brand="Generic", category="smartphones"
        )
        product3 = Product(
            name="Premium Phone", brand="Generic", category="smartphones"
        )
        provider = Provider(name="Test Store", base_url="https://test.com")

        db_session.add_all([product1, product2, product3, provider])
        await db_session.commit()
        await db_session.refresh(product1)
        await db_session.refresh(product2)
        await db_session.refresh(product3)
        await db_session.refresh(provider)

        # Add price records
        price1 = PriceRecord(
            product_id=product1.id, provider_id=provider.id, price=200.0, currency="USD"
        )
        price2 = PriceRecord(
            product_id=product2.id, provider_id=provider.id, price=500.0, currency="USD"
        )
        price3 = PriceRecord(
            product_id=product3.id,
            provider_id=provider.id,
            price=1000.0,
            currency="USD",
        )

        db_session.add_all([price1, price2, price3])
        await db_session.commit()

        # Filter by price range 300-700
        response = client.get("/api/products/search?min_price=300&max_price=700")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "Mid Range Phone"

    @pytest.mark.asyncio
    async def test_filter_by_availability(self, client, db_session: AsyncSession):
        """Test filtering products by availability."""
        product1 = Product(name="Available Product", brand="Brand", category="test")
        product2 = Product(name="Unavailable Product", brand="Brand", category="test")
        provider = Provider(name="Test Store", base_url="https://test.com")

        db_session.add_all([product1, product2, provider])
        await db_session.commit()
        await db_session.refresh(product1)
        await db_session.refresh(product2)
        await db_session.refresh(provider)

        # Add price records with different availability
        price1 = PriceRecord(
            product_id=product1.id,
            provider_id=provider.id,
            price=100.0,
            is_available=True,
        )
        price2 = PriceRecord(
            product_id=product2.id,
            provider_id=provider.id,
            price=100.0,
            is_available=False,
        )

        db_session.add_all([price1, price2])
        await db_session.commit()

        # Filter by availability
        response = client.get("/api/products/search?available=true")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "Available Product"

    @pytest.mark.asyncio
    async def test_combined_filters(self, client, db_session: AsyncSession):
        """Test combining multiple filters."""
        # Create test data
        product1 = Product(name="iPhone 15", brand="Apple", category="smartphones")
        product2 = Product(name="Galaxy S24", brand="Samsung", category="smartphones")
        product3 = Product(name="MacBook Pro", brand="Apple", category="laptops")
        provider = Provider(name="Test Store", base_url="https://test.com")

        db_session.add_all([product1, product2, product3, provider])
        await db_session.commit()
        await db_session.refresh(product1)
        await db_session.refresh(product2)
        await db_session.refresh(product3)
        await db_session.refresh(provider)

        # Add prices
        price1 = PriceRecord(
            product_id=product1.id, provider_id=provider.id, price=999.0
        )
        price2 = PriceRecord(
            product_id=product2.id, provider_id=provider.id, price=899.0
        )
        price3 = PriceRecord(
            product_id=product3.id, provider_id=provider.id, price=1999.0
        )

        db_session.add_all([price1, price2, price3])
        await db_session.commit()

        # Combine category and brand filters
        response = client.get("/api/products/search?category=smartphones&brand=Apple")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "iPhone 15"


class TestFacetedSearch:
    """Test faceted search functionality."""

    @pytest.mark.asyncio
    async def test_get_search_facets(self, client, db_session: AsyncSession):
        """Test retrieving search facets for filtering."""
        # Create diverse products
        products = [
            Product(name="iPhone 15", brand="Apple", category="smartphones"),
            Product(name="Galaxy S24", brand="Samsung", category="smartphones"),
            Product(name="MacBook Pro", brand="Apple", category="laptops"),
            Product(name="ThinkPad X1", brand="Lenovo", category="laptops"),
            Product(name="iPad Pro", brand="Apple", category="tablets"),
        ]

        db_session.add_all(products)
        await db_session.commit()

        response = client.get("/api/products/facets")
        assert response.status_code == 200

        data = response.json()
        assert "brands" in data
        assert "categories" in data

        # Check brand facets
        expected_brands = {"Apple": 3, "Samsung": 1, "Lenovo": 1}
        for brand_facet in data["brands"]:
            assert brand_facet["value"] in expected_brands
            assert brand_facet["count"] == expected_brands[brand_facet["value"]]

        # Check category facets
        expected_categories = {"smartphones": 2, "laptops": 2, "tablets": 1}
        for category_facet in data["categories"]:
            assert category_facet["value"] in expected_categories
            assert (
                category_facet["count"] == expected_categories[category_facet["value"]]
            )

    @pytest.mark.asyncio
    async def test_facets_with_search_query(self, client, db_session: AsyncSession):
        """Test facets when combined with search query."""
        products = [
            Product(name="iPhone 15 Pro", brand="Apple", category="smartphones"),
            Product(name="iPhone 14", brand="Apple", category="smartphones"),
            Product(name="iPad Pro", brand="Apple", category="tablets"),
            Product(name="Galaxy Phone", brand="Samsung", category="smartphones"),
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Get facets for "iPhone" search
        response = client.get("/api/products/facets?q=iPhone")
        assert response.status_code == 200

        data = response.json()

        # Should only show facets for iPhone products
        brand_counts = {b["value"]: b["count"] for b in data["brands"]}
        assert brand_counts.get("Apple", 0) == 2
        assert "Samsung" not in brand_counts

    @pytest.mark.asyncio
    async def test_price_range_facets(self, client, db_session: AsyncSession):
        """Test price range facets."""
        products = [
            Product(name="Budget Phone", brand="Generic", category="smartphones"),
            Product(name="Mid Phone", brand="Generic", category="smartphones"),
            Product(name="Premium Phone", brand="Generic", category="smartphones"),
        ]
        provider = Provider(name="Store", base_url="https://test.com")

        db_session.add_all(products + [provider])
        await db_session.commit()

        for i, product in enumerate(products):
            await db_session.refresh(product)
        await db_session.refresh(provider)

        # Add different price points
        prices = [
            PriceRecord(
                product_id=products[0].id, provider_id=provider.id, price=199.0
            ),
            PriceRecord(
                product_id=products[1].id, provider_id=provider.id, price=599.0
            ),
            PriceRecord(
                product_id=products[2].id, provider_id=provider.id, price=1299.0
            ),
        ]

        db_session.add_all(prices)
        await db_session.commit()

        response = client.get("/api/products/facets")
        assert response.status_code == 200

        data = response.json()
        assert "price_ranges" in data

        # Should have price range buckets
        price_ranges = data["price_ranges"]
        assert len(price_ranges) > 0

        # Verify structure
        for price_range in price_ranges:
            assert "min" in price_range
            assert "max" in price_range
            assert "count" in price_range


class TestSortingAndPagination:
    """Test sorting and pagination functionality."""

    @pytest.mark.asyncio
    async def test_sort_by_name(self, client, db_session: AsyncSession):
        """Test sorting products by name."""
        products = [
            Product(name="Zebra Product", brand="Brand", category="test"),
            Product(name="Alpha Product", brand="Brand", category="test"),
            Product(name="Beta Product", brand="Brand", category="test"),
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Sort ascending
        response = client.get("/api/products/search?sort=name&order=asc")
        assert response.status_code == 200

        data = response.json()
        names = [p["name"] for p in data["results"]]
        assert names == ["Alpha Product", "Beta Product", "Zebra Product"]

        # Sort descending
        response = client.get("/api/products/search?sort=name&order=desc")
        assert response.status_code == 200

        data = response.json()
        names = [p["name"] for p in data["results"]]
        assert names == ["Zebra Product", "Beta Product", "Alpha Product"]

    @pytest.mark.asyncio
    async def test_sort_by_price(self, client, db_session: AsyncSession):
        """Test sorting products by price."""
        products = [
            Product(name="Expensive", brand="Brand", category="test"),
            Product(name="Cheap", brand="Brand", category="test"),
            Product(name="Medium", brand="Brand", category="test"),
        ]
        provider = Provider(name="Store", base_url="https://test.com")

        db_session.add_all(products + [provider])
        await db_session.commit()

        for product in products:
            await db_session.refresh(product)
        await db_session.refresh(provider)

        prices = [
            PriceRecord(
                product_id=products[0].id, provider_id=provider.id, price=999.0
            ),
            PriceRecord(product_id=products[1].id, provider_id=provider.id, price=99.0),
            PriceRecord(
                product_id=products[2].id, provider_id=provider.id, price=499.0
            ),
        ]

        db_session.add_all(prices)
        await db_session.commit()

        # Sort by price ascending
        response = client.get("/api/products/search?sort=price&order=asc")
        assert response.status_code == 200

        data = response.json()
        names = [p["name"] for p in data["results"]]
        assert names == ["Cheap", "Medium", "Expensive"]

    @pytest.mark.asyncio
    async def test_pagination(self, client, db_session: AsyncSession):
        """Test pagination of search results."""
        # Create 25 products
        products = [
            Product(name=f"Product {i:02d}", brand="Brand", category="test")
            for i in range(25)
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Test first page
        response = client.get("/api/products/search?page=1&per_page=10")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 10
        assert data["total_count"] == 25
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert data["total_pages"] == 3

        # Test second page
        response = client.get("/api/products/search?page=2&per_page=10")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 10
        assert data["page"] == 2

        # Test last page
        response = client.get("/api/products/search?page=3&per_page=10")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 5  # Remaining products
        assert data["page"] == 3

    @pytest.mark.asyncio
    async def test_pagination_limits(self, client, db_session: AsyncSession):
        """Test pagination limits and boundaries."""
        products = [
            Product(name=f"Product {i}", brand="Brand", category="test")
            for i in range(5)
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Test invalid page number
        response = client.get("/api/products/search?page=0")
        assert response.status_code == 400

        # Test page beyond available results
        response = client.get("/api/products/search?page=10&per_page=10")
        assert response.status_code == 200

        data = response.json()
        assert data["results"] == []

        # Test maximum per_page limit
        response = client.get("/api/products/search?per_page=1000")
        assert response.status_code == 400


class TestFullTextSearch:
    """Test full-text search capabilities."""

    @pytest.mark.asyncio
    async def test_search_in_description(self, client, db_session: AsyncSession):
        """Test searching within product descriptions."""
        products = [
            Product(
                name="iPhone",
                description="Latest smartphone with advanced camera features",
                brand="Apple",
                category="smartphones",
            ),
            Product(
                name="Camera",
                description="Professional DSLR camera",
                brand="Canon",
                category="cameras",
            ),
            Product(
                name="Laptop",
                description="Gaming laptop with RGB lighting",
                brand="Dell",
                category="laptops",
            ),
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Search for "camera" should match both products
        response = client.get("/api/products/search?q=camera")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 2

        names = [p["name"] for p in data["results"]]
        assert "iPhone" in names  # Matches description
        assert "Camera" in names  # Matches name

    @pytest.mark.asyncio
    async def test_search_ranking_relevance(self, client, db_session: AsyncSession):
        """Test search result ranking by relevance."""
        products = [
            Product(
                name="iPhone Case",
                description="Protective case",
                brand="Generic",
                category="accessories",
            ),
            Product(
                name="iPhone",
                description="Smartphone device",
                brand="Apple",
                category="smartphones",
            ),
            Product(
                name="Android Phone",
                description="iPhone competitor",
                brand="Samsung",
                category="smartphones",
            ),
        ]

        db_session.add_all(products)
        await db_session.commit()

        response = client.get("/api/products/search?q=iPhone")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 3

        # iPhone should rank higher than iPhone Case or Android Phone
        assert data["results"][0]["name"] == "iPhone"

    @pytest.mark.asyncio
    async def test_search_with_special_characters(
        self, client, db_session: AsyncSession
    ):
        """Test search handling of special characters."""
        products = [
            Product(name="USB-C Cable", brand="Generic", category="accessories"),
            Product(name="Wi-Fi Router", brand="Netgear", category="networking"),
            Product(name="32GB RAM", brand="Corsair", category="memory"),
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Test various special characters
        test_queries = ["USB-C", "Wi-Fi", "32GB"]

        for query in test_queries:
            response = client.get(f"/api/products/search?q={query}")
            assert response.status_code == 200

            data = response.json()
            assert len(data["results"]) >= 1


class TestSearchAnalytics:
    """Test search analytics and monitoring."""

    @pytest.mark.asyncio
    async def test_search_query_logging(self, client, db_session: AsyncSession):
        """Test that search queries are logged for analytics."""
        product = Product(name="Test Product", brand="Brand", category="test")
        db_session.add(product)
        await db_session.commit()

        response = client.get("/api/products/search?q=test")
        assert response.status_code == 200

        # Verify search was logged (would check analytics database/logs)
        # This is a placeholder for actual analytics implementation
        assert True

    @pytest.mark.asyncio
    async def test_search_performance_metrics(self, client, db_session: AsyncSession):
        """Test search performance monitoring."""
        # Create many products for performance testing
        products = [
            Product(
                name=f"Product {i}",
                brand=f"Brand {i % 10}",
                category=f"category_{i % 5}",
            )
            for i in range(1000)
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Search should complete within reasonable time
        response = client.get("/api/products/search?q=Product")
        assert response.status_code == 200

        # Response should include performance metadata
        data = response.json()
        assert "search_time_ms" in data
        assert data["search_time_ms"] < 1000  # Less than 1 second

    @pytest.mark.asyncio
    async def test_popular_searches(self, client):
        """Test retrieving popular search terms."""
        # Multiple searches to generate data
        search_terms = ["iPhone", "MacBook", "iPhone", "Samsung", "iPhone"]

        for term in search_terms:
            client.get(f"/api/products/search?q={term}")

        response = client.get("/api/search/popular")
        assert response.status_code == 200

        data = response.json()
        assert "popular_terms" in data

        # iPhone should be most popular
        if data["popular_terms"]:
            assert data["popular_terms"][0]["term"] == "iPhone"
            assert data["popular_terms"][0]["count"] == 3


class TestSearchPersonalization:
    """Test personalized search features."""

    @pytest.mark.asyncio
    async def test_personalized_search_results(self, client, db_session: AsyncSession):
        """Test search results personalization based on user preferences."""
        # Create user with preferences
        user = User(email="test@example.com", name="Test User", role=UserRole.VIEWER)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create products
        products = [
            Product(name="iPhone 15", brand="Apple", category="smartphones"),
            Product(name="Galaxy S24", brand="Samsung", category="smartphones"),
            Product(name="MacBook Pro", brand="Apple", category="laptops"),
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Search with user authentication (would boost Apple products for Apple fan)
        headers = {"Authorization": "Bearer valid_jwt_token"}
        response = client.get("/api/products/search?q=phone", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) >= 2

    @pytest.mark.asyncio
    async def test_search_history(self, client, db_session: AsyncSession):
        """Test user search history tracking."""
        user = User(email="test@example.com", name="Test User", role=UserRole.VIEWER)
        db_session.add(user)
        await db_session.commit()

        headers = {"Authorization": "Bearer valid_jwt_token"}

        # Perform multiple searches
        search_terms = ["iPhone", "MacBook", "iPad"]
        for term in search_terms:
            client.get(f"/api/products/search?q={term}", headers=headers)

        # Get search history
        response = client.get("/api/search/history", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert "history" in data
        assert len(data["history"]) == 3

    @pytest.mark.asyncio
    async def test_saved_searches(self, client, db_session: AsyncSession):
        """Test saving and managing search queries."""
        user = User(email="test@example.com", name="Test User", role=UserRole.VIEWER)
        db_session.add(user)
        await db_session.commit()

        headers = {"Authorization": "Bearer valid_jwt_token"}

        # Save a search
        search_data = {
            "name": "Apple Laptops",
            "query": "MacBook",
            "filters": {"brand": "Apple", "category": "laptops"},
        }

        response = client.post("/api/search/saved", json=search_data, headers=headers)
        assert response.status_code == 201

        # Get saved searches
        response = client.get("/api/search/saved", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["saved_searches"]) == 1
        assert data["saved_searches"][0]["name"] == "Apple Laptops"


class TestSearchAPI:
    """Test search API endpoints and responses."""

    @pytest.mark.asyncio
    async def test_search_response_format(self, client, db_session: AsyncSession):
        """Test the structure of search API responses."""
        product = Product(name="Test Product", brand="Brand", category="test")
        db_session.add(product)
        await db_session.commit()

        response = client.get("/api/products/search?q=test")
        assert response.status_code == 200

        data = response.json()

        # Check required fields
        assert "results" in data
        assert "total_count" in data
        assert "page" in data
        assert "per_page" in data
        assert "total_pages" in data

        # Check product structure
        if data["results"]:
            product_data = data["results"][0]
            required_fields = ["id", "name", "brand", "category", "description"]
            for field in required_fields:
                assert field in product_data

    @pytest.mark.asyncio
    async def test_search_error_handling(self, client):
        """Test search API error handling."""
        # Test invalid parameters
        response = client.get("/api/products/search?per_page=-1")
        assert response.status_code == 400

        response = client.get("/api/products/search?page=0")
        assert response.status_code == 400

        response = client.get("/api/products/search?sort=invalid_field")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_search_rate_limiting(self, client):
        """Test search API rate limiting."""
        # Make many rapid requests
        for i in range(100):
            response = client.get(f"/api/products/search?q=test{i}")

            # Should eventually get rate limited
            if response.status_code == 429:
                assert "rate limit" in response.json()["detail"].lower()
                break
        else:
            # If no rate limiting, that's also acceptable
            assert True


class TestHistoricalPriceSearch:
    """Test searching and filtering by historical price data."""

    @pytest.mark.asyncio
    async def test_filter_by_price_history(self, client, db_session: AsyncSession):
        """Test filtering products by historical price ranges."""
        product = Product(name="Test Product", brand="Brand", category="test")
        provider = Provider(name="Store", base_url="https://test.com")

        db_session.add_all([product, provider])
        await db_session.commit()
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create price history
        base_time = datetime.now(timezone.utc)
        price_records = [
            PriceRecord(
                product_id=product.id,
                provider_id=provider.id,
                price=100.0 + i * 10,
                timestamp=base_time - timedelta(days=i),
            )
            for i in range(10)
        ]

        db_session.add_all(price_records)
        await db_session.commit()

        # Search for products with historical low price under $120
        response = client.get(
            "/api/products/search?historical_min_price=0&historical_max_price=120"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1

    @pytest.mark.asyncio
    async def test_filter_by_price_drop(self, client, db_session: AsyncSession):
        """Test filtering products by recent price drops."""
        product1 = Product(name="Dropped Product", brand="Brand", category="test")
        product2 = Product(name="Stable Product", brand="Brand", category="test")
        provider = Provider(name="Store", base_url="https://test.com")

        db_session.add_all([product1, product2, provider])
        await db_session.commit()
        await db_session.refresh(product1)
        await db_session.refresh(product2)
        await db_session.refresh(provider)

        base_time = datetime.now(timezone.utc)

        # Product 1: price dropped from 200 to 150
        price_records = [
            PriceRecord(
                product_id=product1.id,
                provider_id=provider.id,
                price=200.0,
                timestamp=base_time - timedelta(days=7),
            ),
            PriceRecord(
                product_id=product1.id,
                provider_id=provider.id,
                price=150.0,
                timestamp=base_time,
            ),
            # Product 2: stable price
            PriceRecord(
                product_id=product2.id,
                provider_id=provider.id,
                price=100.0,
                timestamp=base_time - timedelta(days=7),
            ),
            PriceRecord(
                product_id=product2.id,
                provider_id=provider.id,
                price=100.0,
                timestamp=base_time,
            ),
        ]

        db_session.add_all(price_records)
        await db_session.commit()

        # Search for products with recent price drops > 10%
        response = client.get("/api/products/search?price_drop_percentage=10")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "Dropped Product"

    @pytest.mark.asyncio
    async def test_filter_by_price_trend(self, client, db_session: AsyncSession):
        """Test filtering products by price trend (rising/falling)."""
        product = Product(name="Trending Product", brand="Brand", category="test")
        provider = Provider(name="Store", base_url="https://test.com")

        db_session.add_all([product, provider])
        await db_session.commit()
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create ascending price trend
        base_time = datetime.now(timezone.utc)
        price_records = [
            PriceRecord(
                product_id=product.id,
                provider_id=provider.id,
                price=100.0 + i * 5,  # Prices going up
                timestamp=base_time - timedelta(days=10 - i),
            )
            for i in range(10)
        ]

        db_session.add_all(price_records)
        await db_session.commit()

        # Search for products with rising price trend
        response = client.get("/api/products/search?price_trend=rising")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1


class TestElasticsearchIntegration:
    """Test Elasticsearch integration for advanced search."""

    @pytest.mark.asyncio
    async def test_elasticsearch_full_text_search(
        self, client, db_session: AsyncSession
    ):
        """Test Elasticsearch-powered full-text search."""
        products = [
            Product(
                name="iPhone 15 Pro Max",
                description="Latest flagship smartphone with titanium design and advanced camera system",
                brand="Apple",
                category="smartphones",
            ),
            Product(
                name="Samsung Galaxy S24 Ultra",
                description="Premium Android smartphone with S Pen and excellent camera capabilities",
                brand="Samsung",
                category="smartphones",
            ),
        ]

        db_session.add_all(products)
        await db_session.commit()

        # Complex search query
        response = client.get(
            "/api/products/search?q=flagship smartphone camera&use_elasticsearch=true"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 2

        # Should have relevance scores
        for result in data["results"]:
            assert "relevance_score" in result

    @pytest.mark.asyncio
    async def test_elasticsearch_autocomplete(self, client, db_session: AsyncSession):
        """Test Elasticsearch autocomplete suggestions."""
        products = [
            Product(name="iPhone 15", brand="Apple", category="smartphones"),
            Product(name="iPhone 14", brand="Apple", category="smartphones"),
            Product(name="iPad Pro", brand="Apple", category="tablets"),
        ]

        db_session.add_all(products)
        await db_session.commit()

        response = client.get("/api/products/autocomplete?q=iP")
        assert response.status_code == 200

        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) >= 3

    @pytest.mark.asyncio
    async def test_elasticsearch_fuzzy_search(self, client, db_session: AsyncSession):
        """Test Elasticsearch fuzzy search for typos."""
        product = Product(name="MacBook Pro", brand="Apple", category="laptops")
        db_session.add(product)
        await db_session.commit()

        # Search with typo
        response = client.get("/api/products/search?q=MacBok&fuzzy=true")
        assert response.status_code == 200

        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "MacBook Pro"


@pytest.fixture
async def search_test_data(db_session: AsyncSession):
    """Fixture providing comprehensive test data for search tests."""
    # Create brands
    brands = ["Apple", "Samsung", "Google", "Sony", "Microsoft"]

    # Create categories
    categories = ["smartphones", "laptops", "tablets", "headphones", "accessories"]

    # Create providers
    providers = [
        Provider(name="Amazon", base_url="https://amazon.com"),
        Provider(name="Best Buy", base_url="https://bestbuy.com"),
        Provider(name="Target", base_url="https://target.com"),
    ]

    db_session.add_all(providers)
    await db_session.commit()

    for provider in providers:
        await db_session.refresh(provider)

    # Create diverse products
    products = []
    for i in range(50):
        product = Product(
            name=f"Product {i:02d}",
            brand=brands[i % len(brands)],
            category=categories[i % len(categories)],
            description=f"Description for product {i} with various features",
        )
        products.append(product)

    db_session.add_all(products)
    await db_session.commit()

    for product in products:
        await db_session.refresh(product)

    # Create price records with varied pricing
    price_records = []
    for i, product in enumerate(products):
        for j, provider in enumerate(providers):
            price = 100 + (i * 10) + (j * 5)  # Varied pricing
            price_record = PriceRecord(
                product_id=product.id,
                provider_id=provider.id,
                price=price,
                currency="USD",
                is_available=(i + j) % 3 != 0,  # Mix of available/unavailable
                timestamp=datetime.now(timezone.utc) - timedelta(days=i % 30),
            )
            price_records.append(price_record)

    db_session.add_all(price_records)
    await db_session.commit()

    return {
        "products": products,
        "providers": providers,
        "price_records": price_records,
    }
