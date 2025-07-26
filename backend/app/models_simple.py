"""
Simplified domain models for initial TDD testing.
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel


class UserRole(str, PyEnum):
    """User roles for role-based access control."""

    ADMIN = "admin"
    VIEWER = "viewer"


class AlertType(str, PyEnum):
    """Alert types for price notifications."""

    PRICE_DROP = "price_drop"
    PRICE_INCREASE = "price_increase"
    BACK_IN_STOCK = "back_in_stock"
    OUT_OF_STOCK = "out_of_stock"


class NotificationChannel(str, PyEnum):
    """Notification delivery channels."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"


class ProductStatus(str, PyEnum):
    """Product tracking status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONTINUED = "discontinued"


class Product(SQLModel, table=True):
    """Product model with basic validation."""

    __tablename__ = "products"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(min_length=2, max_length=200)
    url: Optional[str] = Field(default=None, max_length=2048)
    description: Optional[str] = Field(default=None, max_length=1000)
    category: Optional[str] = Field(default=None, max_length=100)
    image_url: Optional[str] = Field(default=None, max_length=2048)
    status: ProductStatus = Field(default=ProductStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    price_records: List["PriceRecord"] = Relationship(back_populates="product")
    alerts: List["PriceAlert"] = Relationship(back_populates="product")


class Provider(SQLModel, table=True):
    """Provider model with API configuration."""

    __tablename__ = "providers"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(min_length=2, max_length=100)
    base_url: str = Field(max_length=2048)
    api_key: Optional[str] = Field(default=None, max_length=255)
    rate_limit: int = Field(default=100, ge=1, le=10000)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    price_records: List["PriceRecord"] = Relationship(back_populates="provider")


class User(SQLModel, table=True):
    """User model with authentication."""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: EmailStr = Field(unique=True, index=True)
    name: str = Field(min_length=2, max_length=100)
    role: UserRole = Field(default=UserRole.VIEWER)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    alerts: List["PriceAlert"] = Relationship(back_populates="user")
    preferences: Optional["UserPreference"] = Relationship(back_populates="user")


class PriceRecord(SQLModel, table=True):
    """Price record model for TimescaleDB hypertable."""

    __tablename__ = "price_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    provider_id: int = Field(foreign_key="providers.id", index=True)
    price: float = Field(gt=0)
    currency: str = Field(default="USD", max_length=3)
    is_available: bool = Field(default=True)
    recorded_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Relationships
    product: Product = Relationship(back_populates="price_records")
    provider: Provider = Relationship(back_populates="price_records")


class PriceAlert(SQLModel, table=True):
    """Price alert model for notifications."""

    __tablename__ = "price_alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    alert_type: AlertType
    threshold_price: Optional[float] = Field(default=None, gt=0)
    notification_channels: List[NotificationChannel] = Field(
        default=[NotificationChannel.EMAIL]
    )
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User = Relationship(back_populates="alerts")
    product: Product = Relationship(back_populates="alerts")


class UserPreference(SQLModel, table=True):
    """User preference model for settings."""

    __tablename__ = "user_preferences"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    default_currency: str = Field(default="USD", max_length=3)
    timezone: str = Field(default="UTC", max_length=50)
    email_notifications: bool = Field(default=True)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)
    items_per_page: int = Field(default=20, ge=10, le=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User = Relationship(back_populates="preferences")
