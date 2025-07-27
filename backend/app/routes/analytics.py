"""
Analytics API endpoints.
Provides insights into price trends, user engagement, and system performance.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import PriceAlert, PriceRecord, Product, Provider, User
from app.services.cache import CacheService
from app.schemas.analytics import (
    AvailabilityHistoryPoint,
    AvailabilityTrendsResponse,
    DashboardResponse,
    PopularProduct,
    PopularProductsResponse,
    PriceComparison,
    PriceComparisonResponse,
    PriceStatistics,
    PriceTrendPoint,
    PriceTrendsResponse,
    ProviderPerformance,
    ProviderPerformanceResponse,
    RecentAlert,
    RecentPriceUpdate,
    TopProduct,
    TopProvider,
    UserEngagementResponse,
    UserGrowthPoint,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/price-trends/{product_id}", response_model=PriceTrendsResponse)
async def get_price_trends(
    product_id: int,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    aggregation: str = Query(
        "daily", description="Aggregation level (daily, weekly, monthly)"
    ),
    use_cache: bool = Query(True, description="Use cached data if available"),
    session: Session = Depends(get_session),
):
    """Get price trends for a specific product."""
    # Create cache key
    cache_key = f"price_trends:{product_id}:{start_date}:{end_date}:{aggregation}"
    
    # Try to get from cache first
    if use_cache:
        cache_service = CacheService()
        await cache_service.connect()
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            await cache_service.disconnect()
            return cached_data
    
    # Validate aggregation parameter
    if aggregation not in ["daily", "weekly", "monthly"]:
        raise HTTPException(
            status_code=422,
            detail="Invalid aggregation parameter. Must be daily, weekly, or monthly.",
        )

    # Verify product exists
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Set default date range (last 30 days)
    if not end_date:
        end_date_obj = datetime.utcnow()
    else:
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")

    if not start_date:
        start_date_obj = end_date_obj - timedelta(days=30)
    else:
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")

    # Query price records
    price_records = (
        session.query(PriceRecord)
        .filter(
            PriceRecord.product_id == product_id,
            PriceRecord.recorded_at >= start_date_obj,
            PriceRecord.recorded_at <= end_date_obj,
        )
        .order_by(PriceRecord.recorded_at)
        .all()
    )

    if not price_records:
        raise HTTPException(
            status_code=404, detail="No price data found for this product"
        )

    # Create trend points
    trends = [
        PriceTrendPoint(
            date=record.recorded_at,
            price=record.price,
            is_available=record.is_available,
        )
        for record in price_records
    ]

    # Calculate statistics
    prices = [r.price for r in price_records]
    current_price = price_records[-1].price if price_records else None

    # Get price from 30 days ago for comparison
    thirty_days_ago = end_date_obj - timedelta(days=30)
    old_price_record = (
        session.query(PriceRecord)
        .filter(
            PriceRecord.product_id == product_id,
            PriceRecord.recorded_at <= thirty_days_ago,
        )
        .order_by(desc(PriceRecord.recorded_at))
        .first()
    )

    price_change_30d = 0.0
    if old_price_record and current_price:
        price_change_30d = (
            (current_price - old_price_record.price) / old_price_record.price
        ) * 100

    statistics = PriceStatistics(
        current_price=current_price,
        average_price=sum(prices) / len(prices),
        min_price=min(prices),
        max_price=max(prices),
        price_change_30d=price_change_30d,
    )

    response = PriceTrendsResponse(
        product_id=product_id,
        product_name=product.name,
        trends=trends,
        statistics=statistics,
        aggregation=aggregation,
    )
    
    # Cache the result
    if use_cache:
        cache_service = CacheService()
        await cache_service.connect()
        await cache_service.set(cache_key, response, ttl=300)  # Cache for 5 minutes
        await cache_service.disconnect()
    
    return response


@router.get("/popular-products", response_model=PopularProductsResponse)
async def get_popular_products(
    limit: int = Query(10, ge=1, le=100),
    use_cache: bool = Query(True, description="Use cached data if available"),
    session: Session = Depends(get_session),
):
    """Get most popular products based on alert count."""
    # Create cache key
    cache_key = f"popular_products:{limit}"
    
    # Try to get from cache first
    if use_cache:
        cache_service = CacheService()
        await cache_service.connect()
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            await cache_service.disconnect()
            return cached_data
    
    # Query products with alert counts and price statistics
    popular_products_query = (
        session.query(
            Product.id,
            Product.name,
            Product.category,
            func.count(PriceAlert.id).label("alert_count"),
            func.avg(PriceRecord.price).label("avg_price"),
            func.count(PriceRecord.id).label("price_records_count"),
        )
        .outerjoin(PriceAlert, Product.id == PriceAlert.product_id)
        .outerjoin(PriceRecord, Product.id == PriceRecord.product_id)
        .group_by(Product.id, Product.name, Product.category)
        .order_by(desc("alert_count"))
        .limit(limit)
        .all()
    )

    products = [
        PopularProduct(
            id=row.id,
            name=row.name,
            category=row.category or "Uncategorized",
            alert_count=row.alert_count or 0,
            avg_price=float(row.avg_price) if row.avg_price else None,
            price_records_count=row.price_records_count or 0,
        )
        for row in popular_products_query
    ]

    # Get total count
    total_count = session.query(Product).count()

    response = PopularProductsResponse(products=products, total_count=total_count)
    
    # Cache the result
    if use_cache:
        cache_service = CacheService()
        await cache_service.connect()
        await cache_service.set(cache_key, response, ttl=600)  # Cache for 10 minutes
        await cache_service.disconnect()
    
    return response


@router.get("/provider-performance", response_model=ProviderPerformanceResponse)
def get_provider_performance(
    session: Session = Depends(get_session),
):
    """Get provider performance metrics."""
    # Query providers with performance statistics
    provider_performance_query = (
        session.query(
            Provider.id,
            Provider.name,
            func.count(PriceRecord.id).label("price_records_count"),
            func.avg(PriceRecord.price).label("avg_price"),
            func.count(func.distinct(PriceRecord.product_id)).label("products_tracked"),
            func.max(PriceRecord.recorded_at).label("last_update"),
        )
        .outerjoin(PriceRecord, Provider.id == PriceRecord.provider_id)
        .group_by(Provider.id, Provider.name)
        .order_by(desc("price_records_count"))
        .all()
    )

    providers = [
        ProviderPerformance(
            id=row.id,
            name=row.name,
            price_records_count=row.price_records_count or 0,
            avg_price=float(row.avg_price) if row.avg_price else None,
            products_tracked=row.products_tracked or 0,
            last_update=row.last_update,
        )
        for row in provider_performance_query
    ]

    total_count = session.query(Provider).count()

    return ProviderPerformanceResponse(providers=providers, total_count=total_count)


@router.get("/user-engagement", response_model=UserEngagementResponse)
def get_user_engagement_stats(
    session: Session = Depends(get_session),
):
    """Get user engagement statistics."""
    # Basic counts
    total_users = session.query(User).count()
    active_users = session.query(User).filter(User.is_active).count()
    total_alerts = session.query(PriceAlert).count()
    active_alerts = session.query(PriceAlert).filter(PriceAlert.is_active).count()

    avg_alerts_per_user = total_alerts / total_users if total_users > 0 else 0.0

    # User growth over last 30 days (simplified)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    user_growth_query = (
        session.query(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("new_users"),
        )
        .filter(User.created_at >= thirty_days_ago)
        .group_by(func.date(User.created_at))
        .order_by("date")
        .all()
    )

    # Calculate cumulative totals
    cumulative_users = total_users - sum(row.new_users for row in user_growth_query)
    user_growth = []
    for row in user_growth_query:
        cumulative_users += row.new_users
        user_growth.append(
            UserGrowthPoint(
                date=datetime.strptime(str(row.date), "%Y-%m-%d"),
                new_users=row.new_users,
                total_users=cumulative_users,
            )
        )

    return UserEngagementResponse(
        total_users=total_users,
        active_users=active_users,
        total_alerts=total_alerts,
        active_alerts=active_alerts,
        avg_alerts_per_user=avg_alerts_per_user,
        user_growth=user_growth,
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_summary(
    use_cache: bool = Query(True, description="Use cached data if available"),
    session: Session = Depends(get_session),
):
    """Get dashboard summary statistics."""
    # Create cache key
    cache_key = "dashboard_summary"
    
    # Try to get from cache first
    if use_cache:
        cache_service = CacheService()
        await cache_service.connect()
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            await cache_service.disconnect()
            return cached_data
    
    # Core metrics
    total_products = session.query(Product).count()
    total_providers = session.query(Provider).count()
    total_users = session.query(User).count()
    total_alerts = session.query(PriceAlert).count()
    total_price_records = session.query(PriceRecord).count()

    # Recent price updates (last 10)
    recent_price_updates_query = (
        session.query(PriceRecord, Product.name, Provider.name)
        .join(Product, PriceRecord.product_id == Product.id)
        .join(Provider, PriceRecord.provider_id == Provider.id)
        .order_by(desc(PriceRecord.recorded_at))
        .limit(10)
        .all()
    )

    recent_price_updates = [
        RecentPriceUpdate(
            product_name=row[1],
            provider_name=row[2],
            price=row[0].price,
            recorded_at=row[0].recorded_at,
        )
        for row in recent_price_updates_query
    ]

    # Recent alerts (last 10)
    recent_alerts_query = (
        session.query(PriceAlert, User.email, Product.name)
        .join(User, PriceAlert.user_id == User.id)
        .join(Product, PriceAlert.product_id == Product.id)
        .order_by(desc(PriceAlert.created_at))
        .limit(10)
        .all()
    )

    recent_alerts = [
        RecentAlert(
            id=row[0].id,
            user_email=row[1],
            product_name=row[2],
            alert_type=row[0].alert_type,
            created_at=row[0].created_at,
        )
        for row in recent_alerts_query
    ]

    # Top products by alert count
    top_products_query = (
        session.query(
            Product.name,
            func.count(PriceAlert.id).label("alert_count"),
            func.avg(PriceRecord.price).label("avg_price"),
        )
        .outerjoin(PriceAlert, Product.id == PriceAlert.product_id)
        .outerjoin(PriceRecord, Product.id == PriceRecord.product_id)
        .group_by(Product.name)
        .order_by(desc("alert_count"))
        .limit(5)
        .all()
    )

    top_products = [
        TopProduct(
            name=row.name,
            alert_count=row.alert_count or 0,
            avg_price=float(row.avg_price) if row.avg_price else None,
        )
        for row in top_products_query
    ]

    # Top providers by price records count
    top_providers_query = (
        session.query(
            Provider.name,
            func.count(PriceRecord.id).label("price_records_count"),
            func.count(func.distinct(PriceRecord.product_id)).label("products_tracked"),
        )
        .outerjoin(PriceRecord, Provider.id == PriceRecord.provider_id)
        .group_by(Provider.name)
        .order_by(desc("price_records_count"))
        .limit(5)
        .all()
    )

    top_providers = [
        TopProvider(
            name=row.name,
            price_records_count=row.price_records_count or 0,
            products_tracked=row.products_tracked or 0,
        )
        for row in top_providers_query
    ]

    response = DashboardResponse(
        total_products=total_products,
        total_providers=total_providers,
        total_users=total_users,
        total_alerts=total_alerts,
        total_price_records=total_price_records,
        recent_price_updates=recent_price_updates,
        recent_alerts=recent_alerts,
        top_products=top_products,
        top_providers=top_providers,
    )
    
    # Cache the result
    if use_cache:
        cache_service = CacheService()
        await cache_service.connect()
        await cache_service.set(cache_key, response, ttl=120)  # Cache for 2 minutes
        await cache_service.disconnect()
    
    return response


@router.get("/price-comparison/{product_id}", response_model=PriceComparisonResponse)
def get_price_comparison(
    product_id: int,
    session: Session = Depends(get_session),
):
    """Get price comparison across providers for a product."""
    # Verify product exists
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get latest price from each provider
    latest_prices_subquery = (
        session.query(
            PriceRecord.provider_id,
            func.max(PriceRecord.recorded_at).label("latest_recorded_at"),
        )
        .filter(PriceRecord.product_id == product_id)
        .group_by(PriceRecord.provider_id)
        .subquery()
    )

    price_comparisons_query = (
        session.query(
            PriceRecord,
            Provider.name,
        )
        .join(Provider, PriceRecord.provider_id == Provider.id)
        .join(
            latest_prices_subquery,
            and_(
                PriceRecord.provider_id == latest_prices_subquery.c.provider_id,
                PriceRecord.recorded_at == latest_prices_subquery.c.latest_recorded_at,
            ),
        )
        .filter(PriceRecord.product_id == product_id)
        .all()
    )

    comparisons = [
        PriceComparison(
            provider_id=row[0].provider_id,
            provider_name=row[1],
            current_price=row[0].price,
            last_updated=row[0].recorded_at,
            is_available=row[0].is_available,
        )
        for row in price_comparisons_query
    ]

    # Calculate best price and price spread
    available_prices = [
        c.current_price for c in comparisons if c.is_available and c.current_price
    ]
    best_price = min(available_prices) if available_prices else None
    price_spread = (
        (max(available_prices) - min(available_prices))
        if len(available_prices) > 1
        else None
    )

    return PriceComparisonResponse(
        product_id=product_id,
        product_name=product.name,
        comparisons=comparisons,
        best_price=best_price,
        price_spread=price_spread,
    )


@router.get(
    "/availability-trends/{product_id}", response_model=AvailabilityTrendsResponse
)
def get_availability_trends(
    product_id: int,
    session: Session = Depends(get_session),
):
    """Get product availability trends over time."""
    # Verify product exists
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get availability history (daily aggregation)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    availability_query = (
        session.query(
            func.date(PriceRecord.recorded_at).label("date"),
            func.max(PriceRecord.is_available).label(
                "is_available"
            ),  # Use max instead of bool_or for SQLite
            func.count(func.distinct(PriceRecord.provider_id)).label("provider_count"),
        )
        .filter(
            PriceRecord.product_id == product_id,
            PriceRecord.recorded_at >= thirty_days_ago,
        )
        .group_by(func.date(PriceRecord.recorded_at))
        .order_by("date")
        .all()
    )

    availability_history = [
        AvailabilityHistoryPoint(
            date=datetime.strptime(str(row.date), "%Y-%m-%d"),
            is_available=bool(row.is_available),
            provider_count=row.provider_count,
        )
        for row in availability_query
    ]

    # Calculate current availability and percentage
    latest_availability = (
        session.query(PriceRecord.is_available)
        .filter(PriceRecord.product_id == product_id)
        .order_by(desc(PriceRecord.recorded_at))
        .first()
    )

    current_availability = latest_availability[0] if latest_availability else False

    # Calculate availability percentage
    available_days = sum(1 for point in availability_history if point.is_available)
    availability_percentage = (
        (available_days / len(availability_history) * 100)
        if availability_history
        else 0.0
    )

    return AvailabilityTrendsResponse(
        product_id=product_id,
        availability_history=availability_history,
        current_availability=current_availability,
        availability_percentage=availability_percentage,
    )
