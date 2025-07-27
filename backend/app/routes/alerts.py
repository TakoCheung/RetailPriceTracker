"""
Alert API routes for price tracking.
Following RESTful patterns established in other APIs.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import AlertType, PriceAlert, Product, User
from ..schemas import AlertCreate, AlertResponse, AlertUpdate

router = APIRouter()


def _validate_alert_data(alert_data: AlertCreate) -> None:
    """Validate alert data based on alert type."""
    if alert_data.alert_type in [AlertType.PRICE_DROP, AlertType.PRICE_INCREASE]:
        if alert_data.threshold_price is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"threshold_price is required for {alert_data.alert_type} alerts",
            )

    # Validate notification channels
    valid_channels = ["email", "webhook", "sms"]
    for channel in alert_data.notification_channels:
        if channel not in valid_channels:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid notification channel: {channel}. Must be one of: {valid_channels}",
            )


@router.post("/", status_code=201, response_model=AlertResponse)
def create_alert(alert_data: AlertCreate, session: Session = Depends(get_session)):
    """Create a new price alert."""

    # Validate alert data
    _validate_alert_data(alert_data)

    # Verify user exists
    user = session.execute(
        select(User).where(User.id == alert_data.user_id)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Verify product exists
    product = session.execute(
        select(Product).where(Product.id == alert_data.product_id)
    ).scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    # Create the alert
    db_alert = PriceAlert(
        user_id=alert_data.user_id,
        product_id=alert_data.product_id,
        alert_type=alert_data.alert_type,
        threshold_price=alert_data.threshold_price,
        notification_channels=alert_data.notification_channels,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(db_alert)
    session.commit()
    session.refresh(db_alert)

    return db_alert


@router.get("/", response_model=List[AlertResponse])
def get_alerts(
    user_id: Optional[int] = Query(None, description="Filter alerts by user ID"),
    product_id: Optional[int] = Query(None, description="Filter alerts by product ID"),
    is_active: Optional[bool] = Query(
        None, description="Filter alerts by active status"
    ),
    session: Session = Depends(get_session),
):
    """Get alerts with optional filtering."""
    query = select(PriceAlert)

    # Apply filters
    if user_id is not None:
        query = query.where(PriceAlert.user_id == user_id)
    if product_id is not None:
        query = query.where(PriceAlert.product_id == product_id)
    if is_active is not None:
        query = query.where(PriceAlert.is_active == is_active)

    alerts = session.execute(query).scalars().all()
    return alerts


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: int, session: Session = Depends(get_session)):
    """Get a specific alert by ID."""
    alert = session.execute(
        select(PriceAlert).where(PriceAlert.id == alert_id)
    ).scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    return alert


@router.patch("/{alert_id}", response_model=AlertResponse)
def update_alert(
    alert_id: int, alert_update: AlertUpdate, session: Session = Depends(get_session)
):
    """Update an existing alert."""
    alert = session.execute(
        select(PriceAlert).where(PriceAlert.id == alert_id)
    ).scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    # Validate updated alert type if provided
    update_data = alert_update.model_dump(exclude_unset=True)
    if "alert_type" in update_data:
        # Create a temporary object for validation
        temp_alert = AlertCreate(
            user_id=alert.user_id,
            product_id=alert.product_id,
            alert_type=update_data["alert_type"],
            threshold_price=update_data.get("threshold_price", alert.threshold_price),
            notification_channels=update_data.get(
                "notification_channels", alert.notification_channels
            ),
        )
        _validate_alert_data(temp_alert)

    # Update fields that were provided
    for field, value in update_data.items():
        setattr(alert, field, value)

    alert.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(alert)

    return alert


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: int, session: Session = Depends(get_session)):
    """Delete an alert."""
    alert = session.execute(
        select(PriceAlert).where(PriceAlert.id == alert_id)
    ).scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    session.delete(alert)
    session.commit()


@router.post("/process")
def process_alerts(session: Session = Depends(get_session)):
    """Process pending alerts and trigger notifications."""
    from ..models import PriceRecord

    # Get active alerts
    active_alerts = session.exec(select(PriceAlert).where(PriceAlert.is_active)).all()

    triggered_alerts = []

    for alert in active_alerts:
        # Get latest price for the product
        latest_price = session.exec(
            select(PriceRecord)
            .where(PriceRecord.product_id == alert.product_id)
            .order_by(PriceRecord.timestamp.desc())
            .limit(1)
        ).first()

        if latest_price:
            # Check if alert conditions are met
            should_trigger = False

            if (
                alert.condition.value == "below"
                and latest_price.price <= alert.threshold_price
            ):
                should_trigger = True
            elif (
                alert.condition.value == "above"
                and latest_price.price >= alert.threshold_price
            ):
                should_trigger = True

            if should_trigger:
                triggered_alerts.append(
                    {
                        "alert_id": alert.id,
                        "product_id": alert.product_id,
                        "threshold_price": alert.threshold_price,
                        "current_price": latest_price.price,
                        "condition": alert.condition.value,
                    }
                )

    return {
        "alerts_processed": len(active_alerts),
        "triggered_alerts": triggered_alerts,
    }


@router.post("/process-bulk")
def process_bulk_alerts(session: Session = Depends(get_session)):
    """Process multiple alerts in bulk efficiently."""
    import time

    start_time = time.time()

    # Process all alerts
    result = process_alerts(session)

    processing_time = time.time() - start_time

    return {
        "total_alerts_processed": result["alerts_processed"],
        "triggered_alerts_count": len(result["triggered_alerts"]),
        "processing_time": round(processing_time, 2),
    }


@router.post("/{alert_id}/test-notification")
def test_alert_notification(alert_id: int, session: Session = Depends(get_session)):
    """Test notification channels for a specific alert."""
    alert = session.exec(select(PriceAlert).where(PriceAlert.id == alert_id)).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Simulate sending notifications through different channels
    notifications_sent = {}

    for channel in alert.notification_channels:
        if channel == "email":
            notifications_sent["email"] = True
        elif channel == "websocket":
            notifications_sent["websocket"] = True
        elif channel == "push":
            notifications_sent["push"] = True

    return {"alert_id": alert_id, "notifications_sent": notifications_sent}
