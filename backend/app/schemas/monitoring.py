"""
Pydantic schemas for real-time monitoring endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MonitoringTaskCreate(BaseModel):
    """Schema for creating a new monitoring task."""

    provider_id: int = Field(..., gt=0, description="Provider ID to monitor")
    check_interval: int = Field(
        default=300, ge=60, le=3600, description="Check interval in seconds"
    )


class MonitoringTaskResponse(BaseModel):
    """Response schema for monitoring task operations."""

    task_id: str
    status: str
    provider_id: int
    check_interval: int
    message: str


class MonitoringStatusResponse(BaseModel):
    """Response schema for monitoring system status."""

    active_monitors: int
    last_check: str
    system_health: str
    total_products_monitored: int


class PriceChangeEvent(BaseModel):
    """Schema for individual price change events."""

    old_price: float
    new_price: float
    change_percentage: float
    timestamp: str
    provider_id: int


class PriceChangeResponse(BaseModel):
    """Response schema for product price changes."""

    product_id: int
    price_changes: List[Dict[str, Any]]
    total_changes: int
    date_range_days: int


class MonitoringDashboardResponse(BaseModel):
    """Response schema for monitoring dashboard overview."""

    active_monitors: int
    total_products_monitored: int
    alerts_triggered_today: int
    price_changes_detected: int
    system_health: str
    last_update: str


class PriceChangeAnalyticsResponse(BaseModel):
    """Response schema for price change analytics."""

    total_changes: int
    average_change_percentage: float
    changes_by_category: Dict[str, int]
    trending_products: List[Dict[str, Any]]
    period_days: int


class AlertPerformanceResponse(BaseModel):
    """Response schema for alert performance metrics."""

    total_alerts: int
    alerts_by_type: Dict[str, int]
    response_times: Dict[str, float]
    success_rate: float
    period: str


class MonitoringConfigResponse(BaseModel):
    """Response schema for monitoring configuration."""

    default_interval: int
    high_priority_interval: int
    low_priority_interval: int
    price_change_threshold: float
    max_alerts_per_hour: int
    configuration_updated: bool


class AlertThresholdConfig(BaseModel):
    """Configuration schema for alert thresholds."""

    price_change_threshold: float = Field(ge=0.1, le=100.0)
    max_alerts_per_hour: int = Field(ge=1, le=100)


class NotificationTemplateConfig(BaseModel):
    """Configuration schema for notification templates."""

    price_drop_template: Optional[str] = None
    price_increase_template: Optional[str] = None
    back_in_stock_template: Optional[str] = None
    out_of_stock_template: Optional[str] = None


class BatchUpdateRequest(BaseModel):
    """Schema for batch price update requests."""

    price_updates: List[Dict[str, Any]]
    source: str = "monitoring_system"


class BatchUpdateResponse(BaseModel):
    """Response schema for batch price updates."""

    updates_processed: int
    processing_time: float
    success: bool


class MonitoringPerformanceResponse(BaseModel):
    """Response schema for monitoring task performance metrics."""

    average_execution_time: float
    tasks_per_minute: int
    error_rate: float
    queue_length: int


# WebSocket message schemas
class WebSocketPriceUpdate(BaseModel):
    """Schema for WebSocket price update messages."""

    product_id: int
    old_price: Optional[float]
    new_price: float
    currency: str
    is_available: bool
    timestamp: datetime
    provider_id: int
    change_percentage: Optional[float] = None


class WebSocketSubscription(BaseModel):
    """Schema for WebSocket subscription requests."""

    action: str = Field(..., pattern="^(subscribe|unsubscribe)$")
    product_id: int


class WebSocketMessage(BaseModel):
    """Schema for general WebSocket messages."""

    type: str
    data: Dict[str, Any]
