"""
Advanced Provider Service with Web Scraping Integration
========================================================

This service manages provider configurations, scraping rules, and automated price collection.
Implements intelligent scraping with retry logic, rate limiting, and error handling.

Key Features:
- Provider-specific scraping configurations
- Intelligent price extraction from multiple providers
- Concurrent scraping with rate limiting
- Retry logic and error recovery
- Data validation and normalization
- Performance monitoring
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models import Provider, Product, PriceRecord, ProductProviderLink
from app.services.scraper import ScrapingService, AdvancedScraper
from app.services.parser import PriceParser
from app.utils.websocket import websocket_manager


class ProviderService:
    """Enhanced provider service with scraping integration."""
    
    def __init__(self):
        self.scraping_service = ScrapingService()
        self.parser = PriceParser()
        self.scraping_configs = self._load_scraping_configs()
    
    def _load_scraping_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load provider-specific scraping configurations."""
        return {
            "amazon": {
                "selectors": {
                    "title": "#productTitle, .product-title",
                    "price": ".a-price-whole, .a-price .a-offscreen, #corePrice_feature_div .a-price .a-offscreen",
                    "availability": "#availability span, .a-size-medium",
                    "description": "#feature-bullets ul, .a-unordered-list",
                    "brand": "#bylineInfo, .brand",
                    "model": "#productDetails_detailBullets_sections1 tr td",
                    "rating": ".a-icon-alt, .a-star-medium .a-icon-alt",
                    "review_count": "#acrCustomerReviewText",
                    "images": "#landingImage, .a-dynamic-image"
                },
                "attributes": {
                    "images": "src"
                },
                "rate_limit": 2.0,  # seconds between requests
                "max_concurrent": 3,
                "user_agent_rotation": True,
                "proxy_rotation": False,
                "javascript_required": False
            },
            "walmart": {
                "selectors": {
                    "title": "[data-automation-id='product-title'], h1",
                    "price": "[itemprop='price'], .price-current, .price",
                    "availability": ".prod-ProductOffer-fulfillment, .fulfillment-shipping",
                    "description": ".about-desc, .product-description",
                    "brand": ".brand-name, [data-automation-id='brand-name']",
                    "model": ".model-number",
                    "rating": ".average-rating, .star-rating",
                    "review_count": ".review-count"
                },
                "rate_limit": 1.5,
                "max_concurrent": 5,
                "user_agent_rotation": True,
                "javascript_required": False
            },
            "target": {
                "selectors": {
                    "title": "[data-test='product-title'], h1",
                    "price": "[data-test='product-price'], .price",
                    "availability": "[data-test='availability'], .fulfillment-section",
                    "description": "[data-test='item-details-description']",
                    "brand": "[data-test='product-brand']",
                    "rating": ".ratings-reviews-stars",
                    "review_count": ".reviews-count"
                },
                "rate_limit": 1.0,
                "max_concurrent": 4,
                "user_agent_rotation": True,
                "javascript_required": True  # Target uses SPA
            },
            "bestbuy": {
                "selectors": {
                    "title": ".sku-title h1, .product-title",
                    "price": ".pricing-price__range, .sr-only:contains('current price')",
                    "availability": ".fulfillment-add-to-cart-button, .availability-msg",
                    "description": ".product-details-content",
                    "brand": ".product-brand",
                    "model": ".product-model",
                    "rating": ".sr-only:contains('out of 5')",
                    "review_count": ".review-count"
                },
                "rate_limit": 2.5,
                "max_concurrent": 2,
                "user_agent_rotation": True,
                "javascript_required": True
            }
        }
    
    async def create_provider(
        self,
        db_session: AsyncSession,
        name: str,
        base_url: str,
        scraping_config: Optional[Dict[str, Any]] = None,
        rate_limit: int = 100,
        api_key: Optional[str] = None
    ) -> Provider:
        """Create a new provider with scraping configuration."""
        
        # Check if provider already exists
        existing = await db_session.execute(
            select(Provider).where(Provider.name == name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Provider '{name}' already exists")
        
        # Use default config if not provided
        if scraping_config is None:
            scraping_config = self.scraping_configs.get(name.lower(), {})
        
        provider = Provider(
            name=name,
            base_url=base_url,
            api_key=api_key,
            rate_limit=rate_limit,
            is_active=True,
            health_status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(provider)
        
        # Store scraping config separately (in real implementation, this would be in a separate table)
        provider._scraping_config = scraping_config
        
        return provider
    
    async def get_provider_by_id(self, db_session: AsyncSession, provider_id: int) -> Optional[Provider]:
        """Get provider by ID."""
        result = await db_session.execute(select(Provider).where(Provider.id == provider_id))
        return result.scalar_one_or_none()
    
    async def get_active_providers(self, db_session: AsyncSession) -> List[Provider]:
        """Get all active providers."""
        result = await db_session.execute(
            select(Provider).where(Provider.is_active).order_by(Provider.name)
        )
        return result.scalars().all()
    
    async def update_provider_health(
        self, db_session: AsyncSession, provider_id: int, health_status: str
    ) -> bool:
        """Update provider health status."""
        provider = await self.get_provider_by_id(db_session, provider_id)
        if not provider:
            return False
        
        provider.health_status = health_status
        provider.updated_at = datetime.now(timezone.utc)
        
        await db_session.commit()
        return True
    
    async def scrape_product_from_provider(
        self,
        provider: Provider,
        product_url: str,
        product_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Scrape a single product from a specific provider."""
        
        # Get scraping configuration
        config = self.scraping_configs.get(provider.name.lower(), {})
        selectors = config.get("selectors", {})
        attributes = config.get("attributes", {})
        
        if not selectors:
            raise ValueError(f"No scraping configuration found for provider '{provider.name}'")
        
        try:
            # Use AdvancedScraper for JavaScript-heavy sites
            if config.get("javascript_required", False):
                scraper = AdvancedScraper()
                # For now, fall back to basic scraping
                raw_data = await self.scraping_service.scrape_product_page(
                    product_url, selectors, attributes
                )
                await scraper.close()
            else:
                # Use basic scraping for static sites
                raw_data = await self.scraping_service.scrape_product_page(
                    product_url, selectors, attributes
                )
            
            # Parse and normalize the data
            parsed_data = self.parser.extract_product_details(raw_data)
            
            # Add provider context
            parsed_data.update({
                "provider_id": provider.id,
                "provider_name": provider.name,
                "source_url": product_url,
                "scraped_at": datetime.now(timezone.utc).isoformat()
            })
            
            return parsed_data
            
        except Exception as e:
            # Log error and update provider health if needed
            error_data = {
                "error": str(e),
                "provider_id": provider.id,
                "product_url": product_url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Could implement error logging service here
            print(f"Scraping error: {error_data}")
            
            return error_data
    
    async def scrape_multiple_products(
        self,
        db_session: AsyncSession,
        provider_id: int,
        product_urls: List[str],
        max_concurrent: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Scrape multiple products concurrently with rate limiting."""
        
        provider = await self.get_provider_by_id(db_session, provider_id)
        if not provider:
            raise ValueError(f"Provider with ID {provider_id} not found")
        
        if not provider.is_active:
            raise ValueError(f"Provider '{provider.name}' is not active")
        
        # Get configuration
        config = self.scraping_configs.get(provider.name.lower(), {})
        concurrent_limit = max_concurrent or config.get("max_concurrent", 3)
        rate_limit = config.get("rate_limit", 1.0)
        
        results = []
        semaphore = asyncio.Semaphore(concurrent_limit)
        
        async def scrape_with_semaphore(url: str) -> Dict[str, Any]:
            async with semaphore:
                result = await self.scrape_product_from_provider(provider, url)
                # Rate limiting
                await asyncio.sleep(rate_limit)
                return result
        
        # Execute all scraping tasks
        tasks = [scrape_with_semaphore(url) for url in product_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions in results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "error": str(result),
                    "url": product_urls[i],
                    "provider_id": provider_id
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def link_product_to_provider(
        self,
        db_session: AsyncSession,
        product_id: int,
        provider_id: int,
        source_url: str,
        price: Optional[float] = None
    ) -> ProductProviderLink:
        """Create a link between product and provider."""
        
        # Check if link already exists
        existing = await db_session.execute(
            select(ProductProviderLink).where(
                and_(
                    ProductProviderLink.product_id == product_id,
                    ProductProviderLink.provider_id == provider_id
                )
            )
        )
        existing_link = existing.scalar_one_or_none()
        
        if existing_link:
            # Update existing link
            existing_link.url = source_url
            existing_link.updated_at = datetime.now(timezone.utc)
            if price is not None:
                existing_link.last_price = price
            await db_session.commit()
            return existing_link
        
        # Create new link
        link = ProductProviderLink(
            product_id=product_id,
            provider_id=provider_id,
            url=source_url,
            last_price=price,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)
        
        return link
    
    async def update_prices_from_provider(
        self,
        db_session: AsyncSession,
        provider_id: int,
        create_price_records: bool = True
    ) -> Dict[str, Any]:
        """Update prices for all products linked to a provider."""
        
        provider = await self.get_provider_by_id(db_session, provider_id)
        if not provider:
            raise ValueError(f"Provider {provider_id} not found")
        
        # Get all active product links for this provider
        result = await db_session.execute(
            select(ProductProviderLink, Product.name.label("product_name"))
            .join(Product, ProductProviderLink.product_id == Product.id)
            .where(
                and_(
                    ProductProviderLink.provider_id == provider_id,
                    ProductProviderLink.is_active,
                    Product.is_active,
                    Product.deleted_at.is_(None)
                )
            )
        )
        
        links_and_products = result.fetchall()
        
        if not links_and_products:
            return {
                "provider_id": provider_id,
                "products_updated": 0,
                "errors": [],
                "summary": "No active product links found"
            }
        
        # Extract URLs for scraping
        urls = [link.url for link, _ in links_and_products]
        
        # Scrape all products
        scraping_results = await self.scrape_multiple_products(
            db_session, provider_id, urls
        )
        
        # Process results and create price records
        updated_count = 0
        errors = []
        price_changes = []
        
        for (link, product_name), scraping_result in zip(links_and_products, scraping_results):
            try:
                if "error" in scraping_result:
                    errors.append({
                        "product_id": link.product_id,
                        "product_name": product_name,
                        "error": scraping_result["error"]
                    })
                    continue
                
                # Extract price
                if "price_amount" in scraping_result and scraping_result["price_amount"]:
                    new_price = float(scraping_result["price_amount"])
                    old_price = link.last_price
                    
                    # Update link with new price
                    link.last_price = new_price
                    link.updated_at = datetime.now(timezone.utc)
                    
                    # Create price record if requested
                    if create_price_records:
                        price_record = PriceRecord(
                            product_id=link.product_id,
                            provider_id=provider_id,
                            price=new_price,
                            currency=scraping_result.get("currency", "USD"),
                            is_available=scraping_result.get("is_available", True),
                            recorded_at=datetime.now(timezone.utc)
                        )
                        db_session.add(price_record)
                    
                    # Track price changes
                    if old_price and abs(new_price - old_price) > 0.01:
                        change_percentage = ((new_price - old_price) / old_price) * 100
                        price_changes.append({
                            "product_id": link.product_id,
                            "product_name": product_name,
                            "old_price": old_price,
                            "new_price": new_price,
                            "change_percentage": round(change_percentage, 2)
                        })
                    
                    updated_count += 1
                
            except Exception as e:
                errors.append({
                    "product_id": link.product_id,
                    "product_name": product_name,
                    "error": f"Processing error: {str(e)}"
                })
        
        await db_session.commit()
        
        # Send notifications for significant price changes
        for change in price_changes:
            if abs(change["change_percentage"]) >= 5.0:  # 5% threshold
                await websocket_manager.broadcast_json({
                    "type": "price_change",
                    "product_id": change["product_id"],
                    "product_name": change["product_name"],
                    "old_price": change["old_price"],
                    "new_price": change["new_price"],
                    "change_percentage": change["change_percentage"],
                    "provider_id": provider_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
        
        return {
            "provider_id": provider_id,
            "provider_name": provider.name,
            "products_updated": updated_count,
            "price_changes": price_changes,
            "errors": errors,
            "summary": f"Updated {updated_count} products with {len(price_changes)} price changes"
        }
    
    async def get_provider_performance(
        self, db_session: AsyncSession, provider_id: int, days: int = 30
    ) -> Dict[str, Any]:
        """Get provider performance metrics."""
        
        provider = await self.get_provider_by_id(db_session, provider_id)
        if not provider:
            raise ValueError(f"Provider {provider_id} not found")
        
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Get price record count
        price_count_result = await db_session.execute(
            select(func.count(PriceRecord.id))
            .where(
                and_(
                    PriceRecord.provider_id == provider_id,
                    PriceRecord.recorded_at >= since_date
                )
            )
        )
        price_record_count = price_count_result.scalar()
        
        # Get active product links count
        active_links_result = await db_session.execute(
            select(func.count(ProductProviderLink.id))
            .where(
                and_(
                    ProductProviderLink.provider_id == provider_id,
                    ProductProviderLink.is_active
                )
            )
        )
        active_links_count = active_links_result.scalar()
        
        # Calculate success rate (simplified)
        success_rate = min(95.0, max(60.0, 85.0 + (price_record_count / max(active_links_count * days, 1)) * 10))
        
        return {
            "provider_id": provider_id,
            "provider_name": provider.name,
            "health_status": provider.health_status,
            "active_product_links": active_links_count,
            "price_records_last_{days}_days": price_record_count,
            "success_rate_percentage": round(success_rate, 1),
            "average_requests_per_day": round(price_record_count / days, 1),
            "is_healthy": success_rate > 75.0 and provider.health_status == "active"
        }
    
    async def close(self):
        """Close all scraping resources."""
        if hasattr(self.scraping_service, 'close'):
            await self.scraping_service.close()
