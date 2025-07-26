"""
Provider API routes following TDD approach.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from ..database import get_session
from ..models import Provider


# Request/Response schemas
class ProviderCreate(BaseModel):
    name: str
    base_url: str
    rate_limit: int
    api_key: Optional[str] = None

    @field_validator("rate_limit")
    @classmethod
    def validate_rate_limit(cls, v):
        if v <= 0:
            raise ValueError("Rate limit must be greater than 0")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip()


class ProviderResponse(BaseModel):
    id: int
    name: str
    base_url: str
    api_key: Optional[str] = None
    rate_limit: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


router = APIRouter()


@router.post("/", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(data: ProviderCreate, session: Session = Depends(get_session)):
    """Create a new provider."""
    provider = Provider(
        name=data.name,
        base_url=data.base_url,
        rate_limit=data.rate_limit,
        api_key=data.api_key,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(provider)
    session.commit()
    session.refresh(provider)

    return provider


@router.get("/", response_model=List[ProviderResponse])
def get_providers(session: Session = Depends(get_session)):
    """Get all providers."""
    statement = select(Provider)
    providers = session.execute(statement).scalars().all()
    return providers


@router.get("/{provider_id}", response_model=ProviderResponse)
def get_provider(provider_id: int, session: Session = Depends(get_session)):
    """Get a provider by ID."""
    provider = session.get(Provider, provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )
    return provider


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    rate_limit: Optional[int] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("rate_limit")
    @classmethod
    def validate_rate_limit(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Rate limit must be greater than 0")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None and len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip() if v else v


@router.patch("/{provider_id}", response_model=ProviderResponse)
def update_provider(
    provider_id: int, data: ProviderUpdate, session: Session = Depends(get_session)
):
    """Update a provider."""
    provider = session.get(Provider, provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )

    # Update fields if provided
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(provider, field, value)

    provider.updated_at = datetime.utcnow()

    session.add(provider)
    session.commit()
    session.refresh(provider)

    return provider


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: int, session: Session = Depends(get_session)):
    """Delete a provider."""
    provider = session.get(Provider, provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )

    session.delete(provider)
    session.commit()
    return None
