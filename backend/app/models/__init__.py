"""
Simplified domain models for initial TDD testing.
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import List, Optional

from pydantic import EmailStr, ValidationError, field_validator, model_validator
from pydantic_core import ErrorDetails
from sqlalchemy import JSON
from sqlmodel import Column, Field, Relationship, SQLModel


def utc_now():
    """Return timezone-naive UTC datetime for database storage."""
    return datetime.utcnow()


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


class AlertCondition(str, PyEnum):
    """Alert condition types."""

    BELOW = "below"
    ABOVE = "above"
    EQUAL = "equal"


class AlertStatus(str, PyEnum):
    """Alert status types."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    TRIGGERED = "triggered"


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


class ProductProviderLink(SQLModel, table=True):
    """Many-to-many relationship between products and providers."""

    __tablename__ = "product_provider_links"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    provider_id: int = Field(foreign_key="providers.id", index=True)
    product_url: str = Field(max_length=2048)
    price_selector: Optional[str] = Field(default=None, max_length=200)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    product: "Product" = Relationship(back_populates="provider_links")
    provider: "Provider" = Relationship(back_populates="product_links")


class Product(SQLModel, table=True):
    """Product model with basic validation."""

    __tablename__ = "products"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    url: Optional[str] = Field(default=None, max_length=2048)
    description: Optional[str] = Field(default=None, max_length=1000)
    category: Optional[str] = Field(default=None, max_length=100)
    image_url: Optional[str] = Field(default=None, max_length=2048)
    status: ProductStatus = Field(default=ProductStatus.ACTIVE)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    price_records: List["PriceRecord"] = Relationship(back_populates="product")
    alerts: List["PriceAlert"] = Relationship(back_populates="product")
    provider_links: List["ProductProviderLink"] = Relationship(back_populates="product")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValidationError("Product name must be at least 2 characters long")
        return v.strip()

    def is_valid_name(self) -> bool:
        """Check if the product name is valid."""
        return len(self.name.strip()) >= 2 if self.name else False


class Provider(SQLModel, table=True):
    """Provider model with API configuration."""

    __tablename__ = "providers"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(
        min_length=2, max_length=100, unique=True
    )  # Added unique constraint
    base_url: str = Field(max_length=2048)
    api_key: Optional[str] = Field(default=None, max_length=255)
    rate_limit: int = Field(default=100, ge=1, le=10000)
    is_active: bool = Field(default=True)
    health_status: str = Field(default="unknown", max_length=20)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    price_records: List["PriceRecord"] = Relationship(back_populates="provider")
    product_links: List["ProductProviderLink"] = Relationship(back_populates="provider")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValidationError("Provider name must be at least 2 characters long")
        return v.strip()

    @field_validator("rate_limit")
    @classmethod
    def validate_rate_limit(cls, v):
        if v < 1:
            raise ValidationError("Rate limit must be greater than or equal to 1")
        return v

    def __init__(self, **data):
        # Validate name
        if "name" in data:
            name = data["name"]
            if not name or len(name.strip()) < 2:
                raise ValueError("Provider name must be at least 2 characters long")

        # Validate rate_limit
        if "rate_limit" in data:
            rate_limit = data["rate_limit"]
            if rate_limit < 1:
                raise ValueError("Rate limit must be greater than or equal to 1")

        super().__init__(**data)

    def is_valid_rate_limit(self) -> bool:
        """Check if the provider rate limit is valid."""
        return self.rate_limit >= 1


class User(SQLModel, table=True):
    """User model with authentication."""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: EmailStr = Field(unique=True, index=True)
    name: str = Field(min_length=2, max_length=100)
    password_hash: Optional[str] = Field(default=None, max_length=255)
    github_id: Optional[str] = Field(default=None, max_length=50, unique=True)
    role: UserRole = Field(default=UserRole.VIEWER)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

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
    timestamp: datetime = Field(default_factory=utc_now, index=True)
    recorded_at: datetime = Field(default_factory=utc_now, index=True)

    # Relationships
    product: Product = Relationship(back_populates="price_records")
    provider: Provider = Relationship(back_populates="price_records")

    @field_validator("price")
    @classmethod
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError("Price must be greater than 0")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        if len(v) != 3 or not v.isupper():
            raise ValueError("Currency must be 3 uppercase letters")
        return v

    def __init__(self, **data):
        # Manual validation to raise ValidationError as expected by tests
        if "price" in data and data["price"] <= 0:
            from pydantic import ValidationError
            from pydantic_core import ErrorDetails

            error_details: ErrorDetails = {
                "type": "greater_than",
                "loc": ("price",),
                "msg": "Input should be greater than 0",
                "input": data["price"],
                "ctx": {"gt": 0},
            }
            raise ValidationError.from_exception_data(
                "ValidationError", [error_details]
            )

        if "currency" in data:
            currency = data["currency"]
            if len(currency) != 3 or not currency.isupper():
                raise ValueError("Currency must be 3 uppercase letters")

        super().__init__(**data)


class PriceAlert(SQLModel, table=True):
    """Price alert model for notifications."""

    __tablename__ = "price_alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    alert_type: AlertType = Field(default=AlertType.PRICE_DROP)
    threshold_price: Optional[float] = Field(default=None, gt=0)
    condition: AlertCondition = Field(default=AlertCondition.BELOW)
    notification_channels: List[str] = Field(default=["email"], sa_column=Column(JSON))
    status: AlertStatus = Field(default=AlertStatus.ACTIVE)
    is_active: bool = Field(default=True)
    cooldown_minutes: int = Field(default=60, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    user: User = Relationship(back_populates="alerts")
    product: Product = Relationship(back_populates="alerts")

    def __init__(self, **data):
        # Manual validation to raise ValidationError as expected by tests
        if (
            "threshold_price" in data
            and data["threshold_price"] is not None
            and data["threshold_price"] <= 0
        ):
            from pydantic import ValidationError
            from pydantic_core import ErrorDetails

            error_details: ErrorDetails = {
                "type": "greater_than",
                "loc": ("threshold_price",),
                "msg": "Input should be greater than 0",
                "input": data["threshold_price"],
                "ctx": {"gt": 0},
            }
            raise ValidationError.from_exception_data(
                "ValidationError", [error_details]
            )

        # Validate notification_channels
        if "notification_channels" in data:
            channels = data["notification_channels"]
            valid_channels = {"email", "webhook", "sms"}
            for channel in channels:
                if channel not in valid_channels:
                    raise ValueError(f"Invalid notification channel: {channel}")

        super().__init__(**data)


class UserPreference(SQLModel, table=True):
    """User preference model for settings."""

    __tablename__ = "user_preferences"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    default_currency: str = Field(default="USD", max_length=3)
    user_timezone: str = Field(default="UTC", max_length=50)
    email_notifications: bool = Field(default=True)
    push_notifications: bool = Field(default=False)
    webhook_url: Optional[str] = Field(default=None, max_length=2048)
    items_per_page: int = Field(default=20, ge=10, le=100)
    chart_type: str = Field(default="line", max_length=50)
    default_time_range: str = Field(default="7d", max_length=10)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    user: User = Relationship(back_populates="preferences")

    def __init__(self, **data):
        # Validate currency
        if "default_currency" in data:
            currency = data["default_currency"]
            if len(currency) != 3 or not currency.isupper():
                raise ValueError("Currency must be 3 uppercase letters")

        # Validate items_per_page
        if "items_per_page" in data:
            items = data["items_per_page"]
            if not (1 <= items <= 100):
                raise ValueError("Items per page must be between 1 and 100")

        super().__init__(**data)
