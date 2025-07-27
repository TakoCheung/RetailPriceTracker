"""
User Preferences API routes for customizing user settings.
Following RESTful patterns established in other APIs.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import User, UserPreference
from ..schemas import (
    UserPreferencesCreate,
    UserPreferencesResponse,
    UserPreferencesUpdate,
)

router = APIRouter()


@router.post("/", status_code=201, response_model=UserPreferencesResponse)
def create_user_preferences(
    preferences_data: UserPreferencesCreate, session: Session = Depends(get_session)
):
    """Create user preferences."""

    # Verify user exists
    user = session.execute(
        select(User).where(User.id == preferences_data.user_id)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check if preferences already exist for this user
    existing_prefs = session.execute(
        select(UserPreference).where(UserPreference.user_id == preferences_data.user_id)
    ).scalar_one_or_none()

    if existing_prefs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User preferences already exists for this user",
        )

    # Create the preferences
    db_preferences = UserPreference(
        user_id=preferences_data.user_id,
        default_currency=preferences_data.default_currency,
        user_timezone=preferences_data.user_timezone,
        email_notifications=preferences_data.email_notifications,
        push_notifications=preferences_data.push_notifications,
        webhook_url=preferences_data.webhook_url,
        items_per_page=preferences_data.items_per_page,
        chart_type=preferences_data.chart_type,
        default_time_range=preferences_data.default_time_range,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    try:
        session.add(db_preferences)
        session.commit()
        session.refresh(db_preferences)
        return db_preferences
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User preferences already exists for this user",
        )


@router.get("/", response_model=List[UserPreferencesResponse])
def get_all_preferences(session: Session = Depends(get_session)):
    """Get all user preferences."""
    preferences = session.execute(select(UserPreference)).scalars().all()
    return preferences


@router.get("/user/{user_id}", response_model=UserPreferencesResponse)
def get_user_preferences_by_user_id(
    user_id: int, session: Session = Depends(get_session)
):
    """Get user preferences by user ID."""
    preferences = session.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).scalar_one_or_none()

    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User preferences not found"
        )

    return preferences


@router.get("/{preferences_id}", response_model=UserPreferencesResponse)
def get_preferences(preferences_id: int, session: Session = Depends(get_session)):
    """Get specific user preferences by ID."""
    preferences = session.execute(
        select(UserPreference).where(UserPreference.id == preferences_id)
    ).scalar_one_or_none()

    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User preferences not found"
        )

    return preferences


@router.patch("/{preferences_id}", response_model=UserPreferencesResponse)
def update_preferences(
    preferences_id: int,
    preferences_update: UserPreferencesUpdate,
    session: Session = Depends(get_session),
):
    """Update user preferences."""
    preferences = session.execute(
        select(UserPreference).where(UserPreference.id == preferences_id)
    ).scalar_one_or_none()

    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User preferences not found"
        )

    # Update fields that were provided
    update_data = preferences_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preferences, field, value)

    preferences.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(preferences)

    return preferences


@router.delete("/{preferences_id}", status_code=204)
def delete_preferences(preferences_id: int, session: Session = Depends(get_session)):
    """Delete user preferences."""
    preferences = session.execute(
        select(UserPreference).where(UserPreference.id == preferences_id)
    ).scalar_one_or_none()

    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User preferences not found"
        )

    session.delete(preferences)
    session.commit()
