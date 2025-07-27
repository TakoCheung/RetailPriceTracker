"""
Main data ingestion service that orchestrates the entire data ingestion process.
Handles scheduling, provider management, and monitoring.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.exceptions import ETLError, ProviderError, ScrapingError
from app.services.etl import ETLPipeline
from app.services.parser import DataValidator, PriceParser
from app.services.quality import DataQualityChecker
from app.services.scraper import ProductScraper


class IngestionMetrics:
    """Tracks ingestion metrics and performance."""

    def __init__(self):
        self.total_ingestions = 0
        self.successful_ingestions = 0
        self.failed_ingestions = 0
        self.total_records_processed = 0
        self.total_processing_time_ms = 0
        self.error_log = []
        self.start_time = datetime.now()

    def record_success(self, records_count: int, processing_time_ms: int):
        """Record a successful ingestion."""
        self.total_ingestions += 1
        self.successful_ingestions += 1
        self.total_records_processed += records_count
        self.total_processing_time_ms += processing_time_ms

    def record_failure(self, error_message: str):
        """Record a failed ingestion."""
        self.total_ingestions += 1
        self.failed_ingestions += 1
        self.error_log.append({"timestamp": datetime.now(), "error": error_message})

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()

        return {
            "total_ingestions": self.total_ingestions,
            "successful_ingestions": self.successful_ingestions,
            "failed_ingestions": self.failed_ingestions,
            "success_rate": self.successful_ingestions / max(self.total_ingestions, 1),
            "total_records_processed": self.total_records_processed,
            "average_processing_time_ms": self.total_processing_time_ms
            / max(self.successful_ingestions, 1),
            "uptime_seconds": uptime_seconds,
            "records_per_second": self.total_records_processed / max(uptime_seconds, 1),
            "recent_errors": self.error_log[-5:],  # Last 5 errors
        }


class DataIngestionService:
    """Main service for coordinating data ingestion operations."""

    def __init__(self):
        self.scraper = ProductScraper(
            provider="default"
        )  # Initialize with default scraper
        self.parser = PriceParser()
        self.validator = DataValidator()
        self.etl_pipeline = ETLPipeline()
        self.quality_checker = DataQualityChecker()
        self.metrics = IngestionMetrics()
        self.schedule_config = {}
        self.active_ingestions = {}

    async def ingest_from_provider(
        self, provider_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Ingest data from a specific provider.

        Args:
            provider_config: Configuration for the provider

        Returns:
            Ingestion result summary
        """
        start_time = datetime.now()
        provider_id = provider_config.get("provider_id")
        provider_name = provider_config.get("name", f"Provider {provider_id}")

        try:
            # Prepare ETL source configuration
            etl_config = {
                "type": "web_scraper",
                "provider": provider_name.lower().replace(" ", "_"),
                "provider_id": provider_id,
                "urls": [
                    product["url"] for product in provider_config.get("products", [])
                ],
                "selectors": provider_config.get("selectors", {}),
                "rate_limit": provider_config.get("rate_limit", 60),
            }

            # Run ETL pipeline
            etl_result = await self.etl_pipeline.run(etl_config)

            if etl_result["status"] == "success":
                processing_time_ms = int(etl_result["execution_time_seconds"] * 1000)
                records_created = etl_result.get("created", 0)

                self.metrics.record_success(records_created, processing_time_ms)

                return {
                    "status": "success",
                    "provider_id": provider_id,
                    "provider_name": provider_name,
                    "records_extracted": etl_result["records_extracted"],
                    "records_processed": etl_result["records_processed"],
                    "records_created": records_created,
                    "processing_time_ms": processing_time_ms,
                    "quality_score": None,  # Could add quality check here
                }
            else:
                error_message = etl_result.get("error_message", "Unknown ETL error")
                self.metrics.record_failure(
                    f"Provider {provider_name}: {error_message}"
                )

                return {
                    "status": "error",
                    "provider_id": provider_id,
                    "provider_name": provider_name,
                    "error_message": error_message,
                    "records_created": 0,
                }

        except (ScrapingError, ETLError, ProviderError) as e:
            error_message = str(e)
            self.metrics.record_failure(f"Provider {provider_name}: {error_message}")

            return {
                "status": "error",
                "provider_id": provider_id,
                "provider_name": provider_name,
                "error_message": error_message,
                "records_created": 0,
            }
        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            self.metrics.record_failure(f"Provider {provider_name}: {error_message}")

            return {
                "status": "error",
                "provider_id": provider_id,
                "provider_name": provider_name,
                "error_message": error_message,
                "records_created": 0,
            }

    async def get_active_providers(self) -> List[Dict[str, Any]]:
        """
        Get list of active providers for ingestion.

        Returns:
            List of active provider configurations
        """
        # This would typically query the database for active providers
        # For now, return mock data
        return [
            {
                "id": 1,
                "name": "Electronics Store",
                "is_active": True,
                "base_url": "https://electronics.example.com",
                "selectors": {
                    "title": ".product-title",
                    "price": ".price",
                    "availability": ".stock-status",
                },
                "products": [
                    {
                        "url": "https://electronics.example.com/phone/1",
                        "category": "phones",
                    },
                    {
                        "url": "https://electronics.example.com/laptop/1",
                        "category": "laptops",
                    },
                ],
            },
            {
                "id": 2,
                "name": "Fashion Retailer",
                "is_active": True,
                "base_url": "https://fashion.example.com",
                "selectors": {
                    "title": ".item-name",
                    "price": ".price-tag",
                    "availability": ".in-stock",
                },
                "products": [
                    {"url": "https://fashion.example.com/shoes/1", "category": "shoes"},
                    {
                        "url": "https://fashion.example.com/clothes/1",
                        "category": "clothing",
                    },
                ],
            },
        ]

    async def run_scheduled_ingestion(self) -> Dict[str, Any]:
        """
        Run scheduled ingestion for all active providers.

        Returns:
            Summary of scheduled ingestion results
        """
        try:
            providers = await self.get_active_providers()
            ingestion_results = []

            total_providers = len(providers)
            successful_ingestions = 0
            total_records_created = 0

            # Process providers concurrently (with limits)
            max_concurrent = self.schedule_config.get("max_concurrent", 3)
            semaphore = asyncio.Semaphore(max_concurrent)

            async def ingest_provider_with_semaphore(provider):
                async with semaphore:
                    return await self.ingest_from_provider(provider)

            tasks = [ingest_provider_with_semaphore(provider) for provider in providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    ingestion_results.append(
                        {
                            "provider_id": providers[i]["id"],
                            "status": "error",
                            "error_message": str(result),
                        }
                    )
                else:
                    ingestion_results.append(result)
                    if result["status"] == "success":
                        successful_ingestions += 1
                        total_records_created += result["records_created"]

            return {
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "total_providers": total_providers,
                "successful_ingestions": successful_ingestions,
                "failed_ingestions": total_providers - successful_ingestions,
                "total_records_created": total_records_created,
                "results": ingestion_results,
            }

        except Exception as e:
            return {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error_message": str(e),
                "total_providers": 0,
                "successful_ingestions": 0,
                "total_records_created": 0,
            }

    def configure_schedule(self, schedule_config: Dict[str, Any]):
        """
        Configure the ingestion schedule.

        Args:
            schedule_config: Schedule configuration
        """
        self.schedule_config = {
            "interval_minutes": schedule_config.get("interval_minutes", 60),
            "providers": schedule_config.get("providers", []),
            "max_concurrent": schedule_config.get("max_concurrent", 3),
            "retry_failed": schedule_config.get("retry_failed", True),
            "quality_threshold": schedule_config.get("quality_threshold", 0.8),
        }

    def get_ingestion_metrics(self) -> Dict[str, Any]:
        """
        Get ingestion performance metrics.

        Returns:
            Metrics summary
        """
        return self.metrics.get_summary()

    async def validate_provider_config(
        self, provider_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate provider configuration before ingestion.

        Args:
            provider_config: Provider configuration to validate

        Returns:
            Validation result
        """
        errors = []
        warnings = []

        # Check required fields
        required_fields = ["provider_id", "name", "products"]
        for field in required_fields:
            if field not in provider_config:
                errors.append(f"Missing required field: {field}")

        # Validate products
        if "products" in provider_config:
            products = provider_config["products"]
            if not isinstance(products, list) or not products:
                errors.append("Products must be a non-empty list")
            else:
                for i, product in enumerate(products):
                    if "url" not in product:
                        errors.append(f"Product {i}: Missing URL")
                    elif not isinstance(product["url"], str) or not product[
                        "url"
                    ].startswith("http"):
                        errors.append(f"Product {i}: Invalid URL format")

        # Validate selectors
        if "selectors" in provider_config:
            selectors = provider_config["selectors"]
            if not isinstance(selectors, dict):
                errors.append("Selectors must be a dictionary")
            elif not selectors:
                warnings.append("No selectors provided - will use default selectors")

        # Test connectivity (optional)
        connectivity_test = await self._test_provider_connectivity(provider_config)

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "connectivity_test": connectivity_test,
        }

    async def _test_provider_connectivity(
        self, provider_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test connectivity to provider."""
        try:
            # Test first product URL if available
            products = provider_config.get("products", [])
            if products:
                test_url = products[0]["url"]

                # Create a temporary scraper for testing
                scraper = ProductScraper(provider="test")
                try:
                    result = await scraper.scrape_single_product(test_url)
                    await scraper.close()

                    return {
                        "status": "success",
                        "message": "Successfully connected to provider",
                        "test_url": test_url,
                        "response_received": len(str(result)) > 0,
                    }
                except Exception as e:
                    await scraper.close()
                    return {
                        "status": "error",
                        "message": f"Failed to connect: {str(e)}",
                        "test_url": test_url,
                    }
            else:
                return {
                    "status": "skipped",
                    "message": "No products available for connectivity test",
                }

        except Exception as e:
            return {"status": "error", "message": f"Connectivity test failed: {str(e)}"}

    async def run_quality_check(self, provider_id: int) -> Dict[str, Any]:
        """
        Run data quality check for a specific provider.

        Args:
            provider_id: ID of the provider to check

        Returns:
            Quality check results
        """
        try:
            # This would typically fetch recent data for the provider from database
            # For now, simulate with sample data
            sample_data = [
                {
                    "name": "Test Product 1",
                    "price": 99.99,
                    "currency": "USD",
                    "availability": True,
                    "scraped_at": datetime.now().isoformat(),
                },
                {
                    "name": "Test Product 2",
                    "price": 149.99,
                    "currency": "USD",
                    "availability": False,
                    "scraped_at": (datetime.now() - timedelta(hours=2)).isoformat(),
                },
            ]

            quality_report = self.quality_checker.generate_quality_report(sample_data)

            return {
                "provider_id": provider_id,
                "status": "success",
                "quality_report": quality_report,
            }

        except Exception as e:
            return {
                "provider_id": provider_id,
                "status": "error",
                "error_message": str(e),
            }

    async def cleanup_resources(self):
        """Clean up resources and close connections."""
        if self.scraper:
            await self.scraper.close()

        # Clear active ingestions
        self.active_ingestions.clear()
