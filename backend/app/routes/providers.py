"""
Provider API routes following TDD approach.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session

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
