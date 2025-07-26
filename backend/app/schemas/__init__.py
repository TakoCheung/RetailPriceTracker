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


class UserPreferencesCreate(BaseModel):
    """Schema for creating user preferences."""

    user_id: int
    default_currency: str = Field(default="USD", max_length=3)
    timezone: str = Field(default="UTC", max_length=50)
    email_notifications: bool = Field(default=True)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)
    items_per_page: int = Field(default=20, ge=10, le=100)


class UserPreferencesUpdate(BaseModel):
    """Schema for updating user preferences."""

    default_currency: Optional[str] = Field(None, max_length=3)
    timezone: Optional[str] = Field(None, max_length=50)
    email_notifications: Optional[bool] = None
    webhook_url: Optional[str] = Field(None, max_length=2048)
    items_per_page: Optional[int] = Field(None, ge=10, le=100)


class UserPreferencesResponse(BaseModel):
    """Schema for user preferences responses."""

    id: int
    user_id: int
    default_currency: str
    timezone: str
    email_notifications: bool
    webhook_url: Optional[str]
    items_per_page: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserPreferenceUpdate(BaseModel):
    default_currency: Optional[str]
    notify_email: Optional[bool]
