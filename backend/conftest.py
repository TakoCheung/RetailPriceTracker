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
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, create_engine

# Test database URL - using Docker service name for containerized tests
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/prices_test"
)

# Create test engines (both async and sync) with better connection settings
test_engine = create_async_engine(
    TEST_DATABASE_URL, 
    echo=False, 
    future=True, 
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=30,
    max_overflow=0,
    pool_size=1,  # Single connection for tests to avoid conflicts
)

# Sync engine for routes that use sync sessions
sync_test_url = TEST_DATABASE_URL.replace("+asyncpg", "")
sync_test_engine = create_engine(
    sync_test_url, 
    echo=False, 
    pool_pre_ping=True,
    pool_size=1,
    max_overflow=0
)

TestAsyncSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

TestSyncSessionLocal = sessionmaker(
    bind=sync_test_engine, class_=Session, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Setup test database tables once per test session."""
    from sqlmodel import SQLModel
    
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield
    
    # Clean up after all tests
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a clean database session for each test.
    Uses transactions for isolation instead of table dropping.
    """
    async with TestAsyncSessionLocal() as session:
        # Start a transaction
        trans = await session.begin()
        try:
            yield session
        finally:
            # Always rollback to ensure clean state
            await trans.rollback()
            await session.close()


@pytest.fixture
def client():
    """Test client for FastAPI application with improved async handling."""
    from app.database import get_async_session

    async def get_test_async_session():
        async with TestAsyncSessionLocal() as session:
            yield session

    # Override the dependency
    app.dependency_overrides[get_async_session] = get_test_async_session
    
    try:
        # Create test client with proper async handling
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Always clean up overrides
        app.dependency_overrides.clear()


@pytest.fixture
def auth_tokens():
    """Generate valid JWT tokens for testing."""
    # Return mock tokens that match the expected format
    # In practice these would be real JWT tokens
    return {
        "viewer": "valid_jwt_token_viewer",
        "admin": "valid_jwt_token_admin",
        "invalid": "invalid_token",
    }


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
    # Mock time freezing for tests that need it
    from unittest.mock import Mock
    return Mock()
