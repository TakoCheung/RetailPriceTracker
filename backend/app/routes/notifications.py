"""
Notification API routes for real-time alerts and messaging.
"""

from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_session
from ..models import User
from ..services.notification import send_notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# Simple rate limiting storage (in production, use Redis)
notification_history: Dict[int, List[datetime]] = {}
RATE_LIMIT_WINDOW = timedelta(seconds=30)  # 30 second window for stricter rate limiting
RATE_LIMIT_COUNT = 1  # Only 1 notification per 30 seconds


def clear_rate_limit_history():
    """Clear rate limit history - useful for testing."""
    global notification_history
    notification_history.clear()


def check_rate_limit(user_id: int) -> bool:
    """Check if user has exceeded notification rate limit."""
    now = datetime.utcnow()

    if user_id not in notification_history:
        notification_history[user_id] = []

    # Remove old entries outside the window
    notification_history[user_id] = [
        timestamp
        for timestamp in notification_history[user_id]
        if now - timestamp < RATE_LIMIT_WINDOW
    ]

    # Check if under limit (must check BEFORE adding current notification)
    if len(notification_history[user_id]) >= RATE_LIMIT_COUNT:
        return False

    # Add current notification
    notification_history[user_id].append(now)
    return True


@router.post("/send", status_code=201)
def send_notification_endpoint(
    notification_data: Dict, session: Session = Depends(get_session)
):
    """Send notification through specified channels."""
    user_id = notification_data.get("user_id")
    channels = notification_data.get("channels", ["email"])

    # Check rate limit
    if not check_rate_limit(user_id):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Too many notifications sent recently.",
        )

    # Verify user exists
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create notification message
    product_id = notification_data.get("product_id")
    alert_type = notification_data.get("alert_type")
    old_price = notification_data.get("old_price")
    new_price = notification_data.get("new_price")

    message = f"Price alert for product {product_id}: {alert_type} - ${old_price} -> ${new_price}"

    # Send notifications
    results = send_notification(user_id, channels, message)

    return {
        "notification_sent": True,
        "channels_used": list(results.keys()),
        "user_id": user_id,
        "message": message,
    }


@router.delete("/rate-limits", status_code=204)
def clear_rate_limits():
    """Clear all rate limit history. For testing purposes only."""
    clear_rate_limit_history()
    return


@router.get("/history/{user_id}")
def get_notification_history(user_id: int, session: Session = Depends(get_session)):
    """Get notification history for a user."""
    # Verify user exists
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Mock notification history
    notifications = [
        {
            "id": 1,
            "message": "Price drop alert for Product 1",
            "channels": ["email"],
            "sent_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "status": "delivered",
        },
        {
            "id": 2,
            "message": "Price increase alert for Product 2",
            "channels": ["websocket"],
            "sent_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            "status": "delivered",
        },
    ]

    return {
        "user_id": user_id,
        "notifications": notifications,
        "total_count": len(notifications),
    }


@router.get("/preferences/{user_id}")
def get_notification_preferences(user_id: int, session: Session = Depends(get_session)):
    """Get user notification preferences."""
    # Verify user exists
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Mock preferences (in real implementation, store in database)
    return {
        "user_id": user_id,
        "email_enabled": True,
        "websocket_enabled": True,
        "sms_enabled": False,
        "push_enabled": True,
        "quiet_hours": {"enabled": False, "start": "22:00", "end": "08:00"},
    }


@router.patch("/preferences/{user_id}")
def update_notification_preferences(
    user_id: int, preferences: Dict, session: Session = Depends(get_session)
):
    """Update user notification preferences."""
    # Verify user exists
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # In real implementation, update preferences in database
    # For now, return the updated preferences
    return {
        "user_id": user_id,
        **preferences,
        "updated_at": datetime.utcnow().isoformat(),
    }
