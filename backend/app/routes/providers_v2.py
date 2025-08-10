"""
Enhanced Provider API Routes with Scraping Integration
======================================================

This module provides comprehensive provider management endpoints with web scraping capabilities.
Supports provider configuration, scraping automation, and performance monitoring.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_db
from app.services.provider_service import ProviderService


router = APIRouter()
provider_service = ProviderService()


# Request/Response Models
class ProviderCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    base_url: str = Field(..., max_length=2048)
    api_key: Optional[str] = Field(None, max_length=255)
    rate_limit: int = Field(100, ge=1, le=10000)
    scraping_config: Optional[dict] = None


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    base_url: Optional[str] = Field(None, max_length=2048)
    api_key: Optional[str] = Field(None, max_length=255)
    rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    is_active: Optional[bool] = None
    health_status: Optional[str] = Field(None, max_length=20)


class ProductProviderLinkRequest(BaseModel):
    product_id: int
    provider_id: int
    source_url: str = Field(..., max_length=2048)
    initial_price: Optional[float] = Field(None, ge=0)


class ScrapingRequest(BaseModel):
    provider_id: int
    product_urls: List[str] = Field(..., max_items=50)
    max_concurrent: Optional[int] = Field(None, ge=1, le=10)
    create_price_records: bool = True


class ProviderPerformanceResponse(BaseModel):
    provider_id: int
    provider_name: str
    health_status: str
    active_product_links: int
    price_records_last_30_days: int
    success_rate_percentage: float
    average_requests_per_day: float
    is_healthy: bool


class ScrapingResultResponse(BaseModel):
    provider_id: int
    provider_name: str
    products_updated: int
    price_changes: List[dict]
    errors: List[dict]
    summary: str


@router.post("/")
async def create_provider(
    request: ProviderCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new provider with scraping configuration."""
    try:
        provider = await provider_service.create_provider(
            db_session=db,
            name=request.name,
            base_url=request.base_url,
            scraping_config=request.scraping_config,
            rate_limit=request.rate_limit,
            api_key=request.api_key
        )
        return {"success": True, "provider": provider}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def get_providers(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """Get all providers, optionally filtered by active status."""
    try:
        if active_only:
            providers = await provider_service.get_active_providers(db)
        else:
            # For now, just return active providers
            # In real implementation, would have get_all_providers method
            providers = await provider_service.get_active_providers(db)
        
        return {"providers": providers, "count": len(providers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider_id}")
async def get_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific provider by ID."""
    try:
        provider = await provider_service.get_provider_by_id(db, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        return {"provider": provider}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{provider_id}/health")
async def update_provider_health(
    provider_id: int,
    health_status: str = Query(..., max_length=20),
    db: AsyncSession = Depends(get_db)
):
    """Update provider health status."""
    try:
        success = await provider_service.update_provider_health(
            db, provider_id, health_status
        )
        if not success:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        return {"success": True, "provider_id": provider_id, "health_status": health_status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider_id}/scrape")
async def scrape_products(
    provider_id: int,
    request: ScrapingRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Scrape products from a provider."""
    try:
        # Validate provider exists
        provider = await provider_service.get_provider_by_id(db, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        # For immediate response, use background task for large scraping jobs
        if len(request.product_urls) > 10:
            background_tasks.add_task(
                _background_scrape_task,
                db, provider_id, request.product_urls, request.max_concurrent
            )
            return {
                "success": True,
                "message": f"Started background scraping for {len(request.product_urls)} products",
                "provider_id": provider_id
            }
        else:
            # For small jobs, do immediately
            results = await provider_service.scrape_multiple_products(
                db, provider_id, request.product_urls, request.max_concurrent
            )
            return {
                "success": True,
                "results": results,
                "provider_id": provider_id,
                "products_scraped": len(results)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider_id}/update-prices", response_model=ScrapingResultResponse)
async def update_provider_prices(
    provider_id: int,
    background_tasks: BackgroundTasks,
    create_records: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """Update all prices for products linked to a provider."""
    try:
        # For large updates, use background task
        background_tasks.add_task(
            _background_price_update_task, db, provider_id, create_records
        )
        
        return ScrapingResultResponse(
            provider_id=provider_id,
            provider_name="Processing...",
            products_updated=0,
            price_changes=[],
            errors=[],
            summary=f"Started background price update for provider {provider_id}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/links")
async def create_product_provider_link(
    request: ProductProviderLinkRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a link between a product and provider."""
    try:
        link = await provider_service.link_product_to_provider(
            db_session=db,
            product_id=request.product_id,
            provider_id=request.provider_id,
            source_url=request.source_url,
            price=request.initial_price
        )
        return {"success": True, "link": link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider_id}/performance", response_model=ProviderPerformanceResponse)
async def get_provider_performance(
    provider_id: int,
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db)
):
    """Get provider performance metrics."""
    try:
        performance = await provider_service.get_provider_performance(
            db, provider_id, days
        )
        return ProviderPerformanceResponse(**performance)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider_id}/test")
async def test_provider_scraping(
    provider_id: int,
    test_url: str = Query(..., max_length=2048),
    db: AsyncSession = Depends(get_db)
):
    """Test scraping configuration for a provider."""
    try:
        provider = await provider_service.get_provider_by_id(db, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        # Scrape test URL
        result = await provider_service.scrape_product_from_provider(
            provider, test_url
        )
        
        return {
            "success": True,
            "provider_id": provider_id,
            "test_url": test_url,
            "result": result,
            "has_errors": "error" in result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs/available")
async def get_available_scraping_configs():
    """Get list of available pre-configured scraping configurations."""
    configs = {
        "amazon": {
            "name": "Amazon",
            "supported_features": ["price", "title", "availability", "description", "brand", "rating"],
            "rate_limit": 2.0,
            "javascript_required": False
        },
        "walmart": {
            "name": "Walmart",
            "supported_features": ["price", "title", "availability", "description", "brand"],
            "rate_limit": 1.5,
            "javascript_required": False
        },
        "target": {
            "name": "Target",
            "supported_features": ["price", "title", "availability", "description", "brand"],
            "rate_limit": 1.0,
            "javascript_required": True
        },
        "bestbuy": {
            "name": "Best Buy",
            "supported_features": ["price", "title", "availability", "description", "brand", "rating"],
            "rate_limit": 2.5,
            "javascript_required": True
        }
    }
    
    return {"available_configs": configs}


# Background task functions
async def _background_scrape_task(
    db: AsyncSession,
    provider_id: int,
    product_urls: List[str],
    max_concurrent: Optional[int]
):
    """Background task for large scraping operations."""
    try:
        results = await provider_service.scrape_multiple_products(
            db, provider_id, product_urls, max_concurrent
        )
        print(f"Background scraping completed: {len(results)} products processed")
    except Exception as e:
        print(f"Background scraping error: {e}")


async def _background_price_update_task(
    db: AsyncSession,
    provider_id: int,
    create_records: bool
):
    """Background task for price updates."""
    try:
        result = await provider_service.update_prices_from_provider(
            db, provider_id, create_records
        )
        print(f"Background price update completed: {result['summary']}")
    except Exception as e:
        print(f"Background price update error: {e}")


# Cleanup on shutdown
@router.on_event("shutdown")
async def shutdown_provider_service():
    """Clean up provider service resources."""
    await provider_service.close()
