"""
Test cases for Data Ingestion & Processing - TDD Implementation.
These tests cover web scraping, data validation, ETL pipelines,
price parsing, provider integration, and data quality assurance.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from app.exceptions import ParsingError, ScrapingError
from app.services.data_ingestion import DataIngestionService
from app.services.etl import DataTransformer, ETLPipeline
from app.services.parser import DataValidator, PriceParser
from app.services.quality import DataQualityChecker
from app.services.scraper import ProductScraper, ScrapingService


class TestScrapingService:
    """Test cases for web scraping functionality."""

    def test_scraping_service_initialization(self):
        """Test ScrapingService initialization."""
        service = ScrapingService()

        assert service.session is not None
        assert service.user_agents is not None
        assert len(service.user_agents) > 0
        assert service.request_delay >= 1.0
        assert service.max_retries >= 3

    @pytest.mark.asyncio
    async def test_scrape_product_page_success(self):
        """Test successful product page scraping."""
        service = ScrapingService()

        # Mock HTML response
        mock_html = """
        <html>
            <body>
                <h1 class="product-title">Test Product</h1>
                <span class="price">$99.99</span>
                <div class="availability">In Stock</div>
                <div class="description">Test product description</div>
            </body>
        </html>
        """

        with patch.object(service, "_fetch_page", return_value=mock_html):
            result = await service.scrape_product_page(
                url="https://example.com/product/123",
                selectors={
                    "title": ".product-title",
                    "price": ".price",
                    "availability": ".availability",
                    "description": ".description",
                },
            )

        assert result["title"] == "Test Product"
        assert result["price"] == "$99.99"
        assert result["availability"] == "In Stock"
        assert result["description"] == "Test product description"

    @pytest.mark.asyncio
    async def test_scrape_with_missing_elements(self):
        """Test scraping when some elements are missing."""
        service = ScrapingService()

        mock_html = """
        <html>
            <body>
                <h1 class="product-title">Test Product</h1>
                <span class="price">$99.99</span>
                <!-- Missing availability and description -->
            </body>
        </html>
        """

        with patch.object(service, "_fetch_page", return_value=mock_html):
            result = await service.scrape_product_page(
                url="https://example.com/product/123",
                selectors={
                    "title": ".product-title",
                    "price": ".price",
                    "availability": ".availability",
                    "description": ".description",
                },
            )

        assert result["title"] == "Test Product"
        assert result["price"] == "$99.99"
        assert result["availability"] is None
        assert result["description"] is None

    @pytest.mark.asyncio
    async def test_scraping_with_rate_limiting(self):
        """Test scraping with rate limiting."""
        service = ScrapingService()
        service.request_delay = 0.1  # Shorter for testing

        start_time = datetime.now()

        with patch.object(service, "_fetch_page", return_value="<html></html>"):
            await service.scrape_product_page("https://example.com/1", {})
            await service.scrape_product_page("https://example.com/2", {})

        elapsed = (datetime.now() - start_time).total_seconds()
        assert elapsed >= 0.1  # Should respect rate limiting

    @pytest.mark.asyncio
    async def test_scraping_error_handling(self):
        """Test error handling during scraping."""
        service = ScrapingService()

        with patch.object(
            service, "_fetch_page", side_effect=Exception("Network error")
        ):
            with pytest.raises(ScrapingError) as exc_info:
                await service.scrape_product_page("https://example.com/product/123", {})

        assert "Network error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_scraping_retry_mechanism(self):
        """Test retry mechanism for failed requests."""
        service = ScrapingService()
        service.max_retries = 3

        # Mock session.get to fail twice, then succeed
        call_count = 0

        class MockResponse:
            def __init__(self, status, text_content):
                self.status = status
                self._text_content = text_content

            async def text(self):
                return self._text_content

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class MockAsyncContextManager:
            def __init__(self, response):
                self._response = response

            async def __aenter__(self):
                return self._response

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        def mock_get(url, headers=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # Simulate network failure
                raise aiohttp.ClientError("Temporary failure")
            # Third attempt succeeds
            response = MockResponse(200, "<html><div class='price'>$99.99</div></html>")
            return MockAsyncContextManager(response)

        # Mock the session and get method
        mock_session = AsyncMock()
        mock_session.get = mock_get
        mock_session.closed = False

        with patch.object(service, "_get_session", return_value=mock_session):
            with patch.object(service, "_rate_limit", return_value=None):
                result = await service.scrape_product_page(
                    "https://example.com/product/123", {"price": ".price"}
                )

        assert call_count == 3
        assert result["price"] == "$99.99"

    def test_user_agent_rotation(self):
        """Test user agent rotation for scraping."""
        service = ScrapingService()

        agent1 = service.get_random_user_agent()
        agent2 = service.get_random_user_agent()

        # Should have multiple user agents available
        assert len(service.user_agents) > 1
        assert agent1 in service.user_agents
        assert agent2 in service.user_agents


class TestProductScraper:
    """Test cases for product-specific scraping."""

    def test_amazon_scraper_configuration(self):
        """Test Amazon scraper configuration."""
        scraper = ProductScraper(provider="amazon")

        assert scraper.provider == "amazon"
        assert scraper.base_url == "https://amazon.com"
        assert "price" in scraper.selectors
        assert "title" in scraper.selectors
        assert "availability" in scraper.selectors

    def test_scraper_selector_customization(self):
        """Test custom selector configuration."""
        custom_selectors = {
            "price": ".custom-price",
            "title": ".custom-title",
            "availability": ".custom-stock",
        }

        scraper = ProductScraper(provider="custom", selectors=custom_selectors)

        assert scraper.selectors == custom_selectors

    @pytest.mark.asyncio
    async def test_scrape_multiple_products(self):
        """Test scraping multiple products efficiently."""
        scraper = ProductScraper(provider="test")

        urls = [
            "https://example.com/product/1",
            "https://example.com/product/2",
            "https://example.com/product/3",
        ]

        mock_results = [
            {"title": "Product 1", "price": "$10.00"},
            {"title": "Product 2", "price": "$20.00"},
            {"title": "Product 3", "price": "$30.00"},
        ]

        with patch.object(
            scraper.scraping_service, "scrape_product_page", side_effect=mock_results
        ):
            results = await scraper.scrape_multiple_products(urls)

        assert len(results) == 3
        assert results[0]["title"] == "Product 1"
        assert results[1]["price"] == "$20.00"

    @pytest.mark.asyncio
    async def test_scraper_concurrent_limits(self):
        """Test concurrent scraping limits."""
        scraper = ProductScraper(provider="test", max_concurrent=2)

        urls = ["https://example.com/product/{}".format(i) for i in range(5)]

        start_time = datetime.now()

        with patch.object(
            scraper.scraping_service,
            "scrape_product_page",
            return_value={"title": "Test", "price": "$10.00"},
        ):
            await scraper.scrape_multiple_products(urls)

        # Should respect concurrency limits
        elapsed = (datetime.now() - start_time).total_seconds()
        assert elapsed >= 0.1  # Minimum time due to concurrency control


class TestPriceParser:
    """Test cases for price parsing and data extraction."""

    def test_price_parser_initialization(self):
        """Test PriceParser initialization."""
        parser = PriceParser()

        assert parser.currency_symbols is not None
        assert "$" in parser.currency_symbols
        assert "€" in parser.currency_symbols
        assert "£" in parser.currency_symbols

    def test_parse_simple_price(self):
        """Test parsing simple price formats."""
        parser = PriceParser()

        test_cases = [
            ("$99.99", 99.99, "USD"),
            ("€125.50", 125.50, "EUR"),
            ("£75.25", 75.25, "GBP"),
            ("¥1000", 1000.0, "JPY"),
            ("$1,234.56", 1234.56, "USD"),
        ]

        for price_text, expected_amount, expected_currency in test_cases:
            result = parser.parse_price(price_text)
            assert result["amount"] == expected_amount
            assert result["currency"] == expected_currency

    def test_parse_complex_price_formats(self):
        """Test parsing complex price formats."""
        parser = PriceParser()

        test_cases = [
            ("Price: $99.99 each", 99.99, "USD"),
            ("Was $150.00 Now $99.99", 99.99, "USD"),
            ("From $29.99", 29.99, "USD"),
            ("Only €45.50!", 45.50, "EUR"),
            ("Sale: £199.99 (Save 50%)", 199.99, "GBP"),
        ]

        for price_text, expected_amount, expected_currency in test_cases:
            result = parser.parse_price(price_text)
            assert result["amount"] == expected_amount
            assert result["currency"] == expected_currency

    def test_parse_invalid_price_formats(self):
        """Test handling of invalid price formats."""
        parser = PriceParser()

        invalid_prices = [
            "No price available",
            "Call for pricing",
            "TBD",
            "Contact us",
            "",
            "abc123",
        ]

        for invalid_price in invalid_prices:
            with pytest.raises(ParsingError):
                parser.parse_price(invalid_price)

    def test_parse_availability_status(self):
        """Test parsing availability status."""
        parser = PriceParser()

        test_cases = [
            ("In Stock", True),
            ("Available", True),
            ("In stock", True),
            ("Out of Stock", False),
            ("Temporarily Unavailable", False),
            ("Sold Out", False),
            ("Coming Soon", False),
            ("Pre-order", True),  # Consider pre-order as available
        ]

        for status_text, expected_available in test_cases:
            result = parser.parse_availability(status_text)
            assert result == expected_available

    def test_extract_product_details(self):
        """Test extracting structured product details."""
        parser = PriceParser()

        raw_data = {
            "title": "Apple iPhone 14 Pro 128GB Space Black",
            "price": "$999.99",
            "availability": "In Stock",
            "description": "Latest iPhone with A16 Bionic chip",
            "brand": "Apple",
            "model": "iPhone 14 Pro",
        }

        result = parser.extract_product_details(raw_data)

        assert result["name"] == "Apple iPhone 14 Pro 128GB Space Black"
        assert result["price_amount"] == 999.99
        assert result["currency"] == "USD"
        assert result["is_available"] is True
        assert result["description"] == "Latest iPhone with A16 Bionic chip"
        assert result["brand"] == "Apple"

    def test_normalize_product_name(self):
        """Test product name normalization."""
        parser = PriceParser()

        test_cases = [
            ("  Apple iPhone 14 Pro  ", "Apple iPhone 14 Pro"),
            ("SAMSUNG GALAXY S23", "Samsung Galaxy S23"),
            ("sony-playstation-5", "Sony Playstation 5"),
            ("Nike_Air_Max_270", "Nike Air Max 270"),
        ]

        for input_name, expected_name in test_cases:
            result = parser.normalize_product_name(input_name)
            assert result == expected_name


class TestDataValidator:
    """Test cases for data validation."""

    def test_data_validator_initialization(self):
        """Test DataValidator initialization."""
        validator = DataValidator()

        assert validator.required_fields is not None
        assert validator.validation_rules is not None

    def test_validate_product_data(self):
        """Test product data validation."""
        validator = DataValidator()

        valid_data = {
            "name": "Test Product",
            "price_amount": 99.99,
            "currency": "USD",
            "is_available": True,
            "provider_url": "https://example.com/product/123",
        }

        result = validator.validate_product_data(valid_data)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_invalid_product_data(self):
        """Test validation of invalid product data."""
        validator = DataValidator()

        invalid_data = {
            "name": "",  # Empty name
            "price_amount": -10.0,  # Negative price
            "currency": "INVALID",  # Invalid currency
            "provider_url": "not-a-url",  # Invalid URL
        }

        result = validator.validate_product_data(invalid_data)
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("name" in error for error in result.errors)
        assert any("price_amount" in error for error in result.errors)

    def test_validate_price_range(self):
        """Test price range validation."""
        validator = DataValidator()

        # Valid prices
        assert validator.validate_price(10.00) is True
        assert validator.validate_price(999999.99) is True

        # Invalid prices
        assert validator.validate_price(-5.00) is False
        assert validator.validate_price(0.00) is False
        assert validator.validate_price(None) is False

    def test_validate_currency_code(self):
        """Test currency code validation."""
        validator = DataValidator()

        # Valid currencies
        valid_currencies = ["USD", "EUR", "GBP", "JPY", "CAD"]
        for currency in valid_currencies:
            assert validator.validate_currency(currency) is True

        # Invalid currencies
        invalid_currencies = ["US", "Dollar", "123", "", None]
        for currency in invalid_currencies:
            assert validator.validate_currency(currency) is False

    def test_validate_url_format(self):
        """Test URL format validation."""
        validator = DataValidator()

        # Valid URLs
        valid_urls = [
            "https://example.com/product/123",
            "http://shop.example.org/item",
            "https://amazon.com/dp/B0123456",
        ]
        for url in valid_urls:
            assert validator.validate_url(url) is True

        # Invalid URLs
        invalid_urls = ["not-a-url", "ftp://example.com", "example.com", "", None]
        for url in invalid_urls:
            assert validator.validate_url(url) is False


class TestETLPipeline:
    """Test cases for ETL (Extract, Transform, Load) pipeline."""

    def test_etl_pipeline_initialization(self):
        """Test ETL pipeline initialization."""
        pipeline = ETLPipeline()

        assert pipeline.extractors is not None
        assert pipeline.transformers is not None
        assert pipeline.loaders is not None

    @pytest.mark.asyncio
    async def test_extract_data_from_source(self):
        """Test data extraction from source."""
        pipeline = ETLPipeline()

        # Mock data source
        mock_source = {
            "type": "web_scraper",
            "urls": ["https://example.com/product/1", "https://example.com/product/2"],
            "selectors": {"price": ".price", "title": ".title"},
        }

        mock_extracted_data = [
            {
                "title": "Product 1",
                "price": "$10.00",
                "url": "https://example.com/product/1",
            },
            {
                "title": "Product 2",
                "price": "$20.00",
                "url": "https://example.com/product/2",
            },
        ]

        with patch.object(
            pipeline, "_extract_from_scraper", return_value=mock_extracted_data
        ):
            result = await pipeline.extract_data(mock_source)

        assert len(result) == 2
        assert result[0]["title"] == "Product 1"
        assert result[1]["price"] == "$20.00"

    @pytest.mark.asyncio
    async def test_transform_extracted_data(self):
        """Test data transformation."""
        pipeline = ETLPipeline()

        raw_data = [
            {"title": "  Product 1  ", "price": "$10.00", "availability": "In Stock"},
            {"title": "PRODUCT 2", "price": "€25.50", "availability": "Out of Stock"},
        ]

        transformed_data = await pipeline.transform_data(raw_data)

        assert len(transformed_data) == 2
        assert transformed_data[0]["name"] == "Product 1"  # Normalized
        assert transformed_data[0]["price_amount"] == 10.00
        assert transformed_data[0]["currency"] == "USD"
        assert transformed_data[0]["is_available"] is True

        assert transformed_data[1]["name"] == "Product 2"
        assert transformed_data[1]["price_amount"] == 25.50
        assert transformed_data[1]["currency"] == "EUR"
        assert transformed_data[1]["is_available"] is False

    @pytest.mark.asyncio
    async def test_load_data_to_database(self):
        """Test loading data to database."""
        pipeline = ETLPipeline()

        processed_data = [
            {
                "name": "Test Product",
                "price_amount": 99.99,
                "currency": "USD",
                "is_available": True,
                "provider_id": 1,
                "provider_url": "https://example.com/product/123",
            }
        ]

        with patch.object(pipeline, "_save_to_database") as mock_save:
            mock_save.return_value = {"created": 1, "updated": 0, "errors": 0}

            result = await pipeline.load_data(processed_data)

        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["errors"] == 0
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_etl_pipeline(self):
        """Test complete ETL pipeline execution."""
        pipeline = ETLPipeline()

        source_config = {
            "type": "web_scraper",
            "provider_id": 1,
            "urls": ["https://example.com/product/123"],
        }

        # Mock all pipeline stages
        with patch.object(
            pipeline, "extract_data", return_value=[{"title": "Test", "price": "$10"}]
        ):
            with patch.object(
                pipeline,
                "transform_data",
                return_value=[{"name": "Test", "price_amount": 10.0}],
            ):
                with patch.object(pipeline, "load_data", return_value={"created": 1}):
                    result = await pipeline.run(source_config)

        assert result["status"] == "success"
        assert result["records_processed"] == 1
        assert result["created"] == 1

    @pytest.mark.asyncio
    async def test_etl_error_handling(self):
        """Test ETL pipeline error handling."""
        pipeline = ETLPipeline()

        source_config = {"type": "invalid_source"}

        # The pipeline catches ETLError and returns error response
        result = await pipeline.run(source_config)
        assert result["status"] == "error"
        assert "Unsupported source type" in result["error_message"]


class TestDataTransformer:
    """Test cases for data transformation logic."""

    def test_transformer_initialization(self):
        """Test DataTransformer initialization."""
        transformer = DataTransformer()

        assert transformer.transformation_rules is not None

    def test_normalize_text_data(self):
        """Test text data normalization."""
        transformer = DataTransformer()

        test_cases = [
            ("  Product Name  ", "Product Name"),
            ("UPPERCASE TEXT", "Uppercase Text"),
            ("mixed_case-text", "Mixed Case Text"),
            ("Product\nwith\nnewlines", "Product with newlines"),
        ]

        for input_text, expected_output in test_cases:
            result = transformer.normalize_text(input_text)
            assert result == expected_output

    def test_standardize_currency_data(self):
        """Test currency data standardization."""
        transformer = DataTransformer()

        # Test currency symbol mapping
        symbol_mappings = [("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("¥", "JPY")]

        for symbol, expected_code in symbol_mappings:
            result = transformer.map_currency_symbol(symbol)
            assert result == expected_code

    def test_clean_price_data(self):
        """Test price data cleaning."""
        transformer = DataTransformer()

        dirty_prices = [
            "Price: $99.99",
            "$1,234.56 each",
            "Only €45.50!",
            "From £199.99",
        ]

        clean_prices = [99.99, 1234.56, 45.50, 199.99]

        for dirty_price, expected_clean in zip(dirty_prices, clean_prices):
            result = transformer.clean_price_text(dirty_price)
            assert result == expected_clean

    def test_enrich_product_data(self):
        """Test product data enrichment."""
        transformer = DataTransformer()

        base_data = {
            "name": "Apple iPhone 14",
            "price_amount": 999.99,
            "currency": "USD",
        }

        enriched_data = transformer.enrich_product_data(base_data)

        # Should add computed fields
        assert "slug" in enriched_data
        assert "brand" in enriched_data
        assert "category" in enriched_data
        assert enriched_data["slug"] == "apple-iphone-14"
        assert enriched_data["brand"] == "Apple"


class TestDataQualityChecker:
    """Test cases for data quality validation."""

    def test_quality_checker_initialization(self):
        """Test DataQualityChecker initialization."""
        checker = DataQualityChecker()

        assert checker.quality_rules is not None
        assert checker.thresholds is not None

    def test_check_data_completeness(self):
        """Test data completeness validation."""
        checker = DataQualityChecker()

        complete_data = [
            {"name": "Product 1", "price": 10.0, "availability": True},
            {"name": "Product 2", "price": 20.0, "availability": False},
        ]

        incomplete_data = [
            {"name": "Product 1", "price": 10.0},  # Missing availability
            {"name": "", "price": 20.0, "availability": True},  # Empty name
        ]

        complete_score = checker.check_completeness(complete_data)
        incomplete_score = checker.check_completeness(incomplete_data)

        assert complete_score == 1.0  # 100% complete
        assert incomplete_score < 1.0  # Less than 100% complete

    def test_check_data_accuracy(self):
        """Test data accuracy validation."""
        checker = DataQualityChecker()

        data_batch = [
            {"name": "Valid Product", "price": 99.99, "currency": "USD"},
            {
                "name": "Another Product",
                "price": -10.0,
                "currency": "INVALID",
            },  # Invalid
            {"name": "", "price": 50.0, "currency": "EUR"},  # Invalid name
        ]

        accuracy_score = checker.check_accuracy(data_batch)

        assert 0.0 <= accuracy_score <= 1.0
        assert accuracy_score < 1.0  # Should detect invalid data

    def test_check_data_consistency(self):
        """Test data consistency validation."""
        checker = DataQualityChecker()

        consistent_data = [
            {"name": "Product A", "brand": "Apple", "category": "Electronics"},
            {"name": "Product B", "brand": "Samsung", "category": "Electronics"},
        ]

        inconsistent_data = [
            {"name": "Product A", "brand": "Apple", "category": "Electronics"},
            {
                "name": "Product B",
                "brand": "Samsung",
                "category": "Clothing",
            },  # Different format
        ]

        consistent_score = checker.check_consistency(consistent_data)
        inconsistent_score = checker.check_consistency(inconsistent_data)

        assert consistent_score >= inconsistent_score

    def test_detect_duplicate_entries(self):
        """Test duplicate detection."""
        checker = DataQualityChecker()

        data_with_duplicates = [
            {"name": "Product A", "url": "https://example.com/a"},
            {"name": "Product B", "url": "https://example.com/b"},
            {"name": "Product A", "url": "https://example.com/a"},  # Duplicate
        ]

        duplicates = checker.detect_duplicates(data_with_duplicates)

        assert len(duplicates) == 1
        assert duplicates[0]["count"] == 2
        assert duplicates[0]["name"] == "Product A"

    def test_generate_quality_report(self):
        """Test quality report generation."""
        checker = DataQualityChecker()

        test_data = [
            {"name": "Good Product", "price": 99.99, "currency": "USD"},
            {"name": "", "price": -10.0, "currency": "INVALID"},  # Poor quality
        ]

        report = checker.generate_quality_report(test_data)

        assert "completeness_score" in report
        assert "accuracy_score" in report
        assert "consistency_score" in report
        assert "duplicate_count" in report
        assert "total_records" in report
        assert "issues" in report

        assert report["total_records"] == 2
        assert len(report["issues"]) > 0


class TestDataIngestionService:
    """Test cases for the main data ingestion service."""

    def test_ingestion_service_initialization(self):
        """Test DataIngestionService initialization."""
        service = DataIngestionService()

        assert service.scraper is not None
        assert service.parser is not None
        assert service.validator is not None
        assert service.etl_pipeline is not None
        assert service.quality_checker is not None

    @pytest.mark.asyncio
    async def test_ingest_from_provider(self):
        """Test data ingestion from a provider."""
        service = DataIngestionService()

        provider_config = {
            "provider_id": 1,
            "name": "Test Provider",
            "base_url": "https://example.com",
            "products": [
                {
                    "url": "https://example.com/product/1",
                    "selectors": {"price": ".price"},
                }
            ],
        }

        # Mock the entire ingestion pipeline
        with patch.object(service.scraper, "scrape_multiple_products") as mock_scrape:
            with patch.object(service.etl_pipeline, "run") as mock_etl:
                mock_scrape.return_value = [{"title": "Test", "price": "$10"}]
                mock_etl.return_value = {
                    "status": "success",
                    "created": 1,
                    "records_extracted": 1,
                    "records_processed": 1,
                    "execution_time_seconds": 1.5,
                }

                result = await service.ingest_from_provider(provider_config)

        assert result["status"] == "success"
        assert result["provider_id"] == 1
        assert result["records_created"] == 1

    @pytest.mark.asyncio
    async def test_scheduled_ingestion(self):
        """Test scheduled data ingestion."""
        service = DataIngestionService()

        # Mock providers and ingestion
        mock_providers = [
            {"id": 1, "name": "Provider 1", "is_active": True},
            {"id": 2, "name": "Provider 2", "is_active": True},
        ]

        with patch.object(service, "get_active_providers", return_value=mock_providers):
            with patch.object(service, "ingest_from_provider") as mock_ingest:
                mock_ingest.return_value = {"status": "success", "records_created": 5}

                result = await service.run_scheduled_ingestion()

        assert result["total_providers"] == 2
        assert result["successful_ingestions"] == 2
        assert result["total_records_created"] == 10

    @pytest.mark.asyncio
    async def test_ingestion_error_recovery(self):
        """Test error recovery during ingestion."""
        service = DataIngestionService()

        provider_config = {"provider_id": 1, "name": "Failing Provider"}

        with patch.object(
            service.scraper,
            "scrape_multiple_products",
            side_effect=ScrapingError("Network timeout"),
        ):
            result = await service.ingest_from_provider(provider_config)

        assert result["status"] == "error"
        assert "Network timeout" in result["error_message"]
        assert result["records_created"] == 0

    def test_configure_ingestion_schedule(self):
        """Test ingestion schedule configuration."""
        service = DataIngestionService()

        schedule_config = {
            "interval_minutes": 30,
            "providers": [1, 2, 3],
            "max_concurrent": 2,
            "retry_failed": True,
        }

        service.configure_schedule(schedule_config)

        assert service.schedule_config["interval_minutes"] == 30
        assert service.schedule_config["max_concurrent"] == 2
        assert service.schedule_config["retry_failed"] is True

    @pytest.mark.asyncio
    async def test_data_ingestion_monitoring(self):
        """Test data ingestion monitoring and metrics."""
        service = DataIngestionService()

        # Run some ingestion operations
        with patch.object(service, "ingest_from_provider") as mock_ingest:
            mock_ingest.return_value = {
                "status": "success",
                "records_created": 10,
                "processing_time_ms": 1500,
            }

            await service.ingest_from_provider({"provider_id": 1})
            await service.ingest_from_provider({"provider_id": 2})

        # Get monitoring metrics
        metrics = service.get_ingestion_metrics()

        assert metrics["total_ingestions"] == 2
        assert metrics["successful_ingestions"] == 2
        assert metrics["total_records_processed"] == 20
        assert "average_processing_time_ms" in metrics


# Fixtures for data ingestion testing
@pytest.fixture
def sample_scraped_data():
    """Sample scraped data for testing."""
    return [
        {
            "title": "Apple iPhone 14 Pro 128GB",
            "price": "$999.99",
            "availability": "In Stock",
            "description": "Latest iPhone with A16 Bionic chip",
            "url": "https://example.com/iphone-14-pro",
        },
        {
            "title": "Samsung Galaxy S23 Ultra",
            "price": "€1,199.00",
            "availability": "Available",
            "description": "Premium Android smartphone",
            "url": "https://example.com/galaxy-s23-ultra",
        },
    ]


@pytest.fixture
def sample_provider_config():
    """Sample provider configuration for testing."""
    return {
        "provider_id": 1,
        "name": "Test Electronics Store",
        "base_url": "https://electronics.example.com",
        "rate_limit": 60,
        "selectors": {
            "title": ".product-title",
            "price": ".price-current",
            "availability": ".stock-status",
            "description": ".product-description",
        },
        "products": [
            {
                "product_id": 1,
                "url": "https://electronics.example.com/smartphone/iphone-14",
                "category": "Smartphones",
            },
            {
                "product_id": 2,
                "url": "https://electronics.example.com/laptop/macbook-pro",
                "category": "Laptops",
            },
        ],
    }


@pytest.fixture
def mock_html_response():
    """Mock HTML response for testing scraping."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Product Page</title>
    </head>
    <body>
        <div class="product-container">
            <h1 class="product-title">Apple iPhone 14 Pro 128GB Space Black</h1>
            <div class="price-section">
                <span class="price-current">$999.99</span>
                <span class="price-original">$1,099.99</span>
            </div>
            <div class="stock-section">
                <span class="stock-status">In Stock</span>
                <span class="delivery-info">Ships within 2-3 business days</span>
            </div>
            <div class="product-details">
                <p class="product-description">
                    The iPhone 14 Pro features the A16 Bionic chip, 
                    Pro camera system, and Dynamic Island.
                </p>
                <ul class="specifications">
                    <li>6.1-inch Super Retina XDR display</li>
                    <li>128GB storage capacity</li>
                    <li>5G connectivity</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """
