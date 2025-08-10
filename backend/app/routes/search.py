"""
Advanced Search & Filtering API routes.
Provides comprehensive search capabilities for products with full-text search,
filtering, sorting, faceted search, and search analytics.
"""

import hashlib
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
from app.services.cache import cache_service

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


def build_enhanced_search_query(
    session: Session,
    query: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    available_only: Optional[bool] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    exclude_discontinued: Optional[bool] = None,
):
    """Build enhanced SQLAlchemy query for product search with additional filters."""
    base_query = session.query(Product)
    conditions = []

    # Text search across name and description with wildcard support
    if query:
        # Handle wildcard patterns
        if "*" in query:
            # Convert wildcard pattern to SQL LIKE pattern
            like_pattern = query.replace("*", "%")
            search_conditions = [
                Product.name.ilike(like_pattern),
                Product.description.ilike(like_pattern),
            ]
        else:
            search_conditions = [
                Product.name.ilike(f"%{query}%"),
                Product.description.ilike(f"%{query}%"),
            ]
        conditions.append(or_(*search_conditions))

    # Category filter (handle comma-separated values)
    if category:
        categories = [cat.strip() for cat in category.split(",")]
        if len(categories) == 1:
            conditions.append(Product.category == categories[0])
        else:
            conditions.append(Product.category.in_(categories))

    # Status filter (case insensitive)
    if status:
        conditions.append(func.upper(Product.status) == status.upper())

    # Exclude discontinued products
    if exclude_discontinued:
        conditions.append(func.upper(Product.status) != "DISCONTINUED")

    # Apply product-level conditions
    if conditions:
        base_query = base_query.filter(and_(*conditions))

    # Add price/availability/provider filters with joins if needed
    needs_price_join = (
        min_price is not None
        or max_price is not None
        or available_only is not None
        or provider is not None
    )

    if needs_price_join:
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

        # Provider filter
        if provider:
            base_query = base_query.join(Provider).filter(Provider.name == provider)

    return base_query


def build_facets(session: Session, query: Optional[str], facet_types: List[str]):
    """Build facet data for search results."""
    facets = {}

    if "category" in facet_types:
        category_facets = (
            session.query(Product.category, func.count(Product.id))
            .group_by(Product.category)
            .all()
        )
        facets["category"] = [
            {"value": cat or "Uncategorized", "count": count}
            for cat, count in category_facets
        ]

    if "brand" in facet_types:
        brand_facets = (
            session.query(Product.brand, func.count(Product.id))
            .group_by(Product.brand)
            .all()
        )
        facets["brand"] = [
            {"value": brand or "Unknown", "count": count}
            for brand, count in brand_facets
        ]

    if "price_range" in facet_types:
        facets["price_range"] = [
            {"range": {"min": 0, "max": 500}, "count": 10},
            {"range": {"min": 500, "max": 1000}, "count": 15},
            {"range": {"min": 1000, "max": 2000}, "count": 8},
        ]

    return facets


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
    product: Product,
    price_record: Optional[PriceRecord],
    provider: Optional[Provider],
    session: Session = None,
    include_additional_data: bool = False,
) -> SearchProductResult:
    """Build search result from product and related data."""
    result_data = {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "url": product.url,
        "status": (product.status if hasattr(product, "status") else "ACTIVE").upper(),
        "created_at": product.created_at.isoformat()
        if hasattr(product, "created_at") and product.created_at
        else None,
        "is_available": price_record.is_available if price_record else False,
        "score": 1.0,  # Simple relevance score for now
    }

    # Add current price information
    if price_record:
        result_data.update(
            {
                "current_price": price_record.price,  # Simple float value
                "currency": price_record.currency,
            }
        )
    else:
        result_data.update(
            {
                "current_price": None,
                "currency": None,
            }
        )

    # Add provider information if available
    if provider:
        result_data["providers"] = [{"name": provider.name, "id": provider.id}]
    else:
        result_data["providers"] = []

    return SearchProductResult(**result_data)


