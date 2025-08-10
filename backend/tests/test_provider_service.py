"""
Provider Service Unit Tests
==========================

Comprehensive test suite for ProviderService with mock scraping and database operations.
Tests provider CRUD, scraping automation, performance monitoring, and error handling.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from app.models import Product, ProductProviderLink, Provider
from app.services.provider_service import ProviderService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db():
    """Mock database session."""
    return Mock(spec=AsyncSession)


@pytest.fixture
def provider_service():
    """Provider service instance for testing."""
    return ProviderService()


@pytest.fixture
def sample_provider():
    """Sample provider for testing."""
    return Provider(
        id=1,
        name="Test Provider",
        base_url="https://testprovider.com",
        scraping_config={
            "price_selector": ".price",
            "title_selector": "h1",
            "availability_selector": ".stock",
        },
        rate_limit=2.0,
        is_active=True,
        health_status="healthy",
    )


@pytest.fixture
def sample_product():
    """Sample product for testing."""
    return Product(
        id=1,
        name="Test Product",
        brand="Test Brand",
        sku="TEST123",
        is_active=True,
        deleted_at=None,
    )


@pytest.fixture
def sample_product_link():
    """Sample product-provider link for testing."""
    return ProductProviderLink(
        id=1,
        product_id=1,
        provider_id=1,
        source_url="https://testprovider.com/product/123",
        is_active=True,
        price=99.99,
        price_last_updated=datetime.utcnow(),
    )


class TestProviderCRUD:
    """Test provider CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_provider_success(self, provider_service, mock_db):
        """Test successful provider creation."""
        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await provider_service.create_provider(
            db_session=mock_db,
            name="Amazon",
            base_url="https://amazon.com",
            rate_limit=100,
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.refresh.called

    @pytest.mark.asyncio
    async def test_create_provider_duplicate_name(self, provider_service, mock_db):
        """Test provider creation with duplicate name."""
        # Mock existing provider query
        with patch.object(provider_service, "_check_provider_exists") as mock_check:
            mock_check.return_value = True

            with pytest.raises(ValueError, match="already exists"):
                await provider_service.create_provider(
                    db_session=mock_db,
                    name="Existing Provider",
                    base_url="https://existing.com",
                )

    @pytest.mark.asyncio
    async def test_get_provider_by_id(self, provider_service, mock_db, sample_provider):
        """Test getting provider by ID."""
        # Mock query result
        mock_result = Mock()
        mock_result.scalars.return_value.first.return_value = sample_provider
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await provider_service.get_provider_by_id(mock_db, 1)

        assert result == sample_provider
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_get_active_providers(
        self, provider_service, mock_db, sample_provider
    ):
        """Test getting active providers."""
        # Mock query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [sample_provider]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await provider_service.get_active_providers(mock_db)

        assert len(result) == 1
        assert result[0] == sample_provider
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_update_provider_health(
        self, provider_service, mock_db, sample_provider
    ):
        """Test updating provider health status."""
        # Mock get provider
        with patch.object(provider_service, "get_provider_by_id") as mock_get:
            mock_get.return_value = sample_provider
            mock_db.commit = AsyncMock()

            result = await provider_service.update_provider_health(
                mock_db, 1, "unhealthy"
            )

            assert result is True
            assert sample_provider.health_status == "unhealthy"
            assert mock_db.commit.called


class TestProductLinking:
    """Test product-provider linking operations."""

    @pytest.mark.asyncio
    async def test_link_product_to_provider_success(self, provider_service, mock_db):
        """Test successful product-provider linking."""
        mock_db.add = Mock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        await provider_service.link_product_to_provider(
            db_session=mock_db,
            product_id=1,
            provider_id=1,
            source_url="https://provider.com/product/1",
            price=99.99,
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.refresh.called

    @pytest.mark.asyncio
    async def test_get_provider_product_links(
        self, provider_service, mock_db, sample_product_link
    ):
        """Test getting product links for a provider."""
        # Mock query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [sample_product_link]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await provider_service.get_provider_product_links(mock_db, 1)

        assert len(result) == 1
        assert result[0] == sample_product_link
        assert mock_db.execute.called


class TestWebScraping:
    """Test web scraping functionality."""

    @pytest.mark.asyncio
    @patch("app.services.provider_service.ScrapingService")
    async def test_scrape_product_success(
        self, mock_scraping_service, provider_service, sample_provider
    ):
        """Test successful product scraping."""
        # Mock scraping service
        mock_scraper_instance = AsyncMock()
        mock_scraper_instance.scrape_url.return_value = {
            "price": 99.99,
            "title": "Test Product",
            "availability": "In Stock",
            "success": True,
        }
        mock_scraping_service.return_value = mock_scraper_instance

        result = await provider_service.scrape_product_from_provider(
            sample_provider, "https://testprovider.com/product/123"
        )

        assert result["success"] is True
        assert result["price"] == 99.99
        assert result["title"] == "Test Product"

    @pytest.mark.asyncio
    @patch("app.services.provider_service.ScrapingService")
    async def test_scrape_product_error(
        self, mock_scraping_service, provider_service, sample_provider
    ):
        """Test scraping error handling."""
        # Mock scraping service error
        mock_scraper_instance = AsyncMock()
        mock_scraper_instance.scrape_url.side_effect = Exception("Network error")
        mock_scraping_service.return_value = mock_scraper_instance

        result = await provider_service.scrape_product_from_provider(
            sample_provider, "https://testprovider.com/product/123"
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_scrape_multiple_products(
        self, provider_service, mock_db, sample_provider
    ):
        """Test scraping multiple products concurrently."""
        with (
            patch.object(provider_service, "get_provider_by_id") as mock_get_provider,
            patch.object(
                provider_service, "scrape_product_from_provider"
            ) as mock_scrape,
        ):
            mock_get_provider.return_value = sample_provider
            mock_scrape.side_effect = [
                {"success": True, "price": 99.99},
                {"success": True, "price": 149.99},
                {"success": False, "error": "Not found"},
            ]

            urls = [
                "https://testprovider.com/product/1",
                "https://testprovider.com/product/2",
                "https://testprovider.com/product/3",
            ]

            results = await provider_service.scrape_multiple_products(
                mock_db, 1, urls, max_concurrent=2
            )

            assert len(results) == 3
            assert mock_scrape.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limiting(self, provider_service, sample_provider):
        """Test rate limiting functionality."""
        # Set very low rate limit
        sample_provider.rate_limit = 0.1  # 10 requests per second

        start_time = datetime.utcnow()

        with patch.object(
            provider_service, "scrape_product_from_provider"
        ) as mock_scrape:
            mock_scrape.return_value = {"success": True}

            # Scrape multiple URLs (should be rate limited)
            urls = ["https://test.com/1", "https://test.com/2"]
            await provider_service.scrape_multiple_products(mock_db, 1, urls)

        # Should take at least the rate limit time
        duration = (datetime.utcnow() - start_time).total_seconds()
        expected_min_duration = len(urls) / sample_provider.rate_limit
        # Allow some tolerance for timing
        assert duration >= (expected_min_duration * 0.8)


class TestPriceUpdates:
    """Test price update functionality."""

    @pytest.mark.asyncio
    async def test_update_prices_from_provider(
        self, provider_service, mock_db, sample_provider, sample_product_link
    ):
        """Test updating prices from provider."""
        with (
            patch.object(provider_service, "get_provider_by_id") as mock_get_provider,
            patch.object(
                provider_service, "get_provider_product_links"
            ) as mock_get_links,
            patch.object(
                provider_service, "scrape_product_from_provider"
            ) as mock_scrape,
        ):
            mock_get_provider.return_value = sample_provider
            mock_get_links.return_value = [sample_product_link]
            mock_scrape.return_value = {
                "success": True,
                "price": 89.99,  # Price changed
                "title": "Test Product",
            }

            mock_db.add = Mock()
            mock_db.commit = AsyncMock()

            result = await provider_service.update_prices_from_provider(
                mock_db, 1, create_price_records=True
            )

            assert result["products_updated"] == 1
            assert len(result["price_changes"]) == 1
            assert result["price_changes"][0]["old_price"] == 99.99
            assert result["price_changes"][0]["new_price"] == 89.99

    @pytest.mark.asyncio
    async def test_update_prices_no_changes(
        self, provider_service, mock_db, sample_provider, sample_product_link
    ):
        """Test price update with no price changes."""
        with (
            patch.object(provider_service, "get_provider_by_id") as mock_get_provider,
            patch.object(
                provider_service, "get_provider_product_links"
            ) as mock_get_links,
            patch.object(
                provider_service, "scrape_product_from_provider"
            ) as mock_scrape,
        ):
            mock_get_provider.return_value = sample_provider
            mock_get_links.return_value = [sample_product_link]
            mock_scrape.return_value = {
                "success": True,
                "price": 99.99,  # Same price
                "title": "Test Product",
            }

            result = await provider_service.update_prices_from_provider(
                mock_db, 1, create_price_records=False
            )

            assert result["products_updated"] == 1
            assert len(result["price_changes"]) == 0


class TestPerformanceMonitoring:
    """Test performance monitoring functionality."""

    @pytest.mark.asyncio
    async def test_get_provider_performance(
        self, provider_service, mock_db, sample_provider
    ):
        """Test getting provider performance metrics."""
        # Mock database queries for performance metrics
        mock_results = [
            Mock(
                scalars=Mock(return_value=Mock(first=Mock(return_value=Mock(count=5))))
            ),  # active links
            Mock(
                scalars=Mock(
                    return_value=Mock(first=Mock(return_value=Mock(count=100)))
                )
            ),  # price records
            Mock(
                scalars=Mock(
                    return_value=Mock(first=Mock(return_value=Mock(avg_requests=50.0)))
                )
            ),  # avg requests
        ]

        mock_db.execute = AsyncMock(side_effect=mock_results)

        with patch.object(provider_service, "get_provider_by_id") as mock_get_provider:
            mock_get_provider.return_value = sample_provider

            result = await provider_service.get_provider_performance(
                mock_db, 1, days=30
            )

            assert result["provider_id"] == 1
            assert result["provider_name"] == "Test Provider"
            assert result["health_status"] == "healthy"
            assert result["active_product_links"] == 5
            assert result["price_records_last_30_days"] == 100

    @pytest.mark.asyncio
    async def test_get_provider_performance_not_found(self, provider_service, mock_db):
        """Test performance metrics for non-existent provider."""
        with patch.object(provider_service, "get_provider_by_id") as mock_get_provider:
            mock_get_provider.return_value = None

            with pytest.raises(ValueError, match="not found"):
                await provider_service.get_provider_performance(mock_db, 999, days=30)


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_database_error_handling(self, provider_service, mock_db):
        """Test database error handling."""
        mock_db.commit = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception):
            await provider_service.create_provider(
                db_session=mock_db, name="Test Provider", base_url="https://test.com"
            )

    @pytest.mark.asyncio
    async def test_invalid_scraping_config(self, provider_service):
        """Test handling invalid scraping configurations."""
        invalid_config = {"invalid_key": "invalid_value"}

        # This should not raise an error but use default config
        config = provider_service._get_scraping_config(
            "unknown_provider", invalid_config
        )
        assert config is not None

    @pytest.mark.asyncio
    async def test_concurrent_scraping_limits(
        self, provider_service, mock_db, sample_provider
    ):
        """Test concurrent scraping with limits."""
        with patch.object(provider_service, "get_provider_by_id") as mock_get_provider:
            mock_get_provider.return_value = sample_provider

            # Test with more URLs than concurrent limit
            urls = [f"https://test.com/product/{i}" for i in range(20)]

            with patch.object(
                provider_service, "scrape_product_from_provider"
            ) as mock_scrape:
                mock_scrape.return_value = {"success": True, "price": 99.99}

                results = await provider_service.scrape_multiple_products(
                    mock_db, 1, urls, max_concurrent=5
                )

                assert len(results) == 20
                assert mock_scrape.call_count == 20


class TestScrapingConfigurations:
    """Test pre-configured scraping setups."""

    def test_amazon_config(self, provider_service):
        """Test Amazon scraping configuration."""
        config = provider_service._get_scraping_config("amazon")

        assert "price_selector" in config
        assert "title_selector" in config
        assert config["user_agent"] is not None

    def test_walmart_config(self, provider_service):
        """Test Walmart scraping configuration."""
        config = provider_service._get_scraping_config("walmart")

        assert "price_selector" in config
        assert "title_selector" in config
        assert config["user_agent"] is not None

    def test_custom_config_override(self, provider_service):
        """Test custom configuration override."""
        custom_config = {
            "price_selector": ".custom-price",
            "title_selector": ".custom-title",
        }

        config = provider_service._get_scraping_config("amazon", custom_config)

        assert config["price_selector"] == ".custom-price"
        assert config["title_selector"] == ".custom-title"


@pytest.mark.asyncio
async def test_provider_service_close(provider_service):
    """Test provider service cleanup."""
    with patch.object(provider_service.scraping_service, "close") as mock_close:
        await provider_service.close()
        mock_close.assert_called_once()


# Integration test fixtures
@pytest.fixture
def integration_db():
    """Integration test database fixture."""
    # In real tests, this would set up a test database
    pass


@pytest.mark.integration
class TestProviderIntegration:
    """Integration tests requiring actual database."""

    @pytest.mark.asyncio
    async def test_full_provider_workflow(self, integration_db):
        """Test complete provider workflow from creation to scraping."""
        # This would test the full workflow in a real environment
        pass

    @pytest.mark.asyncio
    async def test_real_scraping_performance(self, integration_db):
        """Test scraping performance with real websites."""
        # This would test against actual websites (rate-limited)
        pass
