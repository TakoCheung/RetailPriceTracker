"""
Email service for sending notifications and alerts.
"""

from datetime import datetime
from typing import Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class EmailService:
    """Service for handling email notifications."""
    
    def __init__(self):
        # In production, this would be initialized with SMTP settings
        self.smtp_host = "localhost"
        self.smtp_port = 587
        self.username = "noreply@retailpricetracker.com"
        self.password = None
        
    def send_alert_email(
        self, 
        to_email: str, 
        product_name: str, 
        old_price: float, 
        new_price: float, 
        alert_type: str = "price_drop"
    ) -> bool:
        """Send price alert email notification."""
        try:
            subject = f"Price Alert: {product_name}"
            
            if alert_type == "price_drop":
                body = f"""
                Good news! The price for {product_name} has dropped:
                
                Previous Price: ${old_price:.2f}
                New Price: ${new_price:.2f}
                Savings: ${old_price - new_price:.2f}
                
                Don't miss out on this deal!
                """
            else:
                body = f"""
                Price Update for {product_name}:
                
                Previous Price: ${old_price:.2f}
                New Price: ${new_price:.2f}
                """
            
            # Mock email sending for testing
            print(f"Sending email to {to_email}: {subject}")
            print(f"Body: {body.strip()}")
            
            return True
            
        except Exception as e:
            print(f"Failed to send email: {str(e)}")
            return False
    
    def send_notification_email(
        self, 
        to_email: str, 
        subject: str, 
        body: str,
        template: Optional[str] = None
    ) -> bool:
        """Send generic notification email."""
        try:
            # Mock email sending for testing
            print(f"Sending notification email to {to_email}: {subject}")
            if template:
                print(f"Using template: {template}")
            print(f"Body: {body}")
            
            return True
            
        except Exception as e:
            print(f"Failed to send notification email: {str(e)}")
            return False
            
    def send_bulk_emails(self, recipients: List[str], subject: str, body: str) -> Dict[str, bool]:
        """Send bulk email notifications."""
        results = {}
        
        for recipient in recipients:
            results[recipient] = self.send_notification_email(recipient, subject, body)
            
        return results
        
    def validate_email(self, email: str) -> bool:
        """Validate email address format."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))


# Global email service instance
email_service = EmailService()
