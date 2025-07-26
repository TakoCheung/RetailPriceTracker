"""
Celery tasks for background processing and monitoring.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlmodel import Session, select

from .celery_app import celery
from .database import engine
from .models import PriceAlert, PriceRecord, Product
from .utils.websocket import websocket_manager


@celery.task
def daily_crawl():
    """Daily price crawling task."""
    # In real implementation, fetch prices from providers and store
    print("Fetching prices...")
    return "done"


@celery.task
def monitor_price_changes(task_id: str):
    """Background task to monitor price changes for a specific monitoring task."""
    print(f"Starting price monitoring for task {task_id}")

    with Session(engine) as session:
        # Get all products to monitor
        products = session.exec(select(Product)).all()

        for product in products:
            # Simulate checking price changes
            check_product_prices.delay(product.id)

    return f"Price monitoring completed for task {task_id}"


@celery.task
def check_product_prices(product_id: int):
    """Check for price changes for a specific product."""
    with Session(engine) as session:
        product = session.get(Product, product_id)
        if not product:
            return f"Product {product_id} not found"

        # Get the latest price record
        latest_record = session.exec(
            select(PriceRecord)
            .where(PriceRecord.product_id == product_id)
            .order_by(PriceRecord.recorded_at.desc())
            .limit(1)
        ).first()

        # Simulate price check from providers
        simulate_price_check.delay(
            product_id, latest_record.price if latest_record else 100.0
        )

    return f"Price check completed for product {product_id}"


@celery.task
def simulate_price_check(product_id: int, previous_price: float):
    """Simulate checking price from external providers."""
    import random

    # Simulate random price change
    price_change_factor = random.uniform(0.9, 1.1)  # ±10% change
    new_price = round(previous_price * price_change_factor, 2)

    # Only proceed if there's a significant change (>1%)
    if abs(new_price - previous_price) / previous_price > 0.01:
        process_price_change.delay(product_id, previous_price, new_price)

    return f"Price simulation completed for product {product_id}"


@celery.task
def process_price_change(product_id: int, old_price: float, new_price: float):
    """Process a detected price change."""
    with Session(engine) as session:
        # Create new price record
        price_record = PriceRecord(
            product_id=product_id,
            provider_id=1,  # Default provider for simulation
            price=new_price,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        )
        session.add(price_record)
        session.commit()

        # Calculate change percentage
        change_percentage = ((new_price - old_price) / old_price) * 100

        # Check if we should trigger alerts
        if abs(change_percentage) >= 5.0:  # 5% threshold
            trigger_price_alert.delay(
                product_id, old_price, new_price, change_percentage
            )

        # Notify WebSocket subscribers
        notify_price_change.delay(product_id, old_price, new_price, change_percentage)

    return f"Price change processed: {old_price} -> {new_price}"


@celery.task
def trigger_price_alert(
    product_id: int, old_price: float, new_price: float, change_percentage: float
):
    """Trigger alerts for significant price changes."""
    with Session(engine) as session:
        # Create price alert
        alert = PriceAlert(
            product_id=product_id,
            user_id=1,  # Would be determined by user preferences in real implementation
            alert_type="price_change",
            threshold_value=5.0,
            current_price=new_price,
            message=f"Price changed by {change_percentage:.1f}%: ${old_price} -> ${new_price}",
            is_triggered=True,
            created_at=datetime.utcnow(),
        )
        session.add(alert)
        session.commit()

        # Send notification
        send_notification.delay(alert.id, alert.message)

    return f"Alert triggered for product {product_id}"


@celery.task
def send_notification(alert_id: int, message: str):
    """Send notification for an alert."""
    # In real implementation, this would send email, SMS, or push notifications
    print(f"Notification sent for alert {alert_id}: {message}")
    return f"Notification sent for alert {alert_id}"


@celery.task
def notify_price_change(
    product_id: int, old_price: float, new_price: float, change_percentage: float
):
    """Notify WebSocket subscribers about price changes."""
    try:
        # Create the message data
        message_data = {
            "old_price": old_price,
            "new_price": new_price,
            "currency": "USD",
            "is_available": True,
            "change_percentage": change_percentage,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Schedule the WebSocket notification
        asyncio.run(websocket_manager.notify_subscribers(product_id, message_data))

    except Exception as e:
        print(f"Error notifying WebSocket subscribers: {e}")

    return f"WebSocket notification sent for product {product_id}"


@celery.task
def cleanup_old_monitoring_data():
    """Clean up old monitoring data to prevent database bloat."""
    with Session(engine) as session:
        # Delete price records older than 90 days
        cutoff_date = datetime.utcnow() - timedelta(days=90)

        old_records = session.exec(
            select(PriceRecord).where(PriceRecord.recorded_at < cutoff_date)
        ).all()

        for record in old_records:
            session.delete(record)

        session.commit()

        return f"Cleaned up {len(old_records)} old price records"


@celery.task
def generate_monitoring_report():
    """Generate daily monitoring system performance report."""
    with Session(engine) as session:
        # Get today's statistics
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Count today's price records
        price_records_today = session.exec(
            select(PriceRecord).where(PriceRecord.recorded_at >= today)
        ).all()

        # Count today's alerts
        alerts_today = session.exec(
            select(PriceAlert).where(PriceAlert.created_at >= today)
        ).all()

        report = {
            "date": today.date().isoformat(),
            "price_records_processed": len(price_records_today),
            "alerts_triggered": len(alerts_today),
            "system_health": "healthy",
        }

        print(f"Daily monitoring report: {report}")
        return report


@celery.task
def batch_price_update(price_updates: List[Dict[str, Any]]):
    """Process a batch of price updates efficiently."""
    with Session(engine) as session:
        updates_processed = 0

        for update in price_updates:
            try:
                # Create new price record
                price_record = PriceRecord(
                    product_id=update["product_id"],
                    provider_id=update["provider_id"],
                    price=update["price"],
                    currency=update["currency"],
                    is_available=update["is_available"],
                    recorded_at=datetime.utcnow(),
                )

                session.add(price_record)
                updates_processed += 1

                # Check for price changes and trigger notifications
                check_and_notify_price_change.delay(
                    update["product_id"],
                    update["price"],
                    update["currency"],
                    update["is_available"],
                )

            except Exception as e:
                print(f"Error processing price update: {e}")
                continue

        session.commit()
        return f"Batch update completed: {updates_processed} records processed"


@celery.task
def check_and_notify_price_change(
    product_id: int, new_price: float, currency: str, is_available: bool
):
    """Check for price changes and notify subscribers."""
    with Session(engine) as session:
        # Get the previous price record
        previous_record = session.exec(
            select(PriceRecord)
            .where(PriceRecord.product_id == product_id)
            .order_by(PriceRecord.recorded_at.desc())
            .offset(1)  # Skip the current record
            .limit(1)
        ).first()

        if previous_record and previous_record.price != new_price:
            # Calculate change and notify
            change_percentage = (
                (new_price - previous_record.price) / previous_record.price
            ) * 100

            # Notify WebSocket subscribers
            notify_price_change.delay(
                product_id, previous_record.price, new_price, change_percentage
            )

        return f"Price change check completed for product {product_id}"


# Periodic tasks - would be configured in Celery beat schedule
@celery.task
def hourly_monitoring_check():
    """Hourly monitoring system health check."""
    print("Performing hourly monitoring system health check")
    return "Health check completed"


@celery.task
def daily_monitoring_cleanup():
    """Daily cleanup of monitoring data."""
    cleanup_old_monitoring_data.delay()
    generate_monitoring_report.delay()
    return "Daily monitoring cleanup initiated"
