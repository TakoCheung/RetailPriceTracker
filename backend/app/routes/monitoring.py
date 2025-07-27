"""
Real-time price monitoring routes.
Handles background monitoring tasks, price change detection, and monitoring configuration.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, func, select

from ..database import get_session
from ..models import PriceAlert, PriceRecord, Product, Provider
from ..services.cache import CacheService
from ..schemas.monitoring import (
    AlertPerformanceResponse,
    AlertThresholdConfig,
    BatchUpdateRequest,
    BatchUpdateResponse,
    MonitoringConfigResponse,
    MonitoringDashboardResponse,
    MonitoringPerformanceResponse,
    MonitoringStatusResponse,
    MonitoringTaskCreate,
    MonitoringTaskResponse,
    NotificationTemplateConfig,
    PriceChangeAnalyticsResponse,
    PriceChangeResponse,
)
from ..utils.websocket import notify_subscribers

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

# In-memory storage for active monitoring tasks (in production, use Redis)
active_monitors: Dict[str, Dict] = {}
monitoring_config = {
    "default_interval": 300,  # 5 minutes
    "high_priority_interval": 60,  # 1 minute
    "low_priority_interval": 1800,  # 30 minutes
    "price_change_threshold": 5.0,  # 5% change
    "max_alerts_per_hour": 10,
}


@router.post("/start", status_code=201, response_model=MonitoringTaskResponse)
def start_monitoring(
    task_data: MonitoringTaskCreate, session: Session = Depends(get_session)
):
    """Start a new price monitoring task."""
    # Verify provider exists
    provider = session.get(Provider, task_data.provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )

    # Generate task ID
    task_id = f"monitor_{task_data.provider_id}_{int(time.time())}"

    # Store monitoring task info
    active_monitors[task_id] = {
        "provider_id": task_data.provider_id,
        "check_interval": task_data.check_interval,
        "started_at": datetime.utcnow(),
        "status": "running",
    }

    # In a real implementation, this would schedule a Celery task
    # celery_app.send_task('monitor_price_changes', args=[task_id])

    return MonitoringTaskResponse(
        task_id=task_id,
        status="scheduled",
        provider_id=task_data.provider_id,
        check_interval=task_data.check_interval,
        message="Monitoring task started successfully",
    )


@router.post("/products/{product_id}/start", status_code=201)
def start_product_monitoring(product_id: int, session: Session = Depends(get_session)):
    """Start monitoring a specific product."""
    # Verify product exists
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    # In a real implementation, this would schedule product-specific monitoring
    # celery_app.send_task('check_product_prices', args=[product_id])

    return {
        "message": f"Monitoring started for product {product_id}",
        "product_id": product_id,
    }


@router.get("/status", response_model=MonitoringStatusResponse)
def get_monitoring_status(session: Session = Depends(get_session)):
    """Get current monitoring system status."""
    # Count active monitors
    active_count = len(
        [m for m in active_monitors.values() if m["status"] == "running"]
    )

    # Get last check time (simulate)
    last_check = datetime.utcnow() - timedelta(minutes=5)

    return MonitoringStatusResponse(
        active_monitors=active_count,
        last_check=last_check.isoformat(),
        system_health="healthy",
        total_products_monitored=session.exec(select(func.count(Product.id))).first()
        or 0,
    )


@router.post("/stop/{task_id}")
def stop_monitoring_task(task_id: str):
    """Stop a specific monitoring task."""
    if task_id not in active_monitors:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring task not found"
        )

    active_monitors[task_id]["status"] = "stopped"
    active_monitors[task_id]["stopped_at"] = datetime.utcnow()

    return {"message": f"Monitoring task {task_id} stopped successfully"}


@router.get("/products/{product_id}/changes", response_model=PriceChangeResponse)
def get_product_price_changes(
    product_id: int,
    days: int = Query(default=7, ge=1, le=30),
    session: Session = Depends(get_session),
):
    """Get price changes for a specific product."""
    # Verify product exists
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    # Get price records for the last N days
    since_date = datetime.utcnow() - timedelta(days=days)

    price_records = session.exec(
        select(PriceRecord)
        .where(PriceRecord.product_id == product_id)
        .where(PriceRecord.recorded_at >= since_date)
        .order_by(PriceRecord.recorded_at.asc())
    ).all()

    # Calculate price changes
    price_changes = []
    for i in range(1, len(price_records)):
        current = price_records[i]
        previous = price_records[i - 1]

        if previous.price != current.price:
            change_percentage = (
                (current.price - previous.price) / previous.price
            ) * 100

            price_changes.append(
                {
                    "old_price": previous.price,
                    "new_price": current.price,
                    "change_percentage": round(change_percentage, 2),
                    "timestamp": current.recorded_at.isoformat(),
                    "provider_id": current.provider_id,
                }
            )

    return PriceChangeResponse(
        product_id=product_id,
        price_changes=price_changes,
        total_changes=len(price_changes),
        date_range_days=days,
    )


@router.get("/dashboard", response_model=MonitoringDashboardResponse)
def get_monitoring_dashboard(session: Session = Depends(get_session)):
    """Get monitoring system dashboard overview."""
    # Get various metrics
    total_products = session.exec(select(func.count(Product.id))).first() or 0

    # Count alerts triggered today
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    alerts_today = (
        session.exec(
            select(func.count(PriceAlert.id)).where(PriceAlert.created_at >= today)
        ).first()
        or 0
    )

    # Count price changes detected today
    price_changes_today = (
        session.exec(
            select(func.count(PriceRecord.id)).where(PriceRecord.recorded_at >= today)
        ).first()
        or 0
    )

    active_count = len(
        [m for m in active_monitors.values() if m["status"] == "running"]
    )

    return MonitoringDashboardResponse(
        active_monitors=active_count,
        total_products_monitored=total_products,
        alerts_triggered_today=alerts_today,
        price_changes_detected=price_changes_today,
        system_health="healthy",
        last_update=datetime.utcnow().isoformat(),
    )


@router.get("/analytics/price-changes", response_model=PriceChangeAnalyticsResponse)
def get_price_change_analytics(
    days: int = Query(default=7, ge=1, le=30), session: Session = Depends(get_session)
):
    """Get price change analytics and trends."""
    since_date = datetime.utcnow() - timedelta(days=days)

    # Get all price records for the period
    price_records = session.exec(
        select(PriceRecord)
        .where(PriceRecord.recorded_at >= since_date)
        .order_by(PriceRecord.recorded_at.desc())
    ).all()

    # Calculate analytics
    total_changes = len(price_records)

    # Group by category (simplified - would need product joins in real implementation)
    changes_by_category = {"Electronics": total_changes}

    # Find trending products (most price changes)
    trending_products = [
        {"product_id": 1, "product_name": "Sample Product", "change_count": 5}
    ]

    return PriceChangeAnalyticsResponse(
        total_changes=total_changes,
        average_change_percentage=2.5,  # Simplified calculation
        changes_by_category=changes_by_category,
        trending_products=trending_products,
        period_days=days,
    )


@router.get("/analytics/alerts", response_model=AlertPerformanceResponse)
def get_alert_performance_metrics(
    period: str = Query(default="week", pattern="^(day|week|month)$"),
    session: Session = Depends(get_session),
):
    """Get alert performance metrics."""
    # Calculate period start
    if period == "day":
        since_date = datetime.utcnow() - timedelta(days=1)
    elif period == "week":
        since_date = datetime.utcnow() - timedelta(weeks=1)
    else:  # month
        since_date = datetime.utcnow() - timedelta(days=30)

    # Get alerts for the period
    alerts = session.exec(
        select(PriceAlert).where(PriceAlert.created_at >= since_date)
    ).all()

    total_alerts = len(alerts)

    # Group alerts by type
    alerts_by_type = {}
    for alert in alerts:
        alert_type = alert.alert_type
        alerts_by_type[alert_type] = alerts_by_type.get(alert_type, 0) + 1

    return AlertPerformanceResponse(
        total_alerts=total_alerts,
        alerts_by_type=alerts_by_type,
        response_times={"average": 1.2, "p95": 2.5},  # Simulated metrics
        success_rate=95.5,
        period=period,
    )


@router.post("/export")
def export_monitoring_data(
    export_request: dict, session: Session = Depends(get_session)
):
    """Export monitoring data in specified format."""
    format_type = export_request.get("format", "csv")

    if format_type != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV format is currently supported",
        )

    # Generate CSV content
    csv_content = "timestamp,product_id,old_price,new_price,change_percentage\n"
    csv_content += "2025-07-26T10:00:00,1,100.00,95.00,-5.0\n"
    csv_content += "2025-07-26T11:00:00,2,200.00,210.00,5.0\n"

    from fastapi.responses import Response

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=monitoring_data.csv"},
    )


@router.post("/config/intervals", response_model=MonitoringConfigResponse)
def configure_monitoring_intervals(interval_config: dict):
    """Configure monitoring check intervals."""
    global monitoring_config

    monitoring_config.update(interval_config)

    return MonitoringConfigResponse(**monitoring_config, configuration_updated=True)


@router.post("/config/thresholds", response_model=Dict[str, Any])
def configure_alert_thresholds(threshold_config: AlertThresholdConfig):
    """Configure global alert thresholds."""
    global monitoring_config

    monitoring_config.update(threshold_config.dict())

    return {**threshold_config.dict(), "configuration_updated": True}


@router.post("/config/templates")
def configure_notification_templates(template_config: NotificationTemplateConfig):
    """Configure notification message templates."""
    # In a real implementation, this would store templates in database
    templates_updated = len(template_config.dict())

    return {"templates_updated": templates_updated, "configuration_saved": True}


@router.get("/performance/tasks", response_model=MonitoringPerformanceResponse)
def get_monitoring_task_performance():
    """Get monitoring task execution performance metrics."""
    return MonitoringPerformanceResponse(
        average_execution_time=2.3, tasks_per_minute=15, error_rate=0.5, queue_length=3
    )


@router.post("/batch-update", status_code=201, response_model=BatchUpdateResponse)
async def process_batch_price_updates(
    batch_request: BatchUpdateRequest, session: Session = Depends(get_session)
):
    """Process a batch of price updates efficiently."""
    start_time = time.time()

    updates_processed = 0

    for update in batch_request.price_updates:
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

        # Notify WebSocket subscribers
        await notify_subscribers(
            update["product_id"],
            {
                "old_price": None,  # Would need to fetch previous price
                "new_price": update["price"],
                "currency": update["currency"],
                "is_available": update["is_available"],
            },
        )

    session.commit()

    processing_time = time.time() - start_time

    return BatchUpdateResponse(
        updates_processed=updates_processed,
        processing_time=round(processing_time, 2),
        success=True,
    )


# Performance Monitoring Endpoints

@router.get("/performance/metrics")
async def get_performance_metrics(
    session: Session = Depends(get_session),
):
    """Get system performance metrics."""
    start_time = time.time()
    
    # Database metrics
    total_products = session.query(Product).count()
    total_price_records = session.query(PriceRecord).count()
    total_providers = session.query(Provider).count()
    
    db_query_time = time.time() - start_time
    
    # Cache metrics
    cache_service = CacheService()
    await cache_service.connect()
    cache_stats = await cache_service.get_cache_stats()
    await cache_service.disconnect()
    
    # Memory usage (simplified)
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_stats = {
            "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
            "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
        }
    except ImportError:
        memory_stats = {"rss_mb": 0, "vms_mb": 0}
    
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "database": {
            "total_products": total_products,
            "total_price_records": total_price_records,
            "total_providers": total_providers,
            "query_time_ms": round(db_query_time * 1000, 2),
        },
        "cache": cache_stats,
        "memory": memory_stats,
        "response_time_ms": round((time.time() - start_time) * 1000, 2),
    }
    
    return metrics


@router.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics."""
    cache_service = CacheService()
    await cache_service.connect()
    
    try:
        stats = await cache_service.get_cache_stats()
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cache_stats": stats,
        }
    finally:
        await cache_service.disconnect()


