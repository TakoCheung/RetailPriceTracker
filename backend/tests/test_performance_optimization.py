"""
TDD tests for Performance Optimization & Caching System.
Following TDD: Write comprehensive tests first (RED), implement functionality (GREEN), then optimize (REFACTOR).

This iteration focuses on performance improvements and caching strategies:
- Redis-based caching for frequently accessed data
- Database query optimization and connection pooling
- API response caching and rate limiting
- Background task optimization and monitoring
- Search result caching and faceted search optimization
- Price data aggregation and time-series optimization
"""

import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from app.database import get_session
from app.main import app
from app.models import PriceRecord, Product, Provider, User
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine

# Use the same test engine setup as existing tests
TEST_DATABASE_URL = "sqlite:///test_performance.db"
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
def mock_redis():
    """Mock Redis client for caching tests."""
    mock_redis = Mock()
    mock_redis.get = Mock(return_value=None)
    mock_redis.set = Mock(return_value=True)
    mock_redis.delete = Mock(return_value=1)
    mock_redis.exists = Mock(return_value=False)
    mock_redis.expire = Mock(return_value=True)
    mock_redis.flushdb = Mock(return_value=True)
    mock_redis.pipeline = Mock()
    return mock_redis


@pytest.fixture
def performance_test_data(test_db):
    """Create test data optimized for performance testing."""
    # Create users
    users = []
    for i in range(10):
        user = User(
            email=f"user{i}@example.com",
            name=f"User {i}",
            github_id=f"github{i}",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        test_db.add(user)
        users.append(user)

    # Create providers
    providers = [
        Provider(
            name="Amazon",
            base_url="https://api.amazon.com",
            rate_limit=1000,
            is_active=True,
            health_status="healthy",
        ),
        Provider(
            name="Best Buy",
            base_url="https://api.bestbuy.com",
            rate_limit=500,
            is_active=True,
            health_status="healthy",
        ),
        Provider(
            name="Walmart",
            base_url="https://api.walmart.com",
            rate_limit=750,
            is_active=True,
            health_status="healthy",
        ),
    ]

    for provider in providers:
        test_db.add(provider)

    # Create products
    products = []
    categories = ["Electronics", "Clothing", "Books", "Home", "Sports"]
    for i in range(50):  # More products for performance testing
        product = Product(
            name=f"Product {i}",
            description=f"Test product {i} description",
            category=categories[i % len(categories)],
            brand=f"Brand {i % 10}",
            sku=f"SKU{i:04d}",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        test_db.add(product)
        products.append(product)

    test_db.commit()

    # Refresh entities to get IDs
    for entity_list in [users, products, providers]:
        for entity in entity_list:
            test_db.refresh(entity)

    # Create price records with time-series data (last 90 days)
    price_records = []
    base_date = datetime.utcnow()

    for days_ago in range(90, 0, -1):
        record_date = base_date - timedelta(days=days_ago)

        # Create price records for multiple products and providers
        for product in products[:10]:  # First 10 products
            for provider in providers:
                # Generate realistic price fluctuations
                base_price = 100 + (product.id * 10)
                price_variation = (days_ago % 30) * 2  # Price variations
                final_price = base_price + price_variation

                price_record = PriceRecord(
                    product_id=product.id,
                    provider_id=provider.id,
                    price=final_price,
                    currency="USD",
                    is_available=True,
                    recorded_at=record_date,
                )
                price_records.append(price_record)

    # Add price records in batches for better performance
    batch_size = 100
    for i in range(0, len(price_records), batch_size):
        batch = price_records[i : i + batch_size]
        for record in batch:
            test_db.add(record)
        test_db.commit()

    return {
        "users": users,
        "products": products,
        "providers": providers,
        "price_records": price_records,
    }


class TestRedisCaching:
    """Test Redis-based caching functionality."""

    @patch("app.services.cache.redis_client")
    def test_cache_product_data(self, mock_redis_client, client, performance_test_data):
        """Test caching of frequently accessed product data."""
        mock_redis_client.get.return_value = None  # Cache miss
        mock_redis_client.set.return_value = True

        product_id = performance_test_data["products"][0].id

        # First request - should cache the result
        response = client.get(f"/api/products/{product_id}?use_cache=true")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product_id

        # Verify cache was called
        mock_redis_client.get.assert_called_once()
        mock_redis_client.set.assert_called_once()

    @patch("app.services.cache.redis_client")
    def test_cache_price_trends(self, mock_redis_client, client, performance_test_data):
        """Test caching of price trend calculations."""
        mock_redis_client.get.return_value = None  # Cache miss
        mock_redis_client.set.return_value = True

        product_id = performance_test_data["products"][0].id

        # Request price trends - computationally expensive operation
        response = client.get(
            f"/api/analytics/price-trends/{product_id}?use_cache=true&days=30"
        )

        assert response.status_code == 200
        data = response.json()
        assert "trends" in data
        assert data["product_id"] == product_id

        # Verify caching was attempted
        mock_redis_client.get.assert_called()
        mock_redis_client.set.assert_called()

    @patch("app.services.cache.redis_client")
    def test_cache_hit_performance(
        self, mock_redis_client, client, performance_test_data
    ):
        """Test performance improvement with cache hits."""
        # Set up cache hit
        cached_data = {
            "id": 1,
            "name": "Cached Product",
            "price": 99.99,
            "cached_at": datetime.utcnow().isoformat(),
        }
        mock_redis_client.get.return_value = str(cached_data).encode()

        product_id = performance_test_data["products"][0].id

        start_time = time.time()
        response = client.get(f"/api/products/{product_id}?use_cache=true")
        end_time = time.time()

        assert response.status_code == 200

        # Cache hit should be very fast
        response_time = (end_time - start_time) * 1000  # Convert to ms
        assert response_time < 100  # Should be under 100ms for cache hit

        # Should only read from cache, not write
        mock_redis_client.get.assert_called_once()
        mock_redis_client.set.assert_not_called()

    def test_cache_invalidation(self, client, mock_redis, performance_test_data):
        """Test cache invalidation when data is updated."""
        product_id = performance_test_data["products"][0].id

        with patch("app.services.cache.redis_client", mock_redis):
            # Update product data - should invalidate cache
            update_data = {"name": "Updated Product Name"}
            response = client.patch(f"/api/products/{product_id}", json=update_data)

            assert response.status_code == 200

            # Cache should be invalidated (deleted)
            mock_redis.delete.assert_called()

    @patch("app.services.cache.redis_client")
    def test_cache_search_results(
        self, mock_redis_client, client, performance_test_data
    ):
        """Test caching of search results for popular queries."""
        mock_redis_client.get.return_value = None  # Cache miss
        mock_redis_client.set.return_value = True

        # Perform search with caching enabled
        response = client.get(
            "/api/search/products?q=Product&use_cache=true&per_page=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0

        # Search results should be cached
        mock_redis_client.get.assert_called()
        mock_redis_client.set.assert_called()

    def test_cache_expiration_policy(self, client, mock_redis, performance_test_data):
        """Test different cache expiration policies for different data types."""
        product_id = performance_test_data["products"][0].id

        with patch("app.services.cache.redis_client", mock_redis):
            # Product data should have longer TTL
            client.get(f"/api/products/{product_id}?use_cache=true")

            # Check that expire was called with appropriate TTL
            mock_redis.expire.assert_called()

            # Price data should have shorter TTL
            mock_redis.reset_mock()
            client.get(f"/api/analytics/price-trends/{product_id}?use_cache=true")

            mock_redis.expire.assert_called()


class TestDatabaseOptimization:
    """Test database query optimization and performance."""

    def test_connection_pooling(self, client):
        """Test database connection pooling efficiency."""
        # Make multiple concurrent requests
        import concurrent.futures

        def make_request():
            return client.get("/api/products?per_page=5")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            responses = [future.result() for future in futures]

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200

    def test_query_optimization_with_indexes(self, client, performance_test_data):
        """Test that queries use database indexes effectively."""
        # Test product search by category (should use category index)
        response = client.get("/api/search/products?category=Electronics")

        assert response.status_code == 200
        data = response.json()

        # Should include query performance metrics
        assert "search_time_ms" in data
        assert data["search_time_ms"] < 1000  # Should be under 1 second

    def test_bulk_operations_performance(self, client, performance_test_data):
        """Test performance of bulk database operations."""
        # Create multiple price updates
        bulk_updates = []
        for i in range(100):
            bulk_updates.append(
                {
                    "product_id": performance_test_data["products"][i % 10].id,
                    "provider_id": performance_test_data["providers"][i % 3].id,
                    "price": 100.0 + i,
                    "currency": "USD",
                    "is_available": True,
                }
            )

        start_time = time.time()
        response = client.post(
            "/api/monitoring/batch-update", json={"price_updates": bulk_updates}
        )
        end_time = time.time()

        assert response.status_code == 201
        data = response.json()
        assert data["updates_processed"] == 100

        # Bulk operation should be efficient
        processing_time = (end_time - start_time) * 1000
        assert processing_time < 5000  # Should process 100 records in under 5 seconds

    def test_pagination_performance(self, client, performance_test_data):
        """Test pagination performance with large datasets."""
        # Test deep pagination
        response = client.get("/api/search/products?page=5&per_page=10")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 5
        assert len(data["results"]) <= 10

        # Should include performance metrics
        assert "search_time_ms" in data

    def test_aggregation_queries_performance(self, client, performance_test_data):
        """Test performance of complex aggregation queries."""
        # Test analytics aggregation
        response = client.get("/api/analytics/dashboard")

        assert response.status_code == 200
        data = response.json()

        # Should return aggregated data efficiently
        assert "total_products" in data
        assert "total_providers" in data
        assert "recent_price_updates" in data

    def test_time_series_query_optimization(self, client, performance_test_data):
        """Test optimization of time-series queries on price data."""
        product_id = performance_test_data["products"][0].id

        start_time = time.time()
        response = client.get(f"/api/analytics/price-trends/{product_id}?days=90")
        end_time = time.time()

        assert response.status_code == 200
        data = response.json()
        assert "trends" in data

        # Time-series query should be optimized
        query_time = (end_time - start_time) * 1000
        assert query_time < 2000  # Should complete in under 2 seconds


class TestAPIResponseCaching:
    """Test API response caching and optimization."""

    @patch("app.services.cache.redis_client")
    def test_response_caching_headers(
        self, mock_redis_client, client, performance_test_data
    ):
        """Test proper HTTP caching headers for API responses."""
        mock_redis_client.get.return_value = None

        response = client.get("/api/products?per_page=5")

        assert response.status_code == 200

        # Should include appropriate caching headers
        headers = response.headers
        assert "Cache-Control" in headers
        assert "ETag" in headers or "Last-Modified" in headers

    def test_conditional_requests(self, client, performance_test_data):
        """Test support for conditional requests (304 Not Modified)."""
        # First request
        response1 = client.get("/api/products?per_page=5")
        assert response1.status_code == 200

        # Get ETag from response
        etag = response1.headers.get("ETag")
        if etag:
            # Second request with If-None-Match header
            response2 = client.get(
                "/api/products?per_page=5", headers={"If-None-Match": etag}
            )

            # Should return 304 Not Modified if data hasn't changed
            # (Implementation may vary based on cache strategy)
            assert response2.status_code in [200, 304]

    @patch("app.services.cache.redis_client")
    def test_cache_warming(self, mock_redis_client, client, performance_test_data):
        """Test cache warming for frequently accessed endpoints."""
        mock_redis_client.get.return_value = None
        mock_redis_client.set.return_value = True

        # Simulate cache warming process
        response = client.post("/api/cache/warm")

        assert response.status_code == 200
        data = response.json()
        assert "cache_entries_created" in data
        assert data["cache_entries_created"] > 0

        # Cache should have been populated
        assert mock_redis_client.set.call_count > 0

    def test_rate_limiting_performance(self, client):
        """Test rate limiting doesn't significantly impact performance."""
        # Make requests up to rate limit
        responses = []
        start_time = time.time()

        for i in range(10):  # Assume rate limit is higher than 10
            response = client.get("/api/products?per_page=1")
            responses.append(response)

        end_time = time.time()

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200

        # Rate limiting overhead should be minimal
        total_time = (end_time - start_time) * 1000
        avg_time_per_request = total_time / len(responses)
        assert avg_time_per_request < 500  # Under 500ms per request


class TestBackgroundTaskOptimization:
    """Test optimization of background tasks and job queues."""

    def test_task_queue_performance(self, client):
        """Test background task queue performance."""
        # Schedule multiple background tasks
        task_ids = []
        for i in range(5):
            response = client.post(
                "/api/monitoring/schedule-crawl",
                json={"provider_id": 1, "priority": "normal"},
            )
            assert response.status_code == 202
            data = response.json()
            task_ids.append(data["task_id"])

        # Check task status
        for task_id in task_ids:
            response = client.get(f"/api/monitoring/tasks/{task_id}")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data

    def test_task_priority_optimization(self, client):
        """Test task priority and scheduling optimization."""
        # Schedule high priority task
        response = client.post(
            "/api/monitoring/schedule-crawl",
            json={"provider_id": 1, "priority": "high"},
        )
        assert response.status_code == 202
        high_priority_task = response.json()

        # Schedule normal priority task
        response = client.post(
            "/api/monitoring/schedule-crawl",
            json={"provider_id": 2, "priority": "normal"},
        )
        assert response.status_code == 202
        normal_priority_task = response.json()

        # High priority task should be processed first
        # (This would need actual queue implementation to test properly)
        assert high_priority_task["task_id"] != normal_priority_task["task_id"]

    def test_task_batch_processing(self, client, performance_test_data):
        """Test batch processing of similar tasks."""
        # Schedule multiple price update tasks
        product_ids = [p.id for p in performance_test_data["products"][:10]]

        response = client.post(
            "/api/monitoring/batch-price-check", json={"product_ids": product_ids}
        )

        assert response.status_code == 202
        data = response.json()
        assert "batch_task_id" in data
        assert data["products_queued"] == len(product_ids)

    def test_task_failure_handling(self, client):
        """Test handling of failed background tasks."""
        # Schedule a task that will fail
        response = client.post(
            "/api/monitoring/schedule-crawl",
            json={"provider_id": 999, "priority": "normal"},  # Non-existent provider
        )

        # Should still accept the task
        assert response.status_code == 202
        task_data = response.json()

        # Check task status later - should show failure
        response = client.get(f"/api/monitoring/tasks/{task_data['task_id']}")
        assert response.status_code == 200
        data = response.json()
        # Task should eventually fail gracefully
        assert "status" in data


class TestSearchOptimization:
    """Test search performance and optimization features."""

    def test_search_index_performance(self, client, performance_test_data):
        """Test search indexing and full-text search performance."""
        # Perform complex search query
        start_time = time.time()
        response = client.get(
            "/api/search/products?q=Product Electronics&category=Electronics&sort=relevance"
        )
        end_time = time.time()

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) > 0

        # Search should be fast
        search_time = (end_time - start_time) * 1000
        assert search_time < 1000  # Under 1 second

    def test_faceted_search_optimization(self, client, performance_test_data):
        """Test faceted search performance with aggregations."""
        response = client.get(
            "/api/search/products?q=Product&facets=category,brand,price_range"
        )

        assert response.status_code == 200
        data = response.json()
        assert "facets" in data

        facets = data["facets"]
        assert "category" in facets
        assert "brand" in facets
        assert "price_range" in facets

    def test_search_autocomplete_performance(self, client, performance_test_data):
        """Test search autocomplete/suggestions performance."""
        response = client.get("/api/search/suggestions?q=Prod")

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) > 0

        # Autocomplete should be very fast
        assert "response_time_ms" in data
        assert data["response_time_ms"] < 100

    def test_search_result_caching(self, client, performance_test_data):
        """Test caching of search results for performance."""
        # First search
        start_time = time.time()
        response1 = client.get("/api/search/products?q=Electronics&use_cache=true")
        first_time = time.time() - start_time

        assert response1.status_code == 200

        # Second identical search (should be cached)
        start_time = time.time()
        response2 = client.get("/api/search/products?q=Electronics&use_cache=true")
        second_time = time.time() - start_time

        assert response2.status_code == 200
        assert response1.json() == response2.json()

        # Second request should be significantly faster (cached)
        assert second_time < first_time * 0.5  # At least 50% faster


class TestMemoryOptimization:
    """Test memory usage optimization and resource management."""

    def test_memory_efficient_pagination(self, client, performance_test_data):
        """Test memory-efficient pagination for large datasets."""
        # Request large result set with pagination
        response = client.get("/api/search/products?per_page=50")

        assert response.status_code == 200
        data = response.json()

        # Should not load all results into memory at once
        assert len(data["results"]) <= 50
        assert "total_pages" in data

    def test_streaming_large_responses(self, client, performance_test_data):
        """Test streaming of large API responses."""
        # Request large dataset export
        response = client.get("/api/analytics/export/price-data?format=json")

        assert response.status_code == 200

        # Should use streaming response for large data
        # (Check response headers for chunked transfer)
        headers = response.headers
        content_type = headers.get("content-type", "")
        assert "json" in content_type.lower()

    def test_lazy_loading_relationships(self, client, performance_test_data):
        """Test lazy loading of database relationships."""
        product_id = performance_test_data["products"][0].id

        # Request product with relationships
        response = client.get(f"/api/products/{product_id}?include=price_records")

        assert response.status_code == 200
        data = response.json()
        assert "price_records" in data

        # Should not eagerly load all relationships by default
        response2 = client.get(f"/api/products/{product_id}")
        data2 = response2.json()

        # Default response should be smaller/faster
        assert len(str(data2)) <= len(str(data))


class TestMonitoringAndMetrics:
    """Test performance monitoring and metrics collection."""

    def test_performance_metrics_collection(self, client):
        """Test collection of performance metrics."""
        response = client.get("/api/monitoring/performance/metrics")

        assert response.status_code == 200
        data = response.json()

        # Should include key performance metrics
        assert "avg_response_time_ms" in data
        assert "requests_per_minute" in data
        assert "error_rate" in data
        assert "cache_hit_rate" in data

    def test_slow_query_detection(self, client, performance_test_data):
        """Test detection and logging of slow queries."""
        # Make a potentially slow request
        response = client.get(
            "/api/analytics/complex-report?days=90&include_aggregations=true"
        )

        # Should complete even if slow
        assert response.status_code in [200, 408]  # 408 for timeout

        # Slow queries should be logged/monitored
        metrics_response = client.get("/api/monitoring/performance/slow-queries")
        assert metrics_response.status_code == 200

    def test_resource_usage_monitoring(self, client):
        """Test monitoring of system resource usage."""
        response = client.get("/api/monitoring/system/resources")

        assert response.status_code == 200
        data = response.json()

        # Should include system metrics
        assert "memory_usage_mb" in data
        assert "cpu_usage_percent" in data
        assert "active_connections" in data

    def test_cache_performance_monitoring(self, client):
        """Test monitoring of cache performance."""
        response = client.get("/api/monitoring/cache/stats")

        assert response.status_code == 200
        data = response.json()

        # Should include cache statistics
        assert "cache_hit_rate" in data
        assert "cache_miss_rate" in data
        assert "total_keys" in data
        assert "memory_usage_mb" in data


class TestLoadTesting:
    """Test system performance under load."""

    def test_concurrent_request_handling(self, client, performance_test_data):
        """Test handling of concurrent requests."""
        import threading

        results = []
        errors = []

        def make_requests():
            try:
                # Each thread makes multiple requests
                for i in range(5):
                    response = client.get(f"/api/products?page={i + 1}&per_page=5")
                    results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))

        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_requests)
            threads.append(thread)

        # Start all threads
        start_time = time.time()
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        end_time = time.time()

        # Should handle concurrent requests successfully
        assert len(errors) == 0
        assert all(status == 200 for status in results)

        # Should complete in reasonable time
        total_time = end_time - start_time
        assert total_time < 30  # Should complete within 30 seconds

    def test_memory_usage_under_load(self, client, performance_test_data):
        """Test memory usage remains stable under load."""
        # Get initial memory usage
        initial_response = client.get("/api/monitoring/system/resources")
        initial_data = initial_response.json()
        initial_memory = initial_data.get("memory_usage_mb", 0)

        # Generate load
        for _ in range(50):
            client.get("/api/search/products?q=test&per_page=20")

        # Check memory usage after load
        final_response = client.get("/api/monitoring/system/resources")
        final_data = final_response.json()
        final_memory = final_data.get("memory_usage_mb", 0)

        # Memory usage should not increase dramatically
        memory_increase = final_memory - initial_memory
        assert memory_increase < 100  # Less than 100MB increase

    def test_response_time_under_load(self, client, performance_test_data):
        """Test response times remain acceptable under load."""
        response_times = []

        # Make multiple requests and measure response times
        for i in range(20):
            start_time = time.time()
            response = client.get("/api/products?per_page=10")
            end_time = time.time()

            assert response.status_code == 200
            response_time = (end_time - start_time) * 1000  # Convert to ms
            response_times.append(response_time)

        # Calculate performance metrics
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)

        # Response times should be reasonable
        assert avg_response_time < 1000  # Average under 1 second
        assert max_response_time < 2000  # Max under 2 seconds

        # Most requests should be fast
        fast_responses = [t for t in response_times if t < 500]
        assert len(fast_responses) > len(response_times) * 0.8  # 80% under 500ms
