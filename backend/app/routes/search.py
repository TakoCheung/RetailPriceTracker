"""
Advanced Search & Filtering API routes.
Provides comprehensive search capabilities for products with full-text search,
filtering, sorting, faceted search, and search analytics.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import PriceRecord, Product, Provider
from app.schemas.search import (
    AvailabilityFacet,
    CategoryFacet,
    ExportedProduct,
    PopularQuery,
    PriceRangeFacet,
    SavedSearchCreate,
    SavedSearchResponse,
    SavedSearchUpdate,
    SearchAnalyticsResponse,
    SearchExportResponse,
    SearchFacetsResponse,
    SearchProductResult,
    SearchProductsResponse,
    SearchSuggestionsResponse,
    SearchVolumeMetric,
    TopSearchCategory,
)

router = APIRouter()


def calculate_search_time(start_time: float) -> int:
    """Calculate search execution time in milliseconds."""
    return int((time.time() - start_time) * 1000)


def build_search_query(
    session: Session,
    query: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    available_only: Optional[bool] = None,
):
    """Build SQLAlchemy query for product search with filters."""
    # Start with a simple product query
    base_query = session.query(Product)

    conditions = []

    # Text search across name and description
    if query:
        search_conditions = [
            Product.name.ilike(f"%{query}%"),
            Product.description.ilike(f"%{query}%"),
        ]
        conditions.append(or_(*search_conditions))

    # Category filter
    if category:
        conditions.append(Product.category == category)

    # Apply product-level conditions
    if conditions:
        base_query = base_query.filter(and_(*conditions))

    # If we need price or availability filters, we need to join with price records
    if min_price is not None or max_price is not None or available_only is not None:
        # Subquery to get latest price record for each product
        latest_price_subq = (
            session.query(
                PriceRecord.product_id,
                func.max(PriceRecord.recorded_at).label("max_recorded_at"),
            )
            .group_by(PriceRecord.product_id)
            .subquery()
        )

        # Join with the latest price records
        base_query = base_query.join(
            PriceRecord, Product.id == PriceRecord.product_id
        ).join(
            latest_price_subq,
            and_(
                PriceRecord.product_id == latest_price_subq.c.product_id,
                PriceRecord.recorded_at == latest_price_subq.c.max_recorded_at,
            ),
        )

        # Add price filters
        if min_price is not None:
            base_query = base_query.filter(PriceRecord.price >= min_price)

        if max_price is not None:
            base_query = base_query.filter(PriceRecord.price <= max_price)

        # Availability filter
        if available_only:
            base_query = base_query.filter(PriceRecord.is_available)

    return base_query


def apply_sorting(
    query,
    sort_by: str,
    sort_order: str,
    session: Session,
    has_price_joins: bool = False,
):
    """Apply sorting to the query based on sort parameters."""
    if not sort_by:
        return query

    if sort_order not in ["asc", "desc"]:
        raise HTTPException(
            status_code=422, detail="Invalid sort order. Must be 'asc' or 'desc'"
        )

    if sort_by == "name":
        order_field = Product.name
    elif sort_by == "price":
        # Only add price joins if they don't already exist
        if not has_price_joins:
            # Create a subquery for latest price records
            latest_price_subq = (
                session.query(
                    PriceRecord.product_id,
                    func.max(PriceRecord.recorded_at).label("max_recorded_at"),
                )
                .group_by(PriceRecord.product_id)
                .subquery()
            )

            # Join with latest price records for sorting
            query = query.join(PriceRecord, Product.id == PriceRecord.product_id).join(
                latest_price_subq,
                and_(
                    PriceRecord.product_id == latest_price_subq.c.product_id,
                    PriceRecord.recorded_at == latest_price_subq.c.max_recorded_at,
                ),
            )
        order_field = PriceRecord.price
    elif sort_by == "category":
        order_field = Product.category
    elif sort_by == "date":
        order_field = Product.created_at
    elif sort_by == "relevance":
        # For relevance, we'll use a simple name match for now
        order_field = Product.name
    else:
        raise HTTPException(status_code=422, detail="Invalid sort field")

    if sort_order == "desc":
        return query.order_by(order_field.desc())
    else:
        return query.order_by(order_field.asc())


def build_product_result(
    product: Product, price_record: Optional[PriceRecord], provider: Optional[Provider]
) -> SearchProductResult:
    """Build search result from product and related data."""
    return SearchProductResult(
        id=product.id,
        name=product.name,
        description=product.description,
        category=product.category,
        url=product.url,
        current_price=price_record.price if price_record else None,
        currency=price_record.currency if price_record else None,
        is_available=price_record.is_available if price_record else False,
        provider_name=provider.name if provider else None,
        score=1.0,  # Simple relevance score for now
    )


@router.get("/products", response_model=SearchProductsResponse)
async def search_products(
    query: Optional[str] = Query(
        None, description="Search query for product name or description"
    ),
    category: Optional[str] = Query(None, description="Filter by product category"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    available_only: Optional[bool] = Query(
        None, description="Filter to available products only"
    ),
    sort_by: Optional[str] = Query(
        "name",
        pattern="^(name|price|category|relevance|date)$",
        description="Sort field",
    ),
    sort_order: Optional[str] = Query(
        "asc", pattern="^(asc|desc)$", description="Sort order"
    ),
    limit: int = Query(20, ge=1, le=100, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
):
    """
    Search products with advanced filtering and sorting capabilities.

    - **query**: Search across product names and descriptions
    - **category**: Filter by specific category
    - **min_price/max_price**: Price range filtering
    - **available_only**: Show only available products
    - **sort_by**: Sort by name, price, category, relevance, or date
    - **sort_order**: Sort ascending or descending
    """
    start_time = time.time()

    # Validate price range
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=422, detail="min_price must be less than or equal to max_price"
        )

    try:
        # Build search query
        search_query = build_search_query(
            session, query, category, min_price, max_price, available_only
        )

        # Check if we already have price joins from filtering
        has_price_joins = (
            min_price is not None or max_price is not None or available_only is not None
        )

        # Get total count before pagination
        total_count = search_query.count()

        # Apply sorting
        search_query = apply_sorting(
            search_query, sort_by, sort_order, session, has_price_joins
        )

        # Execute query
        products = search_query.offset(offset).limit(limit).all()

        # Build response results
        search_results = []
        for product in products:
            # Get latest price record for this product
            latest_price = (
                session.query(PriceRecord)
                .filter(PriceRecord.product_id == product.id)
                .order_by(PriceRecord.recorded_at.desc())
                .first()
            )

            provider = None
            if latest_price:
                provider = (
                    session.query(Provider)
                    .filter(Provider.id == latest_price.provider_id)
                    .first()
                )

            search_results.append(build_product_result(product, latest_price, provider))

        # Calculate pagination info
        total_pages = (total_count + limit - 1) // limit
        current_page = (offset // limit) + 1

        search_time = calculate_search_time(start_time)

        return SearchProductsResponse(
            results=search_results,
            total_count=total_count,
            page=current_page,
            per_page=limit,
            total_pages=total_pages,
            search_time_ms=search_time,
            query=query,
            filters_applied={
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "available_only": available_only,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/suggestions", response_model=SearchSuggestionsResponse)
async def get_search_suggestions(
    query: str = Query(..., min_length=1, description="Partial search query"),
    limit: int = Query(10, ge=1, le=20, description="Number of suggestions"),
    session: Session = Depends(get_session),
):
    """
    Get search suggestions/autocomplete for the given query.
    Returns relevant product names and categories that match the partial query.
    """
    start_time = time.time()

    try:
        suggestions = set()

        # Get product name suggestions
        product_names = (
            session.query(Product.name)
            .filter(Product.name.ilike(f"%{query}%"))
            .limit(limit // 2)
            .all()
        )

        for (name,) in product_names:
            suggestions.add(name)

        # Get category suggestions
        categories = (
            session.query(Product.category)
            .filter(Product.category.ilike(f"%{query}%"))
            .distinct()
            .limit(limit // 2)
            .all()
        )

        for (category,) in categories:
            if category:
                suggestions.add(category)

        # Convert to sorted list and limit
        suggestion_list = sorted(list(suggestions))[:limit]

        suggestion_time = calculate_search_time(start_time)

        return SearchSuggestionsResponse(
            suggestions=suggestion_list, query=query, suggestion_time_ms=suggestion_time
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get suggestions: {str(e)}"
        )


@router.get("/facets", response_model=SearchFacetsResponse)
async def get_search_facets(
    query: Optional[str] = Query(None, description="Optional query to filter facets"),
    session: Session = Depends(get_session),
):
    """
    Get search facets for filtering options.
    Returns available categories, price ranges, and availability counts.
    """
    try:
        base_filter = []
        if query:
            base_filter.append(
                or_(
                    Product.name.ilike(f"%{query}%"),
                    Product.description.ilike(f"%{query}%"),
                )
            )

        # Get category facets
        category_query = (
            session.query(Product.category, func.count(Product.id).label("count"))
            .filter(*base_filter)
            .group_by(Product.category)
        )

        categories = [
            CategoryFacet(name=category or "Uncategorized", count=count)
            for category, count in category_query.all()
        ]

        # Get price range facets
        price_ranges = [
            PriceRangeFacet(min_price=0, max_price=100, count=0, label="Under $100"),
            PriceRangeFacet(min_price=100, max_price=500, count=0, label="$100 - $500"),
            PriceRangeFacet(
                min_price=500, max_price=1000, count=0, label="$500 - $1000"
            ),
            PriceRangeFacet(
                min_price=1000, max_price=999999, count=0, label="Over $1000"
            ),
        ]

        # Count products in each price range
        for price_range in price_ranges:
            count_query = (
                session.query(func.count(Product.id.distinct()))
                .join(PriceRecord)
                .filter(*base_filter)
            )

            if price_range.max_price != 999999:
                count_query = count_query.filter(
                    and_(
                        PriceRecord.price >= price_range.min_price,
                        PriceRecord.price < price_range.max_price,
                    )
                )
            else:
                count_query = count_query.filter(
                    PriceRecord.price >= price_range.min_price
                )

            price_range.count = count_query.scalar() or 0

        # Get availability facets
        availability_query = (
            session.query(
                PriceRecord.is_available,
                func.count(Product.id.distinct()).label("count"),
            )
            .join(Product)
            .filter(*base_filter)
            .group_by(PriceRecord.is_available)
        )

        availability_counts = {True: 0, False: 0}
        for is_available, count in availability_query.all():
            availability_counts[is_available] = count

        availability = AvailabilityFacet(
            available=availability_counts[True], unavailable=availability_counts[False]
        )

        return SearchFacetsResponse(
            categories=categories, price_ranges=price_ranges, availability=availability
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get facets: {str(e)}")


@router.get("/analytics", response_model=SearchAnalyticsResponse)
async def get_search_analytics(
    session: Session = Depends(get_session),
):
    """
    Get search analytics including popular queries, search volume, and top categories.
    Note: This is a simplified implementation for demo purposes.
    """
    try:
        # Mock popular queries (in real implementation, this would come from search logs)
        popular_queries = [
            PopularQuery(
                query="iPhone",
                count=150,
                last_searched=datetime.utcnow() - timedelta(hours=2),
            ),
            PopularQuery(
                query="laptop",
                count=120,
                last_searched=datetime.utcnow() - timedelta(hours=1),
            ),
            PopularQuery(
                query="headphones",
                count=89,
                last_searched=datetime.utcnow() - timedelta(minutes=30),
            ),
        ]

        # Mock search volume (in real implementation, this would come from analytics DB)
        search_volume = [
            SearchVolumeMetric(
                period="today",
                total_searches=456,
                unique_queries=234,
                avg_results_per_search=8.5,
            ),
            SearchVolumeMetric(
                period="yesterday",
                total_searches=389,
                unique_queries=198,
                avg_results_per_search=7.8,
            ),
        ]

        # Get real category statistics
        category_stats = (
            session.query(
                Product.category, func.count(Product.id).label("search_count")
            )
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
            .limit(5)
            .all()
        )

        total_products = session.query(func.count(Product.id)).scalar()

        top_categories = [
            TopSearchCategory(
                category=category or "Uncategorized",
                search_count=count,
                percentage=round((count / total_products) * 100, 2)
                if total_products > 0
                else 0,
            )
            for category, count in category_stats
        ]

        return SearchAnalyticsResponse(
            popular_queries=popular_queries,
            search_volume=search_volume,
            top_categories=top_categories,
            total_searches_today=456,
            avg_search_time_ms=125.5,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get analytics: {str(e)}"
        )


@router.get("/products/export", response_model=SearchExportResponse)
async def export_search_results(
    query: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None, description="Category filter"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price"),
    available_only: Optional[bool] = Query(None, description="Available only"),
    format: str = Query("json", pattern="^(json|csv)$", description="Export format"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum number of results"),
    session: Session = Depends(get_session),
):
    """
    Export search results in JSON or CSV format.
    """
    try:
        # Build search query (reuse existing function)
        search_query = build_search_query(
            session, query, category, min_price, max_price, available_only
        )

        # Limit results for export
        results = search_query.limit(limit).all()

        # Build export data
        exported_products = []
        export_time = datetime.utcnow()

        for product in results:
            # Get latest price record
            latest_price = None
            provider = None
            if hasattr(product, "price_records") and product.price_records:
                latest_price = max(product.price_records, key=lambda x: x.recorded_at)
                provider = latest_price.provider

            exported_products.append(
                ExportedProduct(
                    id=product.id,
                    name=product.name,
                    description=product.description,
                    category=product.category,
                    url=product.url,
                    current_price=latest_price.price if latest_price else None,
                    currency=latest_price.currency if latest_price else None,
                    is_available=latest_price.is_available if latest_price else False,
                    provider_name=provider.name if provider else None,
                    exported_at=export_time,
                )
            )

        return SearchExportResponse(
            products=exported_products,
            total_count=len(exported_products),
            exported_at=export_time,
            query=query,
            filters={
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "available_only": available_only,
            },
            format=format,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export results: {str(e)}"
        )


# Simple in-memory storage for saved searches (in production, use database)
SAVED_SEARCHES: Dict[int, Dict] = {}
SEARCH_ID_COUNTER = 1


@router.post("/saved", response_model=SavedSearchResponse, status_code=201)
async def create_saved_search(
    search_data: SavedSearchCreate,
    session: Session = Depends(get_session),
):
    """
    Save a search query with filters for later use.
    """
    global SEARCH_ID_COUNTER

    try:
        # Create saved search entry
        current_time = datetime.utcnow()
        search_id = SEARCH_ID_COUNTER
        SEARCH_ID_COUNTER += 1

        saved_search = {
            "id": search_id,
            "name": search_data.name,
            "query": search_data.query,
            "filters": search_data.filters.dict() if search_data.filters else None,
            "description": search_data.description,
            "created_at": current_time,
            "updated_at": current_time,
            "last_used_at": None,
            "use_count": 0,
        }

        SAVED_SEARCHES[search_id] = saved_search

        return SavedSearchResponse(**saved_search)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save search: {str(e)}")


@router.get("/saved", response_model=List[SavedSearchResponse])
async def get_saved_searches(
    session: Session = Depends(get_session),
):
    """
    Get all saved searches.
    """
    try:
        saved_searches = [
            SavedSearchResponse(**search_data)
            for search_data in SAVED_SEARCHES.values()
        ]

        # Sort by created_at descending
        saved_searches.sort(key=lambda x: x.created_at, reverse=True)

        return saved_searches

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get saved searches: {str(e)}"
        )


@router.get("/saved/{search_id}", response_model=SavedSearchResponse)
async def get_saved_search(
    search_id: int,
    session: Session = Depends(get_session),
):
    """
    Get a specific saved search by ID.
    """
    if search_id not in SAVED_SEARCHES:
        raise HTTPException(status_code=404, detail="Saved search not found")

    return SavedSearchResponse(**SAVED_SEARCHES[search_id])


@router.patch("/saved/{search_id}", response_model=SavedSearchResponse)
async def update_saved_search(
    search_id: int,
    update_data: SavedSearchUpdate,
    session: Session = Depends(get_session),
):
    """
    Update a saved search.
    """
    if search_id not in SAVED_SEARCHES:
        raise HTTPException(status_code=404, detail="Saved search not found")

    try:
        saved_search = SAVED_SEARCHES[search_id]

        # Update fields
        if update_data.name is not None:
            saved_search["name"] = update_data.name
        if update_data.query is not None:
            saved_search["query"] = update_data.query
        if update_data.filters is not None:
            saved_search["filters"] = update_data.filters.dict()
        if update_data.description is not None:
            saved_search["description"] = update_data.description

        saved_search["updated_at"] = datetime.utcnow()

        return SavedSearchResponse(**saved_search)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update saved search: {str(e)}"
        )


@router.delete("/saved/{search_id}", status_code=204)
async def delete_saved_search(
    search_id: int,
    session: Session = Depends(get_session),
):
    """
    Delete a saved search.
    """
    if search_id not in SAVED_SEARCHES:
        raise HTTPException(status_code=404, detail="Saved search not found")

    try:
        del SAVED_SEARCHES[search_id]

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete saved search: {str(e)}"
        )
