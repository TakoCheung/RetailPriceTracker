"""
Notification API routes for real-time alerts and messaging.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..database import get_session
from ..models import User
from ..services.email import EmailService
from ..services.notification import send_notification
from ..services.sms import SMSService

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


class PriceAlertRequest(BaseModel):
    """Request model for price alert notifications."""

    user_email: str
    user_name: str
    product_name: str
    current_price: float
    threshold_price: float
    condition: str  # below, above, equal
    old_price: Optional[float] = None
    channels: list[str] = ["email"]  # email, sms, websocket


@router.post("/send-sms")
async def send_sms_notification(
    phone_number: str, message: str, session: Session = Depends(get_session)
):
    """Send a test SMS notification."""

    sms_service = SMSService()

    try:
        result = await sms_service.send_alert_sms(
            phone_number=phone_number, message=message
        )

        return {
            "success": True,
            "message": "SMS sent successfully",
            "recipient": phone_number,
            "result": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")


@router.post("/price-alert")
async def send_price_alert_notification(request: PriceAlertRequest):
    """Send a complete price alert notification across specified channels."""

    results = {"success": True, "channels_triggered": [], "errors": []}

    # Email notification
    if "email" in request.channels:
        try:
            email_service = EmailService()

            # Calculate savings
            savings = (
                (request.old_price - request.current_price)
                if request.old_price and request.old_price > request.current_price
                else 0
            )

            # Use the correct method signature for send_alert_email
            email_service.send_alert_email(
                to_email=request.user_email,
                product_name=request.product_name,
                old_price=request.old_price or request.threshold_price,
                new_price=request.current_price,
                alert_type="price_drop"
                if request.condition == "below"
                else "price_change",
                subject=f"Price Alert: {request.product_name}",
                threshold_price=request.threshold_price,
                condition=request.condition,
            )
            results["channels_triggered"].append("email")

        except Exception as e:
            results["errors"].append(f"Email failed: {str(e)}")

    # SMS notification
    if "sms" in request.channels:
        try:
            sms_service = SMSService()

            message = f"🚨 Price Alert: {request.product_name} is now ${request.current_price} (target: ${request.threshold_price})"
            if request.old_price:
                savings = request.old_price - request.current_price
                if savings > 0:
                    message = f"🔥 {request.product_name}: ${request.old_price} → ${request.current_price} (Save ${savings:.2f}!)"

            # For testing, use placeholder phone number
            await sms_service.send_alert_sms(
                phone_number="+1234567890", message=message
            )
            results["channels_triggered"].append("sms")

        except Exception as e:
            results["errors"].append(f"SMS failed: {str(e)}")

    # WebSocket notification
    if "websocket" in request.channels:
        try:
            from ..utils.websocket import websocket_manager

            alert_data = {
                "type": "price_alert",
                "product_name": request.product_name,
                "current_price": request.current_price,
                "threshold_price": request.threshold_price,
                "condition": request.condition,
                "old_price": request.old_price,
                "message": f"Price alert for {request.product_name}: ${request.current_price}",
            }

            # Broadcast to all connected clients (in production, send to specific user)
            await websocket_manager.broadcast(alert_data)
            results["channels_triggered"].append("websocket")

        except Exception as e:
            results["errors"].append(f"WebSocket failed: {str(e)}")

    if results["errors"]:
        results["success"] = False

    return results


@router.get("/test-connection")
async def test_notification_services():
    """Test the connectivity and basic functionality of notification services."""

    results = {
        "email_service": {"available": False, "error": None},
        "sms_service": {"available": False, "error": None},
        "websocket_service": {"available": False, "error": None},
    }

    # Test email service
    try:
        email_service = EmailService()
        results["email_service"]["available"] = True
    except Exception as e:
        results["email_service"]["error"] = str(e)

    # Test SMS service
    try:
        sms_service = SMSService()
        results["sms_service"]["available"] = True
    except Exception as e:
        results["sms_service"]["error"] = str(e)

    # Test WebSocket service
    try:
        from ..utils.websocket import websocket_manager

        results["websocket_service"]["available"] = True
        results["websocket_service"]["active_connections"] = len(
            websocket_manager.active_connections
        )
    except Exception as e:
        results["websocket_service"]["error"] = str(e)

    return results


@router.post("/test-all-channels")
async def test_all_notification_channels():
    """Send a test notification through all available channels."""

    test_request = PriceAlertRequest(
        user_email="test@example.com",
        user_name="Test User",
        product_name="Test Product",
        current_price=89.99,
        threshold_price=100.00,
        condition="below",
        old_price=120.00,
        channels=["email", "sms", "websocket"],
    )

    return await send_price_alert_notification(test_request)
