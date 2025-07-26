from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models import AlertType


class ProductCreate(BaseModel):
    name: str


class ProviderCreate(BaseModel):
    name: str


class PriceAlertCreate(BaseModel):
    product_id: int
    threshold: float


class AlertCreate(BaseModel):
    """Schema for creating a new alert."""

    user_id: int
    product_id: int
    alert_type: AlertType
    threshold_price: Optional[float] = Field(None, gt=0)
    notification_channels: List[str] = Field(default=["email"])

    class Config:
        use_enum_values = True


class AlertUpdate(BaseModel):
    """Schema for updating an alert."""

    alert_type: Optional[AlertType] = None
    threshold_price: Optional[float] = Field(None, gt=0)
    notification_channels: Optional[List[str]] = None
    is_active: Optional[bool] = None

    class Config:
        use_enum_values = True


class AlertResponse(BaseModel):
    """Schema for alert responses."""

    id: int
    user_id: int
    product_id: int
    alert_type: str
    threshold_price: Optional[float]
    notification_channels: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserPreferenceUpdate(BaseModel):
    default_currency: Optional[str]
    notify_email: Optional[bool]
