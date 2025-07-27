"""
Test cases for domain models - Product, Provider, User, PriceRecord, PriceAlert, UserPreference.
These tests follow TDD principles - they will fail initially and guide implementation.
"""

from datetime import datetime, timezone

import pytest
from app.models import (
    AlertCondition,
    AlertStatus,
    PriceAlert,
    PriceRecord,
    Product,
    ProductProviderLink,
    Provider,
    User,
    UserPreference,
    UserRole,
)
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class TestProductModel:
    """Test cases for the Product model."""

    @pytest.mark.asyncio
    async def test_create_product_with_valid_data(
        self, db_session: AsyncSession, sample_product_data
    ):
        """Test creating a product with valid data."""
        product = Product(**sample_product_data)
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        assert product.id is not None
        assert product.name == sample_product_data["name"]
        assert product.description == sample_product_data["description"]
        assert product.category == sample_product_data["category"]
        assert product.brand == sample_product_data["brand"]
        assert product.is_active is True
        assert product.created_at is not None
        assert product.deleted_at is None

    @pytest.mark.asyncio
    async def test_product_name_validation(self, db_session: AsyncSession):
        """Test product name validation."""
        # Test empty name
        with pytest.raises(ValueError):
            Product(name="")

        # Test name with only spaces
        with pytest.raises(ValueError):
            Product(name="   ")

        # Test single character name
        with pytest.raises(ValueError):
            Product(name="A")

        # Test valid name
        product = Product(name="Valid Product Name")
        assert product.name == "Valid Product Name"

    @pytest.mark.asyncio
    async def test_product_sku_uniqueness(self, db_session: AsyncSession):
        """Test that product SKU must be unique."""
        # Create first product with SKU
        product1 = Product(name="Product 1", sku="SKU001")
        db_session.add(product1)
        await db_session.commit()

        # Try to create second product with same SKU
        product2 = Product(name="Product 2", sku="SKU001")
        db_session.add(product2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_product_soft_deletion(self, db_session: AsyncSession):
        """Test product soft deletion functionality."""
        product = Product(name="Product to Delete")
        db_session.add(product)
        await db_session.commit()

        # Soft delete
        product.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()

        assert product.deleted_at is not None
        assert product.is_active is True  # is_active is separate from soft deletion

    @pytest.mark.asyncio
    async def test_product_provider_relationship(self, db_session: AsyncSession):
        """Test many-to-many relationship between products and providers."""
        # Create product and provider
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")

        db_session.add(product)
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create relationship
        link = ProductProviderLink(
            product_id=product.id,
            provider_id=provider.id,
            product_url="https://test.com/product/123",
            price_selector=".price",
        )
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        # Test relationship exists via the link
        assert link.product_id == product.id
        assert link.provider_id == provider.id
        assert link.product_url == "https://test.com/product/123"
        assert link.price_selector == ".price"


class TestProviderModel:
    """Test cases for the Provider model."""

    @pytest.mark.asyncio
    async def test_create_provider_with_valid_data(
        self, db_session: AsyncSession, sample_provider_data
    ):
        """Test creating a provider with valid data."""
        provider = Provider(**sample_provider_data)
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(provider)

        assert provider.id is not None
        assert provider.name == sample_provider_data["name"]
        assert provider.base_url == sample_provider_data["base_url"]
        assert provider.api_key == sample_provider_data["api_key"]
        assert provider.rate_limit == sample_provider_data["rate_limit"]
        assert provider.is_active is True
        assert provider.health_status == "unknown"

    @pytest.mark.asyncio
    async def test_provider_name_uniqueness(self, db_session: AsyncSession):
        """Test that provider name must be unique."""
        # Create first provider
        provider1 = Provider(name="Amazon", base_url="https://amazon.com")
        db_session.add(provider1)
        await db_session.commit()

        # Try to create second provider with same name
        provider2 = Provider(name="Amazon", base_url="https://amazon.co.uk")
        db_session.add(provider2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_provider_name_validation(self, db_session: AsyncSession):
        """Test provider name validation."""
        # Test empty name
        with pytest.raises(ValueError):
            Provider(name="", base_url="https://test.com")

        # Test name with only spaces
        with pytest.raises(ValueError):
            Provider(name="   ", base_url="https://test.com")

        # Test single character name
        with pytest.raises(ValueError):
            Provider(name="A", base_url="https://test.com")

    @pytest.mark.asyncio
    async def test_provider_rate_limit_validation(self, db_session: AsyncSession):
        """Test provider rate limit validation."""
        # Test negative rate limit
        with pytest.raises(ValueError):
            Provider(name="Test", base_url="https://test.com", rate_limit=-1)

        # Test zero rate limit
        with pytest.raises(ValueError):
            Provider(name="Test", base_url="https://test.com", rate_limit=0)


class TestUserModel:
    """Test cases for the User model."""

    @pytest.mark.asyncio
    async def test_create_user_with_valid_data(self, db_session: AsyncSession):
        """Test creating a user with valid data."""
        user = User(
            email="test@example.com",
            name="Test User",
            github_id="123456",
            role=UserRole.VIEWER,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.role == UserRole.VIEWER
        assert user.github_id == "123456"
        assert user.is_active is True
        assert user.created_at is not None

    @pytest.mark.asyncio
    async def test_user_email_uniqueness(self, db_session: AsyncSession):
        """Test that user email must be unique."""
        # Create first user
        user1 = User(email="test@example.com", name="User 1")
        db_session.add(user1)
        await db_session.commit()

        # Try to create second user with same email
        user2 = User(email="test@example.com", name="User 2")
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_github_id_uniqueness(self, db_session: AsyncSession):
        """Test that GitHub ID must be unique."""
        # Create first user
        user1 = User(email="user1@example.com", name="User 1", github_id="123456")
        db_session.add(user1)
        await db_session.commit()

        # Try to create second user with same GitHub ID
        user2 = User(email="user2@example.com", name="User 2", github_id="123456")
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestPriceRecordModel:
    """Test cases for the PriceRecord model (TimescaleDB hypertable)."""

    @pytest.mark.asyncio
    async def test_create_price_record_with_valid_data(self, db_session: AsyncSession):
        """Test creating a price record with valid data."""
        # Create required product and provider
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")
        db_session.add(product)
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create price record
        price_record = PriceRecord(
            product_id=product.id,
            provider_id=provider.id,
            price=99.99,
            currency="USD",
            is_available=True,
            timestamp=datetime.now(),
        )
        db_session.add(price_record)
        await db_session.commit()
        await db_session.refresh(price_record)

        assert price_record.id is not None
        assert price_record.product_id == product.id
        assert price_record.provider_id == provider.id
        assert price_record.price == 99.99
        assert price_record.currency == "USD"
        assert price_record.is_available is True
        assert price_record.timestamp is not None

    @pytest.mark.asyncio
    async def test_price_validation(self, db_session: AsyncSession):
        """Test price validation in price records."""
        # Test negative price
        with pytest.raises(ValidationError):
            PriceRecord(product_id=1, provider_id=1, price=-10.0)

        # Test zero price
        with pytest.raises(ValidationError):
            PriceRecord(product_id=1, provider_id=1, price=0.0)

    @pytest.mark.asyncio
    async def test_currency_validation(self, db_session: AsyncSession):
        """Test currency code validation."""
        # Test invalid currency length
        with pytest.raises(ValidationError):
            PriceRecord(product_id=1, provider_id=1, price=10.0, currency="US")

        # Test lowercase currency
        with pytest.raises(ValidationError):
            PriceRecord(product_id=1, provider_id=1, price=10.0, currency="usd")

        # Test valid currency
        price_record = PriceRecord(
            product_id=1, provider_id=1, price=10.0, currency="USD"
        )
        assert price_record.currency == "USD"

    @pytest.mark.asyncio
    async def test_price_record_relationships(self, db_session: AsyncSession):
        """Test relationships between price records, products, and providers."""
        # Create product and provider
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")
        db_session.add(product)
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create price record
        price_record = PriceRecord(
            product_id=product.id, provider_id=provider.id, price=99.99
        )
        db_session.add(price_record)
        await db_session.commit()
        await db_session.refresh(price_record)

        # Test relationships
        assert price_record.product.name == "Test Product"
        assert price_record.provider.name == "Test Provider"
        assert len(product.price_records) == 1
        assert len(provider.price_records) == 1


class TestPriceAlertModel:
    """Test cases for the PriceAlert model."""

    @pytest.mark.asyncio
    async def test_create_price_alert_with_valid_data(self, db_session: AsyncSession):
        """Test creating a price alert with valid data."""
        # Create required user and product
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")
        db_session.add(user)
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)

        # Create price alert
        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=899.99,
            condition=AlertCondition.BELOW,
            notification_channels=["email", "websocket"],
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        assert alert.id is not None
        assert alert.user_id == user.id
        assert alert.product_id == product.id
        assert alert.threshold_price == 899.99
        assert alert.condition == AlertCondition.BELOW
        assert alert.notification_channels == ["email", "websocket"]
        assert alert.status == AlertStatus.ACTIVE
        assert alert.is_active is True
        assert alert.cooldown_minutes == 60

    @pytest.mark.asyncio
    async def test_threshold_price_validation(self, db_session: AsyncSession):
        """Test threshold price validation."""
        # Test negative threshold
        with pytest.raises(ValidationError):
            PriceAlert(
                user_id=1,
                product_id=1,
                threshold_price=-100.0,
                condition=AlertCondition.BELOW,
            )

        # Test zero threshold
        with pytest.raises(ValidationError):
            PriceAlert(
                user_id=1,
                product_id=1,
                threshold_price=0.0,
                condition=AlertCondition.BELOW,
            )

    @pytest.mark.asyncio
    async def test_notification_channels_validation(self, db_session: AsyncSession):
        """Test notification channels validation."""
        # Test invalid channel
        with pytest.raises(ValidationError):
            PriceAlert(
                user_id=1,
                product_id=1,
                threshold_price=100.0,
                condition=AlertCondition.BELOW,
                notification_channels=["invalid_channel"],
            )

        # Test valid channels
        alert = PriceAlert(
            user_id=1,
            product_id=1,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["email", "websocket", "push"],
        )
        assert alert.notification_channels == ["email", "websocket", "push"]

    @pytest.mark.asyncio
    async def test_alert_relationships(self, db_session: AsyncSession):
        """Test relationships between alerts, users, and products."""
        # Create user and product
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")
        db_session.add(user)
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)

        # Create alert
        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        # Test relationships
        assert alert.user.email == "test@example.com"
        assert alert.product.name == "Test Product"
        assert len(user.alerts) == 1
        assert len(product.alerts) == 1


class TestUserPreferenceModel:
    """Test cases for the UserPreference model."""

    @pytest.mark.asyncio
    async def test_create_user_preference_with_defaults(self, db_session: AsyncSession):
        """Test creating user preference with default values."""
        # Create user first
        user = User(email="test@example.com", name="Test User")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create user preference
        preference = UserPreference(user_id=user.id)
        db_session.add(preference)
        await db_session.commit()
        await db_session.refresh(preference)

        assert preference.id is not None
        assert preference.user_id == user.id
        assert preference.default_currency == "USD"
        assert preference.timezone == "UTC"
        assert preference.email_notifications is True
        assert preference.push_notifications is False
        assert preference.items_per_page == 20
        assert preference.chart_type == "line"
        assert preference.default_time_range == "7d"

    @pytest.mark.asyncio
    async def test_user_preference_uniqueness(self, db_session: AsyncSession):
        """Test that each user can have only one preference record."""
        # Create user
        user = User(email="test@example.com", name="Test User")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create first preference
        preference1 = UserPreference(user_id=user.id)
        db_session.add(preference1)
        await db_session.commit()

        # Try to create second preference for same user
        preference2 = UserPreference(user_id=user.id)
        db_session.add(preference2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_currency_validation(self, db_session: AsyncSession):
        """Test currency validation in user preferences."""
        # Test invalid currency length
        with pytest.raises(ValidationError):
            UserPreference(user_id=1, default_currency="US")

        # Test lowercase currency
        with pytest.raises(ValidationError):
            UserPreference(user_id=1, default_currency="usd")

    @pytest.mark.asyncio
    async def test_items_per_page_validation(self, db_session: AsyncSession):
        """Test items per page validation."""
        # Test too low
        with pytest.raises(ValidationError):
            UserPreference(user_id=1, items_per_page=0)

        # Test too high
        with pytest.raises(ValidationError):
            UserPreference(user_id=1, items_per_page=150)

        # Test valid range
        preference = UserPreference(user_id=1, items_per_page=50)
        assert preference.items_per_page == 50

    @pytest.mark.asyncio
    async def test_user_preference_relationship(self, db_session: AsyncSession):
        """Test one-to-one relationship between user and preference."""
        # Create user
        user = User(email="test@example.com", name="Test User")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create preference
        preference = UserPreference(user_id=user.id)
        db_session.add(preference)
        await db_session.commit()
        await db_session.refresh(preference)

        # Test relationships
        assert preference.user.email == "test@example.com"
        assert user.preferences.default_currency == "USD"


class TestModelIndexes:
    """Test cases for database indexes and query optimization."""

    @pytest.mark.asyncio
    async def test_price_records_indexes_exist(self, db_session: AsyncSession):
        """Test that price records have proper indexes for time-series queries."""
        # This test would verify that indexes exist
        # In a real implementation, this would check database metadata
        pass

    @pytest.mark.asyncio
    async def test_query_performance_with_indexes(self, db_session: AsyncSession):
        """Test that indexed queries perform well with large datasets."""
        # This test would create a large dataset and verify query performance
        # For now, this is a placeholder for actual performance testing
        pass


class TestTimescaleDBIntegration:
    """Test cases specific to TimescaleDB hypertable functionality."""

    @pytest.mark.asyncio
    async def test_hypertable_creation(self, db_session: AsyncSession):
        """Test that price_records table is created as a hypertable."""
        # This test would verify TimescaleDB hypertable creation
        # In a real implementation, this would check TimescaleDB-specific metadata
        pass

    @pytest.mark.asyncio
    async def test_automatic_partitioning(self, db_session: AsyncSession):
        """Test that data is automatically partitioned by time."""
        # This test would verify automatic partitioning behavior
        # For now, this is a placeholder for actual TimescaleDB testing
        pass

    @pytest.mark.asyncio
    async def test_data_retention_policies(self, db_session: AsyncSession):
        """Test data retention and compression policies."""
        # This test would verify retention policies work correctly
        # For now, this is a placeholder for actual retention testing
        pass
