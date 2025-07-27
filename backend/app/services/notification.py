"""
Notification service for sending alerts through various channels.
"""

from typing import Dict, List


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send email notification."""
    # Mock implementation for testing
    print(f"Sending email to {to_email}: {subject}")
    return True


def send_websocket_notification(user_id: int, message: Dict) -> bool:
    """Send WebSocket notification."""
    # Mock implementation for testing
    print(f"Sending WebSocket notification to user {user_id}: {message}")
    return True


def send_push_notification(user_id: int, message: str) -> bool:
    """Send push notification."""
    # Mock implementation for testing
    print(f"Sending push notification to user {user_id}: {message}")
    return True


def send_notification(
    user_id: int, channels: List[str], message: str, subject: str = None
) -> Dict[str, bool]:
    """Send notification through multiple channels."""
    results = {}

    for channel in channels:
        if channel == "email":
            # In real implementation, get user email from database
            results["email"] = send_email(
                "user@example.com", subject or "Price Alert", message
            )
        elif channel == "websocket":
            results["websocket"] = send_websocket_notification(
                user_id, {"message": message}
            )
        elif channel == "push":
            results["push"] = send_push_notification(user_id, message)

    return results
