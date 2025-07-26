"""
Product API routes following TDD approach.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..database import get_session
from ..models import Product, ProductStatus


# Request/Response schemas
class ProductCreate(BaseModel):
    name: str
    url: str | None = None
    description: str | None = None
    category: str | None = None
    image_url: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    description: str | None = None
    category: str | None = None
    image_url: str | None = None
    status: ProductStatus | None = None


class ProductResponse(BaseModel):
    id: int
    name: str
    url: str | None
    description: str | None
    category: str | None
    image_url: str | None
    status: ProductStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


router = APIRouter()


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_data: ProductCreate, session: Session = Depends(get_session)
):
    """Create a new product."""
    # Validate using our custom method
    temp_product = Product(name=product_data.name)
    if not temp_product.is_valid_name():
        raise HTTPException(
            status_code=422,
            detail="validation error: Product name must be at least 2 characters long",
        )

    # Create the product
    product = Product(
        name=product_data.name,
        url=product_data.url,
        description=product_data.description,
        category=product_data.category,
        image_url=product_data.image_url,
    )

    session.add(product)
    session.commit()
    session.refresh(product)

    return product


@router.get("/", response_model=List[ProductResponse])
def get_products(session: Session = Depends(get_session)):
    """Get all products."""
    statement = select(Product)
    products = session.execute(statement).scalars().all()
    return products


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, session: Session = Depends(get_session)):
    """Get a specific product by ID."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_update: ProductUpdate,
    session: Session = Depends(get_session),
):
    """Update an existing product."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Update fields that are provided
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    # Update timestamp
    product.updated_at = datetime.utcnow()

    session.add(product)
    session.commit()
    session.refresh(product)

    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, session: Session = Depends(get_session)):
    """Delete a product."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    session.delete(product)
    session.commit()
    return None


@router.get("/{product_id}/price-history")
def get_product_price_history(product_id: int, session: Session = Depends(get_session)):
    """Get price history for a product."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # For now, return empty list - will implement when we add price records
    return []
