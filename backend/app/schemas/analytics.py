"""
Analytics API response schemas.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PriceTrendPoint(BaseModel):
    """A single point in a price trend."""

    date: datetime
    price: float
    is_available: bool


class PriceStatistics(BaseModel):
    """Price statistics for a product."""

    current_price: Optional[float]
    average_price: float
    min_price: float
    max_price: float
    price_change_30d: float  # Percentage change over 30 days


class PriceTrendsResponse(BaseModel):
    """Response for price trends endpoint."""

    product_id: int
    product_name: str
    trends: List[PriceTrendPoint]
    statistics: PriceStatistics
    aggregation: str = "daily"


class PopularProduct(BaseModel):
    """Popular product with metrics."""

    id: int
    name: str
    category: str
    alert_count: int
    avg_price: Optional[float]
    price_records_count: int


class PopularProductsResponse(BaseModel):
    """Response for popular products endpoint."""

    products: List[PopularProduct]
    total_count: int


class ProviderPerformance(BaseModel):
    """Provider performance metrics."""

    id: int
    name: str
    price_records_count: int
    avg_price: Optional[float]
    products_tracked: int
    last_update: Optional[datetime]


class ProviderPerformanceResponse(BaseModel):
    """Response for provider performance endpoint."""

    providers: List[ProviderPerformance]
    total_count: int


class UserGrowthPoint(BaseModel):
    """User growth data point."""

    date: datetime
    new_users: int
    total_users: int


class UserEngagementResponse(BaseModel):
    """Response for user engagement statistics."""

    total_users: int
    active_users: int
    total_alerts: int
    active_alerts: int
    avg_alerts_per_user: float
    user_growth: List[UserGrowthPoint]


class RecentPriceUpdate(BaseModel):
    """Recent price update information."""

    product_name: str
    provider_name: str
    price: float
    recorded_at: datetime


class RecentAlert(BaseModel):
    """Recent alert information."""

    id: int
    user_email: str
    product_name: str
    alert_type: str
    created_at: datetime


class TopProduct(BaseModel):
    """Top performing product."""

    name: str
    alert_count: int
    avg_price: Optional[float]


class TopProvider(BaseModel):
    """Top performing provider."""

    name: str
    price_records_count: int
    products_tracked: int


class DashboardResponse(BaseModel):
    """Response for dashboard summary."""

    # Core metrics
    total_products: int
    total_providers: int
    total_users: int
    total_alerts: int
    total_price_records: int

    # Recent activity
    recent_price_updates: List[RecentPriceUpdate]
    recent_alerts: List[RecentAlert]

    # Top performers
    top_products: List[TopProduct]
    top_providers: List[TopProvider]


class PriceComparison(BaseModel):
    """Price comparison for a single provider."""

    provider_id: int
    provider_name: str
    current_price: Optional[float]
    last_updated: Optional[datetime]
    is_available: bool


class PriceComparisonResponse(BaseModel):
    """Response for price comparison endpoint."""

    product_id: int
    product_name: str
    comparisons: List[PriceComparison]
    best_price: Optional[float]
    price_spread: Optional[float]  # Difference between highest and lowest price


class AvailabilityHistoryPoint(BaseModel):
    """Availability history data point."""

    date: datetime
    is_available: bool
    provider_count: int  # Number of providers where product is available


class AvailabilityTrendsResponse(BaseModel):
    """Response for availability trends endpoint."""

    product_id: int
    availability_history: List[AvailabilityHistoryPoint]
    current_availability: bool
    availability_percentage: float  # Percentage of time product was available
