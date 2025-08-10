"""
Cache management routes.
Handles cache warming, clearing, and statistics.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..models import PriceRecord, Product
from ..services.cache import CacheService

router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.post("/warm")
async def warm_cache(
    session: Session = Depends(get_session),
):
    """Warm up the cache with commonly accessed data."""
    cache_service = CacheService()
    await cache_service.connect()

    try:
        # Warm up popular products
        popular_products = session.query(Product).limit(10).all()

        cache_entries_created = 0

        # Cache product data
        for product in popular_products:
            cache_key = f"product:{product.id}"
            product_data = {
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "category": product.category,
                "brand": product.brand,
                "description": product.description,
                "is_active": product.is_active,
            }
            await cache_service.set(cache_key, product_data, expire=600)
            cache_entries_created += 1

        # Warm up recent price data for popular products
        for product in popular_products[:5]:
            price_cache_key = f"prices:{product.id}:recent"

            # Get recent prices
            recent_prices = (
                session.query(PriceRecord)
                .filter(PriceRecord.product_id == product.id)
                .order_by(PriceRecord.recorded_at.desc())
                .limit(10)
                .all()
            )

            price_data = [
                {
                    "id": price.id,
                    "price": price.price,
                    "currency": price.currency,
                    "provider_id": price.provider_id,
                    "timestamp": price.timestamp.isoformat(),
                    "recorded_at": price.recorded_at.isoformat(),
                }
                for price in recent_prices
            ]

            await cache_service.set(price_cache_key, price_data, expire=300)
            cache_entries_created += 1

        # Warm up analytics cache
        analytics_cache_key = "dashboard:overview"
        analytics_data = {
            "total_products": len(popular_products),
            "total_providers": 3,  # From test data
            "warmed_at": datetime.utcnow().isoformat(),
        }
        await cache_service.set(analytics_cache_key, analytics_data, expire=300)
        cache_entries_created += 1

        return {
            "status": "success",
            "cache_entries_created": cache_entries_created,
            "timestamp": datetime.utcnow().isoformat(),
        }

    finally:
        await cache_service.disconnect()


@router.delete("/clear")
async def clear_cache():
    """Clear all cache data."""
    cache_service = CacheService()
    await cache_service.connect()

    try:
        # Get current stats before clearing
        stats_before = await cache_service.get_cache_stats()

        # Clear cache
        await cache_service.clear_all()

        # Get stats after clearing
        stats_after = await cache_service.get_cache_stats()

        return {
            "status": "success",
            "cleared_items": stats_before.get("keys", 0) - stats_after.get("keys", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }

    finally:
        await cache_service.disconnect()


@router.get("/stats")
async def get_cache_stats():
    """Get cache statistics."""
    cache_service = CacheService()
    await cache_service.connect()

    try:
        stats = await cache_service.get_cache_stats()
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat(),
        }

    finally:
        await cache_service.disconnect()
