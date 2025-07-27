"""
Search API response schemas for Advanced Search & Filtering.
Provides comprehensive search capabilities across products and prices.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Product search result schema
class SearchProductResult(BaseModel):
    """Individual product in search results."""

    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = "ACTIVE"
    created_at: Optional[str] = None
    current_price: Optional[Dict[str, Any]] = None
    currency: Optional[str] = None
    is_available: bool = False
    providers: List[Dict[str, Any]] = []
    score: Optional[float] = Field(None, description="Search relevance score")
    relevance_score: Optional[float] = Field(None, description="Search relevance score")
    price_change: Optional[Dict[str, Any]] = None


class SearchProductsResponse(BaseModel):
    """Response for product search endpoint."""

    results: List[SearchProductResult]
    total: int
    page: int = 1
    per_page: int = 20
    total_pages: int
    search_time_ms: int
    query: Optional[str] = None
    filters_applied: Dict[str, Any] = {}
    facets: Optional[Dict[str, Any]] = None
    applied_filters: Optional[Dict[str, Any]] = None
    performance: Optional[Dict[str, Any]] = None
    spelling_suggestion: Optional[str] = None


# Search suggestions schema
class SearchSuggestionsResponse(BaseModel):
    """Response for search suggestions/autocomplete."""

    suggestions: List[str]
    query: str
    suggestion_time_ms: int


# Search facets schema
class CategoryFacet(BaseModel):
    """Category facet with count."""

    name: str
    count: int


class PriceRangeFacet(BaseModel):
    """Price range facet."""

    min_price: float
    max_price: float
    count: int
    label: str


class AvailabilityFacet(BaseModel):
    """Availability facet."""

    available: int
    unavailable: int


class SearchFacetsResponse(BaseModel):
    """Response for search facets."""

    categories: List[CategoryFacet]
    price_ranges: List[PriceRangeFacet]
    availability: AvailabilityFacet


# Search analytics schemas
class PopularQuery(BaseModel):
    """Popular search query."""

    query: str
    count: int
    last_searched: datetime


class SearchVolumeMetric(BaseModel):
    """Search volume metrics."""

    period: str
    total_searches: int
    unique_queries: int
    avg_results_per_search: float


class TopSearchCategory(BaseModel):
    """Top searched category."""

    category: str
    search_count: int
    percentage: float


class SearchAnalyticsResponse(BaseModel):
    """Response for search analytics."""

    popular_queries: List[PopularQuery]
    search_volume: List[SearchVolumeMetric]
    top_categories: List[TopSearchCategory]
    total_searches_today: int
    avg_search_time_ms: float


# Search export schema
class ExportedProduct(BaseModel):
    """Product data for export."""

    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    current_price: Optional[float] = None
    currency: Optional[str] = None
    is_available: bool
    provider_name: Optional[str] = None
    exported_at: datetime


class SearchExportResponse(BaseModel):
    """Response for search results export."""

    products: List[ExportedProduct]
    total_count: int
    exported_at: datetime
    query: Optional[str] = None
    filters: Dict[str, Any] = {}
    format: str = "json"


# Saved search schemas
class SavedSearchFilters(BaseModel):
    """Filters for saved search."""

    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    available_only: Optional[bool] = None
    sort_by: Optional[str] = None
    sort_order: Optional[str] = None


class SavedSearchCreate(BaseModel):
    """Request to create saved search."""

    name: str = Field(..., min_length=1, max_length=100)
    query: Optional[str] = None
    filters: Optional[SavedSearchFilters] = None
    description: Optional[str] = Field(None, max_length=500)


class SavedSearchResponse(BaseModel):
    """Response for saved search."""

    id: int
    name: str
    query: Optional[str] = None
    filters: Optional[SavedSearchFilters] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    use_count: int = 0


class SavedSearchUpdate(BaseModel):
    """Request to update saved search."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    query: Optional[str] = None
    filters: Optional[SavedSearchFilters] = None
    description: Optional[str] = Field(None, max_length=500)


# Search request parameters schema
class SearchParams(BaseModel):
    """Search parameters for validation."""

    query: Optional[str] = None
    category: Optional[str] = None
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    available_only: Optional[bool] = None
    sort_by: Optional[str] = Field(
        None, pattern="^(name|price|category|relevance|date)$"
    )
    sort_order: Optional[str] = Field(None, pattern="^(asc|desc)$")
    limit: Optional[int] = Field(20, ge=1, le=100)
    offset: Optional[int] = Field(0, ge=0)

    def validate_price_range(self):
        """Validate price range is logical."""
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price must be less than or equal to max_price")


# Error response schemas
class SearchErrorResponse(BaseModel):
    """Error response for search operations."""

    detail: str
    error_code: Optional[str] = None
    suggestions: Optional[List[str]] = None


# Search performance metrics
class SearchPerformanceMetrics(BaseModel):
    """Performance metrics for search operation."""

    total_time_ms: int
    query_time_ms: int
    filter_time_ms: int
    sort_time_ms: int
    pagination_time_ms: int
    results_count: int
    total_available: int
