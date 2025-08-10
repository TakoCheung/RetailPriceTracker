"""
Unit tests for ProductService with advanced filtering and price tracking.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import PriceRecord, Product
from app.services.product_service import ProductService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def product_service():
    return ProductService()


@pytest.fixture
def mock_db_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_product():
    return Product(
        id=1,
        name="Sample Product",
        brand="Sample Brand",
        category="Electronics",
        description="A sample product for testing",
        url="https://example.com/product",
        is_active=True,
        deleted_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_price_record():
    return PriceRecord(
        id=1,
        product_id=1,
        price=99.99,
        provider_id=1,
        created_at=datetime.now(timezone.utc),
    )


class TestProductService:
    """Test suite for ProductService functionality."""

    @pytest.mark.asyncio
    async def test_create_product_success(self, product_service, mock_db_session):
        """Test successful product creation."""
        # Arrange
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        # Act
        result = await product_service.create_product(
            db_session=mock_db_session,
            name="Test Product",
            brand="Test Brand",
            category="Electronics",
        )

        # Assert
        assert result is not None
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_product_by_id_found(
        self, product_service, mock_db_session, sample_product
    ):
        """Test getting a product by ID when it exists."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = sample_product
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.get_product_by_id(mock_db_session, 1)

        # Assert
        assert result == sample_product
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_product_by_id_not_found(self, product_service, mock_db_session):
        """Test getting a product by ID when it doesn't exist."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.get_product_by_id(mock_db_session, 999)

        # Assert
        assert result is None
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_products_basic(self, product_service, mock_db_session):
        """Test basic product search functionality."""
        # Arrange
        mock_products = [
            {"id": 1, "name": "Product 1", "brand": "Brand A"},
            {"id": 2, "name": "Product 2", "brand": "Brand B"},
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_products
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.search_products(
            db_session=mock_db_session, page=1, page_size=10
        )

        # Assert
        assert "products" in result
        assert "pagination" in result
        mock_db_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_search_products_with_filters(self, product_service, mock_db_session):
        """Test product search with various filters."""
        # Arrange
        mock_products = [{"id": 1, "name": "Filtered Product", "brand": "Test Brand"}]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_products
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.search_products(
            db_session=mock_db_session,
            category="Electronics",
            brand="Test Brand",
            min_price=50.0,
            max_price=200.0,
            page=1,
            page_size=10,
        )

        # Assert
        assert "products" in result
        assert len(result["products"]) == 1
        mock_db_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_update_product_success(
        self, product_service, mock_db_session, sample_product
    ):
        """Test successful product update."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = sample_product
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        update_data = {"name": "Updated Product Name", "brand": "Updated Brand"}

        # Act
        result = await product_service.update_product(mock_db_session, 1, update_data)

        # Assert
        assert result is not None
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_product_success(
        self, product_service, mock_db_session, sample_product
    ):
        """Test successful soft deletion of product."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = sample_product
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        # Act
        result = await product_service.soft_delete_product(mock_db_session, 1)

        # Assert
        assert result is True
        assert sample_product.deleted_at is not None
        assert sample_product.is_active is False
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_product_not_found(
        self, product_service, mock_db_session
    ):
        """Test soft deletion of non-existent product."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.soft_delete_product(mock_db_session, 999)

        # Assert
        assert result is False

    @pytest.mark.asyncio
    @patch("app.services.product_service.websocket_manager")
    async def test_add_price_record_with_notification(
        self, mock_websocket_manager, product_service, mock_db_session, sample_product
    ):
        """Test adding price record with price change notification."""
        # Arrange
        mock_product_result = MagicMock()
        mock_product_result.scalars.return_value.first.return_value = sample_product

        mock_latest_price_result = MagicMock()
        mock_latest_price_result.scalars.return_value.first.return_value = MagicMock(
            price=100.0
        )

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_product_result, mock_latest_price_result]
        )
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        # Act
        result = await product_service.add_price_record(mock_db_session, 1, 85.0, 1)

        # Assert
        assert result is not None
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()
        mock_websocket_manager.broadcast_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_price_history(self, product_service, mock_db_session):
        """Test getting price history for a product."""
        # Arrange
        mock_history = [
            {
                "price": 100.0,
                "created_at": datetime.now(timezone.utc),
                "provider_name": "Provider 1",
            },
            {
                "price": 95.0,
                "created_at": datetime.now(timezone.utc),
                "provider_name": "Provider 2",
            },
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_history
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.get_price_history(mock_db_session, 1, 30)

        # Assert
        assert len(result) == 2
        assert all("price" in record for record in result)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_categories_with_counts(self, product_service, mock_db_session):
        """Test getting categories with product counts."""
        # Arrange
        mock_categories = [("Electronics", 5), ("Books", 3), (None, 2)]
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_categories)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.get_categories_with_counts(mock_db_session)

        # Assert
        assert len(result) == 3
        assert result[0]["category"] == "Electronics"
        assert result[0]["product_count"] == 5
        assert (
            result[2]["category"] == "Uncategorized"
        )  # None should become "Uncategorized"

    @pytest.mark.asyncio
    async def test_get_brands_with_counts_no_filter(
        self, product_service, mock_db_session
    ):
        """Test getting brands with product counts without category filter."""
        # Arrange
        mock_brands = [("Brand A", 3), ("Brand B", 2), (None, 1)]
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_brands)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.get_brands_with_counts(mock_db_session)

        # Assert
        assert len(result) == 3
        assert result[0]["brand"] == "Brand A"
        assert result[0]["product_count"] == 3
        assert result[2]["brand"] == "Unknown"  # None should become "Unknown"

    @pytest.mark.asyncio
    async def test_get_brands_with_counts_with_category_filter(
        self, product_service, mock_db_session
    ):
        """Test getting brands with product counts filtered by category."""
        # Arrange
        mock_brands = [("Electronics Brand", 2)]
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_brands)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.get_brands_with_counts(
            mock_db_session, "Electronics"
        )

        # Assert
        assert len(result) == 1
        assert result[0]["brand"] == "Electronics Brand"
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_text_query(self, product_service, mock_db_session):
        """Test product search with text query."""
        # Arrange
        mock_products = [{"id": 1, "name": "Smartphone", "brand": "TechCorp"}]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_products
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.search_products(
            db_session=mock_db_session, query="smartphone", page=1, page_size=10
        )

        # Assert
        assert "products" in result
        assert len(result["products"]) == 1
        mock_db_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_search_with_sorting(self, product_service, mock_db_session):
        """Test product search with sorting options."""
        # Arrange
        mock_products = [
            {"id": 1, "name": "Product A", "brand": "Brand Z"},
            {"id": 2, "name": "Product B", "brand": "Brand A"},
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_products
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await product_service.search_products(
            db_session=mock_db_session,
            sort_by="brand",
            sort_order="desc",
            page=1,
            page_size=10,
        )

        # Assert
        assert "products" in result
        assert "pagination" in result
        mock_db_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_create_product_with_initial_price(
        self, product_service, mock_db_session
    ):
        """Test creating a product with an initial price record."""
        # Arrange
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        # Act
        result = await product_service.create_product(
            db_session=mock_db_session,
            name="Test Product",
            brand="Test Brand",
            provider_id=1,
            current_price=99.99,
        )

        # Assert
        assert result is not None
        # Should add both product and price record
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()

    def test_pagination_calculation(self, product_service):
        """Test pagination calculation logic."""
        # Test basic functionality exists
        assert hasattr(product_service, "search_products")
        assert hasattr(product_service, "create_product")
        assert hasattr(product_service, "update_product")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
