"""
Price Record API routes following TDD approach.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

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


class PriceRecordUpdate(BaseModel):
    price: Optional[float] = None
    currency: Optional[str] = None
    is_available: Optional[bool] = None

    @field_validator("price")
    @classmethod
    def validate_price(cls, v):
        if v is not None and v < 0:
            raise ValueError("Price must be non-negative")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        if v is not None:
            if len(v) != 3:
                raise ValueError("Currency must be a 3-letter code")
            return v.upper()
        return v


class PriceRecordResponse(BaseModel):
    id: int
    product_id: int
    provider_id: int
    price: float
    currency: str
    is_available: bool
    recorded_at: datetime


router = APIRouter()


@router.post(
    "/", response_model=PriceRecordResponse, status_code=status.HTTP_201_CREATED
)
def create_price_record(
    data: PriceRecordCreate, session: Session = Depends(get_session)
):
    """Create a new price record."""
    # Validate that product exists
    product = session.get(Product, data.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {data.product_id} not found",
        )

    # Validate that provider exists
    provider = session.get(Provider, data.provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider with id {data.provider_id} not found",
        )

    # Create price record
    db_price_record = PriceRecord(
        product_id=data.product_id,
        provider_id=data.provider_id,
        price=data.price,
        currency=data.currency,
        is_available=data.is_available,
        recorded_at=datetime.utcnow(),
    )
    session.add(db_price_record)
    session.commit()
    session.refresh(db_price_record)

    return db_price_record


@router.get("/", response_model=List[PriceRecordResponse])
def get_all_price_records(session: Session = Depends(get_session)):
    """Get all price records."""
    statement = select(PriceRecord)
    price_records = session.execute(statement).scalars().all()
    return price_records


@router.get("/{price_record_id}", response_model=PriceRecordResponse)
def get_price_record_by_id(
    price_record_id: int, session: Session = Depends(get_session)
):
    """Get a specific price record by ID."""
    price_record = session.get(PriceRecord, price_record_id)
    if not price_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Price record with id {price_record_id} not found",
        )
    return price_record


@router.patch("/{price_record_id}", response_model=PriceRecordResponse)
def update_price_record(
    price_record_id: int,
    data: PriceRecordUpdate,
    session: Session = Depends(get_session),
):
    """Update an existing price record."""
    price_record = session.get(PriceRecord, price_record_id)
    if not price_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Price record with id {price_record_id} not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(price_record, field, value)

    session.add(price_record)
    session.commit()
    session.refresh(price_record)

    return price_record


@router.delete("/{price_record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price_record(price_record_id: int, session: Session = Depends(get_session)):
    """Delete a price record."""
    price_record = session.get(PriceRecord, price_record_id)
    if not price_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Price record with id {price_record_id} not found",
        )

    session.delete(price_record)
    session.commit()
