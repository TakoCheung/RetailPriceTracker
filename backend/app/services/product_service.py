"""
Product management service with advanced filtering, searching, and price tracking.
Implements comprehensive product CRUD operations with brand support and soft deletes.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceRecord, Product, ProductStatus, Provider
from app.utils.websocket import websocket_manager


class ProductService:
    """Advanced product management service."""

    def __init__(self):
        self.supported_categories = [
            "Electronics",
            "Clothing",
            "Home & Garden",
            "Sports",
            "Books",
            "Health & Beauty",
            "Automotive",
            "Toys",
            "Food",
            "Other",
        ]

    async def create_product(
        self,
        db_session: AsyncSession,
        name: str,
        sku: Optional[str] = None,
        url: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> Product:
        """Create a new product with enhanced metadata."""

        # Validate category
        if category and category not in self.supported_categories:
            raise ValueError(
                f"Category must be one of: {', '.join(self.supported_categories)}"
            )

        # Check for duplicate SKU if provided
        if sku:
            existing = await db_session.execute(
                select(Product).where(
                    and_(Product.sku == sku, Product.deleted_at.is_(None))
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Product with SKU '{sku}' already exists")

        product = Product(
            name=name,
            sku=sku,
            url=url,
            description=description,
            category=category,
            brand=brand,
            image_url=image_url,
            status=ProductStatus.ACTIVE,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        return product

    async def get_product(
        self, db_session: AsyncSession, product_id: int, include_deleted: bool = False
    ) -> Optional[Product]:
        """Get product by ID with soft delete filtering."""

        query = select(Product).where(Product.id == product_id)

        if not include_deleted:
            query = query.where(Product.deleted_at.is_(None))

        result = await db_session.execute(query)
        return result.scalar_one_or_none()

    async def search_products(
        self,
        db_session: AsyncSession,
        search_term: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        is_active: Optional[bool] = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Advanced product search with filtering and pagination."""

        # Base query with price information
        base_query = (
            select(Product, func.max(PriceRecord.price).label("current_price"))
            .outerjoin(PriceRecord, Product.id == PriceRecord.product_id)
            .where(Product.deleted_at.is_(None))
            .group_by(Product.id)
        )

        # Apply filters
        if search_term:
            search_filter = or_(
                Product.name.ilike(f"%{search_term}%"),
                Product.description.ilike(f"%{search_term}%"),
                Product.brand.ilike(f"%{search_term}%"),
            )
            base_query = base_query.where(search_filter)

        if category:
            base_query = base_query.where(Product.category == category)

        if brand:
            base_query = base_query.where(Product.brand.ilike(f"%{brand}%"))

        if is_active is not None:
            base_query = base_query.where(Product.is_active == is_active)

        # Price filtering (requires subquery for current prices)
        if min_price is not None or max_price is not None:
            # This is a simplified approach - in production, you'd want to optimize this
            if min_price is not None:
                base_query = base_query.having(func.max(PriceRecord.price) >= min_price)
            if max_price is not None:
                base_query = base_query.having(func.max(PriceRecord.price) <= max_price)

        # Count total results
        count_query = select(func.count()).select_from(base_query.subquery())
        total_count = (await db_session.execute(count_query)).scalar()

        # Apply pagination and ordering
        results_query = (
            base_query.order_by(desc(Product.updated_at)).limit(limit).offset(offset)
        )
        result = await db_session.execute(results_query)

        products_with_prices = []
        for product, current_price in result:
            product_dict = {
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "url": product.url,
                "description": product.description,
                "category": product.category,
                "brand": product.brand,
                "image_url": product.image_url,
                "status": product.status,
                "is_active": product.is_active,
                "current_price": float(current_price) if current_price else None,
                "created_at": product.created_at,
                "updated_at": product.updated_at,
            }
            products_with_prices.append(product_dict)

        return {
            "products": products_with_prices,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_next": (offset + limit) < total_count,
            "has_previous": offset > 0,
        }

    async def update_product(
        self, db_session: AsyncSession, product_id: int, **updates
    ) -> Optional[Product]:
        """Update product with validation."""

        product = await self.get_product(db_session, product_id)
        if not product:
            return None

        # Validate category if being updated
        if (
            "category" in updates
            and updates["category"] not in self.supported_categories
        ):
            raise ValueError(
                f"Category must be one of: {', '.join(self.supported_categories)}"
            )

        # Check SKU uniqueness if being updated
        if "sku" in updates and updates["sku"]:
            existing = await db_session.execute(
                select(Product).where(
                    and_(
                        Product.sku == updates["sku"],
                        Product.id != product_id,
                        Product.deleted_at.is_(None),
                    )
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Product with SKU '{updates['sku']}' already exists")

        # Apply updates
        for field, value in updates.items():
            if hasattr(product, field):
                setattr(product, field, value)

        product.updated_at = datetime.now(timezone.utc)

        await db_session.commit()
        await db_session.refresh(product)

        return product

    async def soft_delete_product(
        self, db_session: AsyncSession, product_id: int
    ) -> bool:
        """Soft delete a product."""

        product = await self.get_product(db_session, product_id)
        if not product:
            return False

        product.deleted_at = datetime.now(timezone.utc)
        product.is_active = False
        product.status = ProductStatus.DISCONTINUED

        await db_session.commit()
        return True

    async def restore_product(self, db_session: AsyncSession, product_id: int) -> bool:
        """Restore a soft-deleted product."""

        product = await self.get_product(db_session, product_id, include_deleted=True)
        if not product or not product.deleted_at:
            return False

        product.deleted_at = None
        product.is_active = True
        product.status = ProductStatus.ACTIVE
        product.updated_at = datetime.now(timezone.utc)

        await db_session.commit()
        return True

    async def get_product_price_history(
        self,
        db_session: AsyncSession,
        product_id: int,
        days: int = 30,
        provider_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get price history for a product."""

        query = (
            select(PriceRecord, Provider.name.label("provider_name"))
            .join(Provider, PriceRecord.provider_id == Provider.id)
            .where(PriceRecord.product_id == product_id)
            .where(
                PriceRecord.recorded_at
                >= datetime.now(timezone.utc).date() - timedelta(days=days)
            )
        )

        if provider_id:
            query = query.where(PriceRecord.provider_id == provider_id)

        query = query.order_by(desc(PriceRecord.recorded_at))

        result = await db_session.execute(query)

        price_history = []
        for record, provider_name in result:
            price_history.append(
                {
                    "price": float(record.price),
                    "recorded_at": record.recorded_at,
                    "provider_name": provider_name,
                    "currency": record.currency,
                    "availability": record.availability,
                }
            )

        return price_history

    async def add_price_record(
        self,
        db_session: AsyncSession,
        product_id: int,
        provider_id: int,
        price: float,
        currency: str = "USD",
        availability: bool = True,
    ) -> Optional[PriceRecord]:
        """Add a new price record and trigger notifications if needed."""

        # Verify product exists
        product = await self.get_product(db_session, product_id)
        if not product:
            return None

        # Get the last price for comparison
        last_price_query = (
            select(PriceRecord)
            .where(
                and_(
                    PriceRecord.product_id == product_id,
                    PriceRecord.provider_id == provider_id,
                )
            )
            .order_by(desc(PriceRecord.recorded_at))
            .limit(1)
        )

        last_price_result = await db_session.execute(last_price_query)
        last_price_record = last_price_result.scalar_one_or_none()

        # Create new price record
        price_record = PriceRecord(
            product_id=product_id,
            provider_id=provider_id,
            price=price,
            currency=currency,
            availability=availability,
            recorded_at=datetime.now(timezone.utc),
        )

        db_session.add(price_record)
        await db_session.commit()
        await db_session.refresh(price_record)

        # Check for significant price changes and notify
        if last_price_record and abs(price - last_price_record.price) > 0.01:
            await self._notify_price_change(
                product, price_record, last_price_record.price
            )

        return price_record

    async def _notify_price_change(
        self, product: Product, new_price_record: PriceRecord, old_price: float
    ):
        """Send notifications for price changes."""

        price_change = new_price_record.price - old_price
        change_percent = (price_change / old_price) * 100

        # Prepare notification data
        notification_data = {
            "type": "price_change",
            "product_id": product.id,
            "product_name": product.name,
            "brand": product.brand,
            "category": product.category,
            "old_price": float(old_price),
            "new_price": float(new_price_record.price),
            "price_change": float(price_change),
            "change_percent": float(change_percent),
            "currency": new_price_record.currency,
            "timestamp": new_price_record.recorded_at.isoformat(),
        }

        # Send WebSocket notification to all connected clients
        try:
            await websocket_manager.broadcast(notification_data)
        except Exception as e:
            print(f"Failed to send WebSocket notification: {e}")

        # Log significant price changes
        if abs(change_percent) > 10:  # More than 10% change
            print(
                f"Significant price change detected: {product.name} - {change_percent:.1f}%"
            )

    async def get_categories_with_counts(
        self, db_session: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Get all categories with product counts."""

        query = (
            select(Product.category, func.count(Product.id).label("product_count"))
            .where(and_(Product.deleted_at.is_(None), Product.is_active))
            .group_by(Product.category)
            .order_by(desc(func.count(Product.id)))
        )

        result = await db_session.execute(query)

        categories = []
        for category, count in result:
            categories.append(
                {"category": category or "Uncategorized", "product_count": count}
            )

        return categories

    async def get_brands_with_counts(
        self, db_session: AsyncSession, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all brands with product counts, optionally filtered by category."""

        query = select(
            Product.brand, func.count(Product.id).label("product_count")
        ).where(and_(Product.deleted_at.is_(None), Product.is_active))

        if category:
            query = query.where(Product.category == category)

        query = query.group_by(Product.brand).order_by(desc(func.count(Product.id)))

        result = await db_session.execute(query)

        brands = []
        for brand, count in result:
            if brand:  # Only include products with brands
                brands.append({"brand": brand, "product_count": count})

        return brands


# Global service instance
product_service = ProductService()
