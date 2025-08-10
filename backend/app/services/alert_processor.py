"""
Alert processing service for handling price change notifications.
Integrates with email, SMS, and WebSocket notification systems.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import PriceAlert, PriceRecord, User, Product, AlertCondition, AlertStatus
from app.services.email import EmailService
from app.services.sms import SMSService
from app.utils.websocket import websocket_manager


class AlertProcessingService:
    """Service for processing price alerts and triggering notifications."""
    
    def __init__(self):
        self.email_service = EmailService()
        self.sms_service = SMSService()
    
    async def process_price_change(
        self, 
        db_session: AsyncSession,
        product_id: int,
        new_price: float,
        old_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Process a price change and trigger relevant alerts."""
        results = {
            "alerts_processed": 0,
            "notifications_sent": 0,
            "triggered_alerts": [],
            "failed_notifications": []
        }
        
        # Get active alerts for this product
        statement = select(PriceAlert).where(
            PriceAlert.product_id == product_id,
            PriceAlert.is_active,
            PriceAlert.status == AlertStatus.ACTIVE
        )
        active_alerts = (await db_session.execute(statement)).scalars().all()
        
        for alert in active_alerts:
            should_trigger = self._should_trigger_alert(alert, new_price)
            
            if should_trigger:
                # Check cooldown period
                if self._is_in_cooldown(alert):
                    continue
                    
                # Process the alert
                await self._trigger_alert(db_session, alert, new_price, old_price)
                
                results["alerts_processed"] += 1
                results["triggered_alerts"].append({
                    "alert_id": alert.id,
                    "user_id": alert.user_id,
                    "product_id": alert.product_id,
                    "threshold_price": alert.threshold_price,
                    "current_price": new_price,
                    "condition": alert.condition.value
                })
                
        return results
    
    def _should_trigger_alert(self, alert: PriceAlert, current_price: float) -> bool:
        """Determine if an alert should be triggered based on conditions."""
        if not alert.threshold_price:
            return False
            
        if alert.condition == AlertCondition.BELOW:
            return current_price <= alert.threshold_price
        elif alert.condition == AlertCondition.ABOVE:  
            return current_price >= alert.threshold_price
        elif alert.condition == AlertCondition.EXACT:
            return abs(current_price - alert.threshold_price) < 0.01
            
        return False
    
    def _is_in_cooldown(self, alert: PriceAlert) -> bool:
        """Check if alert is in cooldown period."""
        if not alert.updated_at:
            return False
            
        cooldown_end = alert.updated_at + timedelta(minutes=alert.cooldown_minutes)
        return datetime.now(timezone.utc) < cooldown_end
    
    async def _trigger_alert(
        self,
        db_session: AsyncSession,
        alert: PriceAlert,
        current_price: float,
        old_price: Optional[float] = None
    ):
        """Trigger all notifications for an alert."""
        
        # Get user and product details
        user_stmt = select(User).where(User.id == alert.user_id)
        user = (await db_session.execute(user_stmt)).scalar_one_or_none()
        
        product_stmt = select(Product).where(Product.id == alert.product_id)
        product = (await db_session.execute(product_stmt)).scalar_one_or_none()
        
        if not user or not product:
            return
            
        # Prepare alert data
        alert_data = {
            "type": "price_alert",
            "alert_id": alert.id,
            "user_id": alert.user_id,
            "product": {
                "id": product.id,
                "name": product.name,
                "category": getattr(product, 'category', None),
                "brand": getattr(product, 'brand', None)
            },
            "current_price": current_price,
            "threshold_price": alert.threshold_price,
            "condition": alert.condition.value,
            "savings": (old_price - current_price) if old_price and old_price > current_price else 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Send notifications based on channels
        for channel in alert.notification_channels:
            await self._send_notification(channel, user, product, alert_data, current_price, old_price)
            
        # Update alert timestamp for cooldown
        alert.updated_at = datetime.now(timezone.utc)
        await db_session.commit()
    
    async def _send_notification(
        self,
        channel: str,
        user: User,
        product: Product,
        alert_data: Dict[str, Any],
        current_price: float,
        old_price: Optional[float]
    ):
        """Send notification via specific channel."""
        
        try:
            if channel == "email":
                await self._send_email_notification(user, product, current_price, old_price, alert_data)
            elif channel == "sms":
                await self._send_sms_notification(user, product, current_price, old_price, alert_data)
            elif channel == "websocket":
                await self._send_websocket_notification(user.id, alert_data)
            elif channel == "push":
                # Push notifications would be implemented here
                print(f"Push notification sent to user {user.id}")
                
        except Exception as e:
            print(f"Failed to send {channel} notification: {str(e)}")
    
    async def _send_email_notification(
        self,
        user: User,
        product: Product,
        current_price: float,
        old_price: Optional[float],
        alert_data: Dict[str, Any]
    ):
        """Send email notification for price alert."""
        
        # Determine alert type based on price comparison
        alert_type = "price_drop" if old_price and current_price < old_price else "price_alert"
        
        # Call the email service
        success = self.email_service.send_alert_email(
            to_email=user.email,
            product_name=product.name,
            old_price=old_price or current_price,
            new_price=current_price,
            alert_type=alert_type,
            subject=f"Price Alert: {product.name}",
            threshold_price=alert_data["threshold_price"],
            condition=alert_data["condition"]
        )
        
        if success:
            print(f"Email alert sent to {user.email} for product {product.name}")
    
    async def _send_sms_notification(
        self,
        user: User,
        product: Product,
        current_price: float,
        old_price: Optional[float],
        alert_data: Dict[str, Any]
    ):
        """Send SMS notification for price alert."""
        
        # Use email as phone number for testing (would be user.phone in production)
        phone_number = "+1234567890"  # Mock phone number
        
        # Determine alert type
        alert_type = "price_drop" if old_price and current_price < old_price else "price_alert"
        
        success = self.sms_service.send_alert(
            to_number=phone_number,
            product_name=product.name,
            old_price=old_price or current_price,
            new_price=current_price,
            alert_type=alert_type
        )
        
        if success:
            print(f"SMS alert sent to {phone_number} for product {product.name}")
    
    async def _send_websocket_notification(self, user_id: int, alert_data: Dict[str, Any]):
        """Send WebSocket notification for price alert."""
        await websocket_manager.send_personal_message(alert_data, user_id)
        print(f"WebSocket alert sent to user {user_id}")
    
    async def process_new_price_record(
        self,
        db_session: AsyncSession,
        price_record: PriceRecord
    ) -> Dict[str, Any]:
        """Process a new price record and trigger alerts if conditions are met."""
        
        # Get previous price for comparison
        prev_price_stmt = select(PriceRecord).where(
            PriceRecord.product_id == price_record.product_id,
            PriceRecord.id != price_record.id
        ).order_by(PriceRecord.recorded_at.desc()).limit(1)
        
        prev_record = (await db_session.execute(prev_price_stmt)).scalar_one_or_none()
        old_price = prev_record.price if prev_record else None
        
        # Process price change alerts
        return await self.process_price_change(
            db_session,
            price_record.product_id,
            price_record.price,
            old_price
        )


# Global instance
alert_processor = AlertProcessingService()
