"""
Test configuration and fixtures for the Retail Price Tracker application.
Provides database setup, authentication mocks, and common test utilities.
"""

import os
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Test database URL - using Docker service name for containerized tests
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/prices_test"
)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL, echo=False, future=True, pool_pre_ping=True
)

TestAsyncSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a clean database session for each test.
    Creates all tables before test and drops them after.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest.fixture
def mock_user():
    """Mock authenticated user for testing."""
    return {
        "id": 1,
        "email": "test@example.com",
        "name": "Test User",
        "role": "viewer",
        "github_id": "123456",
    }


@pytest.fixture
def mock_admin_user():
    """Mock admin user for testing."""
    return {
        "id": 2,
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
        "github_id": "789012",
    }


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.publish.return_value = 1
    return mock_redis


@pytest.fixture
def mock_celery():
    """Mock Celery for testing."""
    mock_celery = Mock()
    mock_celery.send_task.return_value = Mock(id="test-task-id")
    return mock_celery


@pytest.fixture
def sample_price_data():
    """Sample price data for testing."""
    return {
        "product_id": 1,
        "provider_id": 1,
        "price": 99.99,
        "currency": "USD",
        "timestamp": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return {
        "name": "iPhone 15 Pro",
        "description": "Latest iPhone model",
        "category": "smartphones",
        "brand": "Apple",
    }


@pytest.fixture
def sample_provider_data():
    """Sample provider data for testing."""
    return {
        "name": "Amazon",
        "base_url": "https://api.amazon.com",
        "api_key": "test-api-key",
        "rate_limit": 100,
        "is_active": True,
    }


@pytest.fixture
def sample_alert_data():
    """Sample alert data for testing."""
    return {
        "user_id": 1,
        "product_id": 1,
        "threshold_price": 899.99,
        "condition": "below",
        "is_active": True,
        "notification_channels": ["email", "websocket"],
    }


@pytest.fixture
def freeze_time():
    """Fixture to freeze time for testing."""
    from freezegun import freeze_time

    return freeze_time
