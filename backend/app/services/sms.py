"""
SMS service for sending text notifications.
"""

import re
from typing import Dict, List


class SMSService:
    """Service for handling SMS notifications."""

    def __init__(self):
        # In production, this would be initialized with SMS provider settings (Twilio, etc.)
        self.provider = "mock_sms_provider"
        self.api_key = None
        self.from_number = "+1234567890"

    def send_alert(
        self,
        to_number: str,
        product_name: str,
        old_price: float,
        new_price: float,
        alert_type: str = "price_drop",
    ) -> bool:
        """Send price alert SMS notification."""
        try:
            if alert_type == "price_drop":
                message = f"🔥 Price Drop Alert! {product_name}: ${old_price:.2f} → ${new_price:.2f} (Save ${old_price - new_price:.2f})"
            else:
                message = f"📱 Price Update: {product_name}: ${old_price:.2f} → ${new_price:.2f}"

            # Truncate message if too long (SMS limit ~160 chars)
            if len(message) > 160:
                message = message[:157] + "..."

            # Mock SMS sending for testing
            print(f"Sending SMS to {to_number}: {message}")

            return True

        except Exception as e:
            print(f"Failed to send SMS: {str(e)}")
            return False

    def send_sms(self, to_number: str, message: str, priority: str = "normal") -> bool:
        """Send generic SMS notification."""
        try:
            # Mock SMS sending for testing
            print(f"Sending SMS to {to_number} (priority: {priority}): {message}")

            return True

        except Exception as e:
            print(f"Failed to send SMS: {str(e)}")
            return False

    async def send_alert_sms(self, phone_number: str, message: str) -> bool:
        """Send SMS alert notification (async compatibility)."""
        return self.send_sms(phone_number, message, priority="high")

    def send_bulk_sms(self, recipients: List[str], message: str) -> Dict[str, bool]:
        """Send bulk SMS notifications."""
        results = {}

        for recipient in recipients:
            results[recipient] = self.send_sms(recipient, message)

        return results

    def validate_phone_number(self, phone: str) -> bool:
        """Validate phone number format."""
        # Basic validation for US/international phone numbers
        pattern = r"^\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}$"
        return bool(
            re.match(
                pattern,
                phone.replace(" ", "")
                .replace("-", "")
                .replace("(", "")
                .replace(")", ""),
            )
        )

    def format_phone_number(self, phone: str) -> str:
        """Format phone number to standard format."""
        # Remove all non-digit characters except +
        cleaned = re.sub(r"[^\d+]", "", phone)

        # Add +1 if it's a 10-digit US number
        if len(cleaned) == 10:
            cleaned = "+1" + cleaned
        elif len(cleaned) == 11 and cleaned.startswith("1"):
            cleaned = "+" + cleaned

        return cleaned


# Global SMS service instance
sms_service = SMSService()
