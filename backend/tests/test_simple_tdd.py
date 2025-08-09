"""
Simple TDD test cases to demonstrate Test-Driven Development approach.
"""

import pytest
from app.models import Product, Provider, User, UserRole
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine


@pytest.fixture
def simple_db_session():
    """Create a simple in-memory database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=True)
    SQLModel.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


class TestSimpleTDD:
    """Simple TDD test cases to demonstrate the approach."""

    def test_create_product_with_valid_data(self, simple_db_session):
        """Test creating a product with valid data."""
        # Arrange
        product_data = {
            "name": "iPhone 15",
            "url": "https://apple.com/iphone-15",
            "description": "Latest iPhone model",
            "category": "Electronics",
        }

        # Act
        product = Product(**product_data)
        simple_db_session.add(product)
        simple_db_session.commit()
        simple_db_session.refresh(product)

        # Assert
        assert product.id is not None
        assert product.name == "iPhone 15"
        assert product.category == "Electronics"
        assert product.created_at is not None

    def test_create_provider_with_valid_data(self, simple_db_session):
        """Test creating a provider with valid data."""
        # Arrange
        provider_data = {
            "name": "Amazon",
            "base_url": "https://api.amazon.com",
            "rate_limit": 1000,
        }

        # Act
        provider = Provider(**provider_data)
        simple_db_session.add(provider)
        simple_db_session.commit()
        simple_db_session.refresh(provider)

        # Assert
        assert provider.id is not None
        assert provider.name == "Amazon"
        assert provider.is_active is True
        assert provider.created_at is not None

    def test_create_user_with_valid_data(self, simple_db_session):
        """Test creating a user with valid data."""
        # Arrange
        user_data = {
            "email": "user@example.com",
            "name": "John Doe",
            "role": UserRole.VIEWER,
        }

        # Act
        user = User(**user_data)
        simple_db_session.add(user)
        simple_db_session.commit()
        simple_db_session.refresh(user)

        # Assert
        assert user.id is not None
        assert user.email == "user@example.com"
        assert user.name == "John Doe"
        assert user.role == UserRole.VIEWER
        assert user.is_active is True

    def test_product_name_validation(self, simple_db_session):
        """Test that product name validation works."""
        # For now, let's test a simpler constraint that SQLModel respects
        # This test demonstrates TDD - we'll implement a custom method
        product = Product(name="Valid Product Name")

        # Test our custom validation method (to be implemented)
        assert product.is_valid_name() is True

        product_invalid = Product(name="X")
        assert product_invalid.is_valid_name() is False

    def test_provider_rate_limit_validation(self, simple_db_session):
        """Test that provider rate limit validation works."""
        # Test our custom validation method (to be implemented)
        provider = Provider(
            name="Test Provider", base_url="https://test.com", rate_limit=100
        )

        assert provider.is_valid_rate_limit() is True

        # Test that invalid rate_limit raises ValueError during creation
        with pytest.raises(ValueError, match="Rate limit must be greater than or equal to 1"):
            Provider(
                name="Test Provider", base_url="https://test.com", rate_limit=0
            )
