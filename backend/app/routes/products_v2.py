"""
Product management routes with advanced filtering and price tracking.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.product_service import ProductService

router = APIRouter()
product_service = ProductService()


class ProductCreateRequest(BaseModel):
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    provider_id: Optional[int] = None
    current_price: Optional[float] = None


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None


class PriceRecordRequest(BaseModel):
    price: float
    provider_id: int


class ProductSearchRequest(BaseModel):
    query: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    has_discount: Optional[bool] = None
    sort_by: Optional[str] = None
    sort_order: Optional[str] = "asc"
    page: int = 1
    page_size: int = 20


@router.get("/")
async def get_products(
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    has_discount: Optional[bool] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
):
    """Get products with filtering and pagination."""
    try:
        products = await product_service.search_products(
            db_session=db,
            category=category,
            brand=brand,
            min_price=min_price,
            max_price=max_price,
            has_discount=has_discount,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_products_advanced(
    request: ProductSearchRequest, db: AsyncSession = Depends(get_db)
):
    """Advanced product search with text query."""
    try:
        products = await product_service.search_products(
            db_session=db,
            query=request.query,
            category=request.category,
            brand=request.brand,
            min_price=request.min_price,
            max_price=request.max_price,
            has_discount=request.has_discount,
            sort_by=request.sort_by,
            sort_order=request.sort_order,
            page=request.page,
            page_size=request.page_size,
        )
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_product(
    request: ProductCreateRequest, db: AsyncSession = Depends(get_db)
):
    """Create a new product."""
    try:
        product = await product_service.create_product(
            db_session=db,
            name=request.name,
            brand=request.brand,
            category=request.category,
            description=request.description,
            url=request.url,
            provider_id=request.provider_id,
            current_price=request.current_price,
        )
        return {"success": True, "product": product}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{product_id}")
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific product by ID."""
    try:
        product = await product_service.get_product_by_id(db, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{product_id}")
async def update_product(
    product_id: int, request: ProductUpdateRequest, db: AsyncSession = Depends(get_db)
):
    """Update a product."""
    try:
        update_data = {k: v for k, v in request.dict().items() if v is not None}
        product = await product_service.update_product(db, product_id, update_data)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"success": True, "product": product}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{product_id}")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Soft delete a product."""
    try:
        success = await product_service.soft_delete_product(db, product_id)
        if not success:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"success": True, "message": "Product deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{product_id}/prices")
async def add_price_record(
    product_id: int, request: PriceRecordRequest, db: AsyncSession = Depends(get_db)
):
    """Add a new price record for a product."""
    try:
        price_record = await product_service.add_price_record(
            db, product_id, request.price, request.provider_id
        )
        return {"success": True, "price_record": price_record}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{product_id}/price-history")
async def get_price_history(
    product_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get price history for a product."""
    try:
        history = await product_service.get_price_history(db, product_id, days)
        return {"product_id": product_id, "price_history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meta/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    """Get all categories with product counts."""
    try:
        categories = await product_service.get_categories_with_counts(db)
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/meta/brands")
async def get_brands(
    category: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)
):
    """Get all brands with product counts, optionally filtered by category."""
    try:
        brands = await product_service.get_brands_with_counts(db, category)
        return {"brands": brands}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
