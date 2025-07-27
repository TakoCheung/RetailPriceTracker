"""
ETL (Extract, Transform, Load) pipeline for data ingestion.
Handles data extraction from various sources, transformation, and loading into database.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List

from app.exceptions import ETLError
from app.services.parser import DataEnricher, DataValidator, PriceParser
from app.services.scraper import ProductScraper


class DataTransformer:
    """Service for transforming raw scraped data."""

    def __init__(self):
        self.parser = PriceParser()
        self.enricher = DataEnricher()
        self.transformation_rules = {
            "normalize_text": True,
            "extract_brand": True,
            "categorize_products": True,
            "standardize_currency": True,
        }

    def normalize_text(self, text: str) -> str:
        """Normalize text data."""
        if not text or not isinstance(text, str):
            return ""

        # Remove extra whitespace and normalize
        text = " ".join(text.split())

        # Convert to title case for names
        if len(text) > 3:  # Avoid converting short codes
            text = text.title()

        return text

    def map_currency_symbol(self, symbol: str) -> str:
        """Map currency symbol to currency code."""
        symbol_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
        return symbol_map.get(symbol, "USD")

    def clean_price_text(self, price_text: str) -> float:
        """Clean and extract price from text."""
        if not price_text:
            return 0.0

        # Use the parser to extract price
        try:
            price_info = self.parser.parse_price(price_text)
            return price_info["amount"]
        except Exception:
            return 0.0

    def enrich_product_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich product data with computed fields."""
        return self.enricher.enrich_product_data(data)

    async def transform_single_item(self, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single raw data item."""
        try:
            # Parse basic product details
            parsed_data = self.parser.extract_product_details(raw_item)

            # Apply transformations
            if self.transformation_rules.get("normalize_text"):
                if "name" in parsed_data:
                    parsed_data["name"] = self.normalize_text(parsed_data["name"])
                if "description" in parsed_data:
                    parsed_data["description"] = self.normalize_text(
                        parsed_data["description"]
                    )

            # Enrich with computed fields
            if self.transformation_rules.get(
                "extract_brand"
            ) or self.transformation_rules.get("categorize_products"):
                parsed_data = self.enrich_product_data(parsed_data)

            return parsed_data

        except Exception as e:
            raise ETLError(f"Error transforming item: {str(e)}", "transform")

    async def transform_batch(
        self, raw_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Transform a batch of raw data items."""
        transformed_items = []

        for raw_item in raw_data:
            try:
                transformed_item = await self.transform_single_item(raw_item)
                transformed_items.append(transformed_item)
            except ETLError:
                # Log error but continue with other items
                continue

        return transformed_items


class ETLPipeline:
    """Main ETL pipeline orchestrator."""

    def __init__(self):
        self.extractors = {}
        self.transformers = DataTransformer()
        self.loaders = {}
        self.validator = DataValidator()

    async def extract_data(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract data from configured source.

        Args:
            source_config: Configuration for data source

        Returns:
            List of extracted raw data items
        """
        source_type = source_config.get("type")

        if source_type == "web_scraper":
            return await self._extract_from_scraper(source_config)
        elif source_type == "api":
            return await self._extract_from_api(source_config)
        elif source_type == "file":
            return await self._extract_from_file(source_config)
        else:
            raise ETLError(f"Unsupported source type: {source_type}", "extract")

    async def _extract_from_scraper(
        self, config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract data using web scraping."""
        try:
            provider = config.get("provider", "generic")
            urls = config.get("urls", [])
            selectors = config.get("selectors", {})

            scraper = ProductScraper(provider=provider, selectors=selectors)

            results = await scraper.scrape_multiple_products(urls)
            await scraper.close()

            return results

        except Exception as e:
            raise ETLError(f"Scraping extraction failed: {str(e)}", "extract")

    async def _extract_from_api(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract data from API endpoint."""
        # Placeholder for API extraction
        # In a real implementation, this would make HTTP requests to APIs
        return []

    async def _extract_from_file(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract data from file source."""
        # Placeholder for file extraction (CSV, JSON, etc.)
        return []

    async def transform_data(
        self, raw_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Transform raw extracted data.

        Args:
            raw_data: List of raw data items

        Returns:
            List of transformed data items
        """
        try:
            return await self.transformers.transform_batch(raw_data)
        except Exception as e:
            raise ETLError(f"Transformation failed: {str(e)}", "transform")

    async def load_data(self, processed_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Load processed data into target storage.

        Args:
            processed_data: List of processed data items

        Returns:
            Summary of load operation
        """
        try:
            return await self._save_to_database(processed_data)
        except Exception as e:
            raise ETLError(f"Loading failed: {str(e)}", "load")

    async def _save_to_database(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save data to database."""
        # Placeholder for database operations
        # In a real implementation, this would use SQLAlchemy or similar

        # Validate data before saving
        validation_result = self.validator.validate_batch_data(data)

        if validation_result["validation_rate"] < 0.8:  # 80% threshold
            raise ETLError(
                f"Data quality too low: {validation_result['validation_rate']:.2%}",
                "load",
            )

        # Simulate database save
        created_count = validation_result["valid_items"]
        updated_count = 0
        error_count = validation_result["invalid_items"]

        return {
            "created": created_count,
            "updated": updated_count,
            "errors": error_count,
            "total_processed": len(data),
        }

    async def run(self, source_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run complete ETL pipeline.

        Args:
            source_config: Configuration for data source

        Returns:
            Summary of pipeline execution
        """
        start_time = datetime.now()

        try:
            # Extract
            raw_data = await self.extract_data(source_config)

            # Transform
            processed_data = await self.transform_data(raw_data)

            # Load
            load_result = await self.load_data(processed_data)

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            return {
                "status": "success",
                "execution_time_seconds": execution_time,
                "records_extracted": len(raw_data),
                "records_processed": len(processed_data),
                "created": load_result["created"],
                "updated": load_result["updated"],
                "errors": load_result["errors"],
            }

        except ETLError as e:
            return {
                "status": "error",
                "error_message": str(e),
                "error_stage": e.stage,
                "execution_time_seconds": (datetime.now() - start_time).total_seconds(),
            }


class BatchETLProcessor:
    """Processor for handling batch ETL operations."""

    def __init__(self):
        self.pipeline = ETLPipeline()
        self.max_concurrent = 5
        self.batch_size = 100

    async def process_multiple_sources(
        self, source_configs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process multiple data sources concurrently.

        Args:
            source_configs: List of source configurations

        Returns:
            List of pipeline execution results
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_with_semaphore(config: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await self.pipeline.run(config)

        tasks = [process_with_semaphore(config) for config in source_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    {"status": "error", "error_message": str(result), "source_index": i}
                )
            else:
                processed_results.append(result)

        return processed_results

    async def process_large_dataset(
        self, source_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process large datasets in batches.

        Args:
            source_config: Source configuration for large dataset

        Returns:
            Aggregated processing results
        """
        total_processed = 0
        total_created = 0
        total_errors = 0
        batch_results = []

        try:
            # Extract all data first
            raw_data = await self.pipeline.extract_data(source_config)

            # Process in batches
            for i in range(0, len(raw_data), self.batch_size):
                batch = raw_data[i : i + self.batch_size]

                # Process batch
                processed_batch = await self.pipeline.transform_data(batch)
                load_result = await self.pipeline.load_data(processed_batch)

                # Accumulate results
                total_processed += len(processed_batch)
                total_created += load_result["created"]
                total_errors += load_result["errors"]

                batch_results.append(
                    {
                        "batch_index": i // self.batch_size,
                        "records_in_batch": len(batch),
                        "records_processed": len(processed_batch),
                        "created": load_result["created"],
                        "errors": load_result["errors"],
                    }
                )

            return {
                "status": "success",
                "total_records": len(raw_data),
                "total_processed": total_processed,
                "total_created": total_created,
                "total_errors": total_errors,
                "batches_processed": len(batch_results),
                "batch_results": batch_results,
            }

        except Exception as e:
            return {
                "status": "error",
                "error_message": str(e),
                "total_processed": total_processed,
                "total_created": total_created,
                "total_errors": total_errors,
            }
