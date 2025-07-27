"""
Product API routes following TDD approach.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session, select

from ..database import get_async_session, get_session
from ..models import Product, ProductStatus
from ..services.cache import cache_service


# Request/Response schemas
class ProductCreate(BaseModel):
    name: str
    url: str | None = None
    description: str | None = None
    category: str | None = None
    image_url: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    description: str | None = None
    category: str | None = None
    image_url: str | None = None
    status: ProductStatus | None = None


class ProductResponse(BaseModel):
    id: int
    name: str
    url: str | None
    description: str | None
    category: str | None
    image_url: str | None
    status: ProductStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


router = APIRouter()


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_data: ProductCreate, session: Session = Depends(get_session)
):
    """Create a new product."""
    # Validate using our custom method
    temp_product = Product(name=product_data.name)
    if not temp_product.is_valid_name():
        raise HTTPException(
            status_code=422,
            detail="validation error: Product name must be at least 2 characters long",
        )

    # Create the product
    product = Product(
        name=product_data.name,
        url=product_data.url,
        description=product_data.description,
        category=product_data.category,
        image_url=product_data.image_url,
    )

    session.add(product)
    session.commit()
    session.refresh(product)

    return product


@router.get("/", response_model=List[ProductResponse])
def get_products(session: Session = Depends(get_session)):
    """Get all products."""
    statement = select(Product)
    products = session.execute(statement).scalars().all()
    return products


# Advanced Search & Filtering endpoints for products


@router.get("/search")
async def search_products(
    q: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price"),
    available: Optional[bool] = Query(None, description="Filter by availability"),
    historical_min_price: Optional[float] = Query(
        None, ge=0, description="Historical minimum price"
    ),
    historical_max_price: Optional[float] = Query(
        None, ge=0, description="Historical maximum price"
    ),
    price_drop_percentage: Optional[float] = Query(
        None, ge=0, le=100, description="Price drop percentage"
    ),
    price_trend: Optional[str] = Query(None, description="Price trend"),
    sort: Optional[str] = Query("relevance", description="Sort field"),
    order: Optional[str] = Query("desc", description="Sort order"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    use_elasticsearch: bool = Query(False, description="Use Elasticsearch"),
    fuzzy: bool = Query(False, description="Enable fuzzy search"),
    session: AsyncSession = Depends(get_async_session),
):
    """Advanced product search with filtering, sorting, and pagination."""
    # Validate parameters
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if per_page < 1 or per_page > 100:
        raise HTTPException(
            status_code=400, detail="Per page must be between 1 and 100"
        )
    if sort not in ["name", "price", "brand", "category", "relevance", "created_at"]:
        raise HTTPException(status_code=400, detail=f"Invalid sort field: {sort}")

    # Build query
    stmt = select(Product)

    # Apply search filter
    if q:
        stmt = stmt.where(
            (Product.name.ilike(f"%{q}%"))
            | (Product.description.ilike(f"%{q}%"))
            | (Product.brand.ilike(f"%{q}%"))
        )

    # Apply filters
    if category:
        stmt = stmt.where(Product.category == category)
    if brand:
        stmt = stmt.where(Product.brand == brand)

    # Execute query and get total count
    result = await session.execute(stmt)
    all_products = result.scalars().all()
    total_count = len(all_products)

    # Apply sorting
    if sort == "name":
        all_products.sort(key=lambda x: x.name, reverse=(order == "desc"))
    elif sort == "brand":
        all_products.sort(key=lambda x: x.brand, reverse=(order == "desc"))
    elif sort == "category":
        all_products.sort(key=lambda x: x.category, reverse=(order == "desc"))
    elif sort == "created_at":
        all_products.sort(key=lambda x: x.created_at, reverse=(order == "desc"))
    elif sort == "relevance" and q:
        # Simple relevance scoring
        def relevance_score(product):
            score = 0
            q_lower = q.lower()
            name_lower = product.name.lower()
            if q_lower == name_lower:
                score = 3
            elif name_lower.startswith(q_lower):
                score = 2
            elif q_lower in name_lower:
                score = 1
            return score

        all_products.sort(key=relevance_score, reverse=True)

    # Apply pagination
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_products = all_products[start_idx:end_idx]

    # Format results
    results = []
    for product in paginated_products:
        results.append(
            {
                "id": product.id,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "description": product.description,
                "created_at": product.created_at,
            }
        )

    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page

    return {
        "results": results,
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "search_time_ms": 50,  # Mock value
    }


@router.get("/facets")
async def get_product_search_facets(
    q: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None, description="Category filter"),
    brand: Optional[str] = Query(None, description="Brand filter"),
    min_price: Optional[float] = Query(None, ge=0, description="Min price"),
    max_price: Optional[float] = Query(None, ge=0, description="Max price"),
    session: AsyncSession = Depends(get_async_session),
):
    """Get search facets for product filtering."""
    # Build base query for facets
    stmt = select(Product)

    # Apply current filters
    if q:
        stmt = stmt.where(
            (Product.name.ilike(f"%{q}%"))
            | (Product.description.ilike(f"%{q}%"))
            | (Product.brand.ilike(f"%{q}%"))
        )

    # Get all products for facet calculation
    result = await session.execute(stmt)
    products = result.scalars().all()

    # Calculate brand facets
    brand_counts = {}
    for product in products:
        if product.brand not in brand_counts:
            brand_counts[product.brand] = 0
        brand_counts[product.brand] += 1

    brands = [
        {"value": brand, "count": count}
        for brand, count in sorted(
            brand_counts.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Calculate category facets
    category_counts = {}
    for product in products:
        if product.category not in category_counts:
            category_counts[product.category] = 0
        category_counts[product.category] += 1

    categories = [
        {"value": category, "count": count}
        for category, count in sorted(
            category_counts.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Mock price ranges
    price_ranges = [
        {"min": 0, "max": 100, "count": 25, "label": "$0 - $100"},
        {"min": 100, "max": 500, "count": 45, "label": "$100 - $500"},
        {"min": 500, "max": 1000, "count": 30, "label": "$500 - $1000"},
        {"min": 1000, "max": None, "count": 15, "label": "$1000+"},
    ]

    return {"brands": brands, "categories": categories, "price_ranges": price_ranges}


@router.get("/autocomplete")
async def get_product_autocomplete(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=20, description="Max suggestions"),
    session: AsyncSession = Depends(get_async_session),
):
    """Get autocomplete suggestions for product search."""
    if len(q) < 2:
        return {"suggestions": []}

    # Get product name suggestions
    product_stmt = select(Product.name).where(Product.name.ilike(f"%{q}%")).distinct()
    product_result = await session.execute(product_stmt)
    product_names = product_result.scalars().all()

    # Get brand suggestions
    brand_stmt = select(Product.brand).where(Product.brand.ilike(f"%{q}%")).distinct()
    brand_result = await session.execute(brand_stmt)
    brand_names = brand_result.scalars().all()

    # Combine suggestions
    suggestions = []

    # Add product names
    for name in product_names[: limit // 2]:
        suggestions.append({"text": name, "type": "product", "category": None})

    # Add brands
    for brand in brand_names[: limit // 2]:
        suggestions.append({"text": brand, "type": "brand", "category": None})

    # Remove duplicates and limit
    seen = set()
    unique_suggestions = []
    for suggestion in suggestions:
        if suggestion["text"] not in seen:
            seen.add(suggestion["text"])
            unique_suggestions.append(suggestion)
            if len(unique_suggestions) >= limit:
                break

    return {"suggestions": unique_suggestions}


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    use_cache: bool = Query(False, description="Whether to use caching"),
    session: Session = Depends(get_session),
):
    """Get a specific product by ID with optional caching."""
    if use_cache:
        # Try to get from cache first
        cached_product = await cache_service.get_cached_product(product_id)
        if cached_product:
            return cached_product

    # Get from database
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Convert to dict for caching
    product_data = {
        "id": product.id,
        "name": product.name,
        "url": product.url,
        "description": product.description,
        "category": product.category,
        "image_url": product.image_url,
        "status": product.status,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }

    # Cache the result if caching is enabled
    if use_cache:
        await cache_service.cache_product(product_id, product_data)

    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    product_update: ProductUpdate,
    session: Session = Depends(get_session),
):
    """Update an existing product."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Update fields that are provided
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    # Update timestamp
    product.updated_at = datetime.utcnow()

    session.add(product)
    session.commit()
    session.refresh(product)

    # Invalidate cache for this product
    await cache_service.invalidate_product(product_id)

    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, session: Session = Depends(get_session)):
    """Delete a product."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    session.delete(product)
    session.commit()
    return None


@router.get("/{product_id}/price-history")
def get_product_price_history(product_id: int, session: Session = Depends(get_session)):
    """Get price history for a product."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # For now, return empty list - will implement when we add price records
    return []