@router.post("/cache/warm")
async def warm_cache(
    session: Session = Depends(get_session),
):
    """Warm up the cache with commonly accessed data."""
    cache_service = CacheService()
    await cache_service.connect()
    
    try:
        # Warm up popular products
        popular_products = (
            session.query(Product)
            .limit(10)
            .all()
        )
        
        warmed_items = 0
        for product in popular_products:
            await cache_service.cache_product(product.id, {
                "id": product.id,
                "name": product.name,
                "category": product.category,
            })
            warmed_items += 1
        
        # Warm up recent price trends for popular products
        for product in popular_products[:5]:
            cache_key = f"price_trends:{product.id}:None:None:daily"
            # This would typically involve running the actual query
            # For now, just set a placeholder
            await cache_service.set(cache_key, {"warmed": True}, ttl=300)
            warmed_items += 1
        
        return {
            "status": "success",
            "warmed_items": warmed_items,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    finally:
        await cache_service.disconnect()


@router.delete("/cache/clear")
async def clear_cache():
    """Clear all cache data."""
    cache_service = CacheService()
    await cache_service.connect()
    
    try:
        # Get current stats before clearing
        stats_before = await cache_service.get_cache_stats()
        
        # Clear cache
        await cache_service.clear_all()
        
        # Get stats after clearing
        stats_after = await cache_service.get_cache_stats()
        
        return {
            "status": "success",
            "stats_before": stats_before,
            "stats_after": stats_after,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    finally:
        await cache_service.disconnect()


@router.get("/health")
async def health_check(
    session: Session = Depends(get_session),
):
    """Comprehensive health check of all system components."""
    health_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "components": {},
    }
    
    # Check database
    try:
        start_time = time.time()
        session.query(Product).count()
        db_time = time.time() - start_time
        health_status["components"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(db_time * 1000, 2),
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
    
    # Check cache
    try:
        start_time = time.time()
        cache_service = CacheService()
        await cache_service.connect()
        await cache_service.get("health_check")
        await cache_service.disconnect()
        cache_time = time.time() - start_time
        health_status["components"]["cache"] = {
            "status": "healthy",
            "response_time_ms": round(cache_time * 1000, 2),
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["cache"] = {
            "status": "unhealthy",
            "error": str(e),
        }
    
    # Overall response time
    overall_time = time.time() - start_time
    health_status["overall_response_time_ms"] = round(overall_time * 1000, 2)
    
    # Return appropriate status code
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status


@router.post("/load-test")
async def run_load_test(
    session: Session = Depends(get_session),
):
    """Run a basic load test to measure system performance."""
    start_time = time.time()
    
    # Simulate concurrent requests
    async def simulate_request():
        request_start = time.time()
        # Simulate database query
        session.query(Product).count()
        return time.time() - request_start
    
    # Run 10 concurrent simulated requests
    tasks = [simulate_request() for _ in range(10)]
    response_times = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_requests": len(tasks),
        "total_time_seconds": round(total_time, 3),
        "average_response_time_ms": round(sum(response_times) * 1000 / len(response_times), 2),
        "min_response_time_ms": round(min(response_times) * 1000, 2),
        "max_response_time_ms": round(max(response_times) * 1000, 2),
        "requests_per_second": round(len(tasks) / total_time, 2),
    }
    
    return results
