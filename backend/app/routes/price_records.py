"""
Price Record API routes following TDD approach.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session

from ..database import get_session
from ..models import PriceRecord, Product, Provider


# Request/Response schemas
class PriceRecordCreate(BaseModel):
    product_id: int
    provider_id: int
    price: float
    currency: str
    is_available: bool

    @field_validator("price")
    @classmethod
    def validate_price(cls, v):
        if v < 0:
            raise ValueError("Price must be non-negative")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        if len(v) != 3:
            raise ValueError("Currency must be a 3-letter code")
        return v.upper()


class PriceRecordResponse(BaseModel):
    id: int
    product_id: int
    provider_id: int
    price: float
    currency: str
    is_available: bool
    recorded_at: datetime


router = APIRouter()


@router.post("/", response_model=PriceRecordResponse, status_code=status.HTTP_201_CREATED)
def create_price_record(data: PriceRecordCreate, session: Session = Depends(get_session)):
    """Create a new price record."""
    # Validate that product exists
    product = session.get(Product, data.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Validate that provider exists
    provider = session.get(Provider, data.provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found"
        )

    price_record = PriceRecord(
        product_id=data.product_id,
        provider_id=data.provider_id,
        price=data.price,
        currency=data.currency,
        is_available=data.is_available,
        recorded_at=datetime.utcnow(),
    )

    session.add(price_record)
    session.commit()
    session.refresh(price_record)

    return price_record