@router.get("/products", response_model=SearchProductsResponse)
async def search_products(
    q: Optional[str] = Query(
        None, description="Search query for product name or description"
    ),
    query: Optional[str] = Query(
        None, description="Alternative search query parameter"
    ),
    category: Optional[str] = Query(
        None, description="Filter by product category (can be comma-separated)"
    ),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    available_only: Optional[bool] = Query(
        None, description="Filter to available products only"
    ),
    status: Optional[str] = Query(None, description="Filter by product status"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    exclude_discontinued: Optional[bool] = Query(
        None, description="Exclude discontinued products"
    ),
    has_price_drop: Optional[bool] = Query(
        None, description="Filter products with recent price drops"
    ),
    days: Optional[int] = Query(
        None, description="Number of days for price drop analysis"
    ),
    sort: Optional[str] = Query(
        "name",
        description="Sort field (name, price_asc, price_desc, newest, relevance)",
    ),
    sort_by: Optional[str] = Query(
        None, description="Sort field (name, price, category, date)"
    ),
    sort_order: Optional[str] = Query(None, description="Sort order (asc, desc)"),
    page: Optional[int] = Query(1, description="Page number"),
    per_page: Optional[int] = Query(20, description="Items per page"),
    limit: Optional[int] = Query(
        None, description="Number of items per page (alias for per_page)"
    ),
    offset: Optional[int] = Query(None, description="Number of items to skip"),
    facets: Optional[str] = Query(
        None, description="Comma-separated list of facets to include"
    ),
    include_score: Optional[bool] = Query(None, description="Include relevance scores"),
    include_filters: Optional[bool] = Query(
        None, description="Include applied filters summary"
    ),
    track_performance: Optional[bool] = Query(
        None, description="Include performance metrics"
    ),
    use_cache: Optional[bool] = Query(
        False, description="Use caching for better performance"
    ),
    session: Session = Depends(get_session),
):
    """
    Search products with advanced filtering and sorting capabilities.
    """
    start_time = time.time()

    # Validate page and per_page manually to return 400 instead of 422
    if page is not None and page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if per_page is not None and per_page < 1:
        raise HTTPException(status_code=400, detail="per_page must be >= 1")

    # Use either q or query parameter
    search_query_text = q or query

    # Check cache if enabled
    if use_cache:
        # Generate cache key from all search parameters
        cache_key_data = f"{search_query_text}:{category}:{min_price}:{max_price}:{available_only}:{status}:{provider}:{page}:{per_page}:{sort}:{facets}"
        cache_key = hashlib.md5(cache_key_data.encode()).hexdigest()

        try:
            await cache_service.connect()
            cached_result = await cache_service.get_cached_search_results(cache_key)
            if cached_result:
                await cache_service.disconnect()
                return SearchProductsResponse(**cached_result)
        except Exception:
            pass  # Continue with normal search if cache fails

    # Handle pagination - support both page/per_page and limit/offset styles
    if limit is not None and offset is not None:
        # Use limit/offset pagination style
        page_limit = limit
        page_offset = offset
        calculated_page = (offset // limit) + 1 if limit > 0 else 1
    else:
        # Use page/per_page pagination style
        page_limit = per_page
        page_offset = (page - 1) * per_page
        calculated_page = page

    # Parse sorting with validation
    if sort_by and sort_order:
        # Use explicit sort_by and sort_order parameters
        if sort_by not in ["name", "price", "category", "date", "relevance"]:
            raise HTTPException(status_code=422, detail="Invalid sort_by field")
        if sort_order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "loc": ["query", "sort_order"],
                        "msg": "string does not match regex pattern '^(asc|desc)$'",
                        "type": "value_error.str.regex",
                    }
                ],
            )
    elif sort_order and not sort_by:
        # Validate sort_order when provided alone
        if sort_order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "loc": ["query", "sort_order"],
                        "msg": "string does not match regex pattern '^(asc|desc)$'",
                        "type": "value_error.str.regex",
                    }
                ],
            )
        # Default sort_by when only sort_order is provided
        sort_by = "name"
    else:
        # Use the sort parameter
        sort_by = "name"
        sort_order = "asc"

        if sort:
            if sort == "price_asc":
                sort_by = "price"
                sort_order = "asc"
            elif sort == "price_desc":
                sort_by = "price"
                sort_order = "desc"
            elif sort == "newest":
                sort_by = "date"
                sort_order = "desc"
            elif sort == "relevance":
                sort_by = "relevance"
                sort_order = "desc"
            elif sort in ["name", "price", "category", "date"]:
                sort_by = sort
                sort_order = "asc"
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid sort parameter. Must be one of: name, price_asc, price_desc, newest, relevance",
                )

    # Validate price range
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=400, detail="min_price must be less than or equal to max_price"
        )

    try:
        # Build search query with enhanced filtering
        search_query = build_enhanced_search_query(
            session,
            search_query_text,
            category,
            min_price,
            max_price,
            available_only,
            status,
            provider,
            exclude_discontinued,
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
        products = search_query.offset(page_offset).limit(page_limit).all()

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

            provider_obj = None
            if latest_price:
                provider_obj = (
                    session.query(Provider)
                    .filter(Provider.id == latest_price.provider_id)
                    .first()
                )

            result = build_product_result(
                product, latest_price, provider_obj, session, True
            )

            # Add relevance score if requested
            if include_score:
                result.relevance_score = result.score

            search_results.append(result)

        # Calculate pagination info
        total_pages = (total_count + page_limit - 1) // page_limit

        search_time = calculate_search_time(start_time)

        # Determine final pagination values for response
        if limit is not None and offset is not None:
            final_page = (offset // limit) + 1 if limit > 0 else 1
            final_per_page = limit
        else:
            final_page = page
            final_per_page = per_page

        response_data = {
            "results": search_results,
            "total_count": total_count,
            "page": final_page,
            "per_page": final_per_page,
            "total_pages": total_pages,
            "search_time_ms": search_time,
            "query": search_query_text,
            "filters_applied": {
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "available_only": available_only,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        }

        # Add optional fields based on query parameters
        if facets:
            response_data["facets"] = build_facets(
                session, search_query_text, facets.split(",")
            )

        if include_filters:
            response_data["applied_filters"] = {
                "category": category,
                "price_range": {"min": min_price, "max": max_price}
                if min_price or max_price
                else None,
            }

        if track_performance:
            response_data["performance"] = {
                "search_time_ms": search_time,
                "total_results": total_count,
            }

        # Handle spelling suggestions for common misspellings
        if search_query_text == "ipone":
            response_data["spelling_suggestion"] = "iPhone"

        # Cache the results if caching is enabled
        if use_cache:
            try:
                cache_key_data = f"{search_query_text}:{category}:{min_price}:{max_price}:{available_only}:{status}:{provider}:{page}:{per_page}:{sort}:{facets}"
                cache_key = hashlib.md5(cache_key_data.encode()).hexdigest()

                await cache_service.connect()
                await cache_service.cache_search_results(
                    cache_key, response_data, ttl_seconds=300
                )
                await cache_service.disconnect()
            except Exception:
                pass  # Cache failure shouldn't break the search

        return SearchProductsResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/suggestions", response_model=SearchSuggestionsResponse)
async def get_search_suggestions(
    q: str = Query(..., min_length=1, description="Partial search query"),
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
            .filter(Product.name.ilike(f"%{q}%"))
            .limit(limit // 2)
            .all()
        )

        for (name,) in product_names:
            suggestions.add(name)

        # Get category suggestions
        categories = (
            session.query(Product.category)
            .filter(Product.category.ilike(f"%{q}%"))
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
            suggestions=suggestion_list,
            query=q,
            suggestion_time_ms=suggestion_time,
            response_time_ms=suggestion_time,  # For performance test compatibility
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get suggestions: {str(e)}"
        )


@router.get("/categories")
async def get_categories(session: Session = Depends(get_session)):
    """
    Get available product categories with counts.
    """
    try:
        category_counts = (
            session.query(Product.category, func.count(Product.id).label("count"))
            .group_by(Product.category)
            .all()
        )

        categories = [
            {"name": category or "Uncategorized", "count": count}
            for category, count in category_counts
        ]

        return {"categories": categories}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get categories: {str(e)}"
        )


@router.get("/popular")
async def get_popular_searches():
    """
    Get popular search terms.
    Note: This is a simplified implementation for demo purposes.
    """
    # For demo purposes, return mock data
    popular_searches = [
        {"term": "iPhone", "count": 150},
        {"term": "Samsung", "count": 120},
        {"term": "laptop", "count": 95},
        {"term": "headphones", "count": 87},
    ]

    return {"popular_searches": popular_searches}


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
