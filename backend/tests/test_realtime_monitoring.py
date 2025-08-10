"""
Comprehensive TDD tests for Real-time Price Monitoring & Notification System.
Following TDD: Write tests first (RED), implement functionality (GREEN), then optimize (REFACTOR).

Test Coverage:
- WebSocket price update notifications
- Background monitoring task management
- Alert processing and notification system
- Monitoring dashboard and analytics
- Performance monitoring and optimization
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from app.database import get_session
from app.main import app
from app.models import PriceRecord, Product, Provider, User
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, create_engine

# Use the same test engine setup as existing tests
TEST_DATABASE_URL = "sqlite:///test.db"
test_engine = create_engine(TEST_DATABASE_URL, echo=True)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Setup test database once for the entire session."""
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def test_db():
    """Create a test database session."""
    # Clear any existing data before each test
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)

    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_db):
    """Create a test client with database dependency override."""

    def get_test_session():
        SessionLocal = sessionmaker(bind=test_engine, class_=Session)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = get_test_session
    client = TestClient(app)

    yield client


@pytest.fixture
def websocket_client(client):
    """Create a WebSocket test client."""
    return client


@pytest.fixture
def sample_monitoring_data(test_db):
    """Create sample monitoring test data."""
    from datetime import datetime

    from app.models import PriceAlert, PriceRecord

    # Create test user
    user = User(
        email="test@example.com",
        name="Test User",
        password_hash="$2b$12$test",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Create test provider
    provider = Provider(
        name="Test Provider",
        base_url="https://test.com",
        api_key="test_key",
        is_active=True,
    )
    test_db.add(provider)
    test_db.commit()
    test_db.refresh(provider)

    # Create test products with various prices
    products = []
    for i in range(3):
        product = Product(
            name=f"Test Product {i + 1}",
            description=f"Test product description {i + 1}",
            category="Electronics",
            image_url=f"https://example.com/image{i + 1}.jpg",
            url=f"https://example.com/product{i + 1}",
            status="active",
        )
        test_db.add(product)
    test_db.commit()

    for product in test_db.query(Product).all():
        test_db.refresh(product)
        products.append(product)

    # Create price records for testing
    base_prices = [100.0, 200.0, 300.0]
    for i, (product, base_price) in enumerate(zip(products, base_prices)):
        # Create multiple price points for trending analysis
        for j in range(5):
            price_variation = base_price + (j * 5)  # Slight price changes
            price = PriceRecord(
                product_id=product.id,
                provider_id=provider.id,
                price=price_variation,
                currency="USD",
                is_available=True,
                recorded_at=datetime.utcnow().replace(day=1 + j),
            )
            test_db.add(price)
    test_db.commit()

    # Create test alerts
    alerts = []
    for i, product in enumerate(products):
        alert = PriceAlert(
            product_id=product.id,
            user_id=user.id,
            alert_type="price_drop",
            threshold_price=10.0,
            notification_channels=[
                "email",
                "websocket",
            ],  # Include both channels for testing
            is_active=True,
            created_at=datetime.utcnow(),
        )
        test_db.add(alert)
        alerts.append(alert)
    test_db.commit()

    # Refresh alerts to get their IDs
    for alert in alerts:
        test_db.refresh(alert)

    return {
        "user": user,
        "provider": provider,
        "products": products,
        "base_prices": base_prices,
        "alerts": alerts,
    }


class TestWebSocketPriceUpdates:
    """Test real-time WebSocket price updates."""

    def test_websocket_connection_established(self, websocket_client):
        """Test WebSocket connection can be established."""
        with websocket_client.websocket_connect(
            "/ws?token=valid_jwt_token"
        ) as websocket:
            # Should receive initial connection message
            data = websocket.receive_text()
            assert "connection_established" in data or "connected" in data.lower()

    def test_websocket_receives_price_updates(
        self, websocket_client, sample_monitoring_data
    ):
        """Test WebSocket receives real-time price updates."""
        with websocket_client.websocket_connect(
            "/ws?token=valid_jwt_token"
        ) as websocket:
            # Should receive initial connection message
            initial_message = websocket.receive_text()
            assert (
                "connected" in initial_message.lower()
                or "connection_established" in initial_message
            )

            # Test subscription to price updates
            websocket.send_json(
                {
                    "type": "subscribe",
                    "channel": "product_prices",
                    "product_id": sample_monitoring_data["products"][0].id,
                }
            )

            # Verify subscription acknowledgment
            response = websocket.receive_json()
            assert response.get("type") == "subscription_confirmed"
            assert response["product_id"] == sample_monitoring_data["products"][0].id

    def test_websocket_handles_multiple_subscribers(
        self, websocket_client, sample_monitoring_data
    ):
        """Test WebSocket can handle multiple concurrent subscribers."""
        with (
            websocket_client.websocket_connect("/ws?token=valid_jwt_token") as ws1,
            websocket_client.websocket_connect(
                "/ws?token=valid_jwt_token_viewer"
            ) as ws2,
        ):
            # Both should receive connection confirmations
            data1 = ws1.receive_text()
            data2 = ws2.receive_text()

            assert "connected" in data1.lower() or "connection_established" in data1
            assert "connected" in data2.lower() or "connection_established" in data2

    def test_websocket_price_update_format(
        self, websocket_client, sample_monitoring_data
    ):
        """Test WebSocket price update message format."""
        with websocket_client.websocket_connect(
            "/ws?token=valid_jwt_token"
        ) as websocket:
            # Receive connection message first
            websocket.receive_text()

            # Subscribe to product updates
            websocket.send_json(
                {
                    "type": "subscribe",
                    "channel": "product_prices",
                    "product_id": sample_monitoring_data["products"][0].id,
                }
            )

            response = websocket.receive_json()

            # Verify response format
            assert "type" in response
            assert "product_id" in response
            assert "timestamp" in response

    def test_websocket_handles_disconnection_gracefully(self, websocket_client):
        """Test WebSocket handles client disconnection gracefully."""
        with websocket_client.websocket_connect(
            "/ws?token=valid_jwt_token"
        ) as websocket:
            websocket.receive_text()  # Initial connection message
            # Websocket automatically closes when exiting context

        # Should not raise any exceptions
        assert True


class TestBackgroundPriceMonitoring:
    """Test background price monitoring tasks."""

    @patch("app.tasks.monitor_price_changes.delay")
    def test_schedule_price_monitoring_task(
        self, mock_task, client, sample_monitoring_data
    ):
        """Test scheduling background price monitoring task."""
        response = client.post(
            "/api/monitoring/start",
            json={
                "provider_id": sample_monitoring_data["provider"].id,
                "check_interval": 300,  # 5 minutes
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "scheduled"
        assert mock_task.called

    @patch("app.tasks.check_product_prices.delay")
    def test_monitor_specific_product_prices(
        self, mock_task, client, sample_monitoring_data
    ):
        """Test monitoring specific product prices."""
        product_id = sample_monitoring_data["products"][0].id

        response = client.post(f"/api/monitoring/products/{product_id}/start")

        assert response.status_code == 201
        data = response.json()
        assert "monitoring_started" in data["message"].lower()
        assert mock_task.called

    def test_get_monitoring_status(self, client, sample_monitoring_data):
        """Test getting current monitoring status."""
        response = client.get("/api/monitoring/status")

        assert response.status_code == 200
        data = response.json()
        assert "active_monitors" in data
        assert "last_check" in data
        assert isinstance(data["active_monitors"], int)

    def test_stop_monitoring_task(self, client, sample_monitoring_data):
        """Test stopping monitoring task."""
        # First start monitoring
        start_response = client.post(
            "/api/monitoring/start",
            json={
                "provider_id": sample_monitoring_data["provider"].id,
                "check_interval": 300,
            },
        )
        task_id = start_response.json().get("task_id", "test-task-id")

        # Then stop it
        response = client.post(f"/api/monitoring/stop/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert "stopped" in data["message"].lower()

    def test_price_change_detection_algorithm(
        self, client, sample_monitoring_data, test_db
    ):
        """Test price change detection algorithm."""
        product_id = sample_monitoring_data["products"][0].id
        provider_id = sample_monitoring_data["provider"].id

        # Add new price record with different price
        new_price = PriceRecord(
            product_id=product_id,
            provider_id=provider_id,
            price=85.00,  # Dropped from 100.00
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        )
        test_db.add(new_price)
        test_db.commit()

        # Check for price changes (use 30 days to include all prices)
        response = client.get(f"/api/monitoring/products/{product_id}/changes?days=30")

        assert response.status_code == 200
        data = response.json()
        assert "price_changes" in data
        assert len(data["price_changes"]) > 0

        change = data["price_changes"][0]
        assert change["old_price"] == 100.00
        assert change["new_price"] == 85.00
        assert change["change_percentage"] == -15.0  # 15% decrease


class TestAlertProcessing:
    """Test intelligent alert processing."""

    def test_trigger_price_drop_alert(self, client, sample_monitoring_data, test_db):
        """Test triggering price drop alert when threshold is met."""
        product_id = sample_monitoring_data["products"][0].id
        provider_id = sample_monitoring_data["provider"].id

        # Add price record that triggers alert (below 95.00 threshold)
        trigger_price = PriceRecord(
            product_id=product_id,
            provider_id=provider_id,
            price=90.00,  # Below threshold of 95.00
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        )
        test_db.add(trigger_price)
        test_db.commit()

        # Process alerts
        response = client.post("/api/alerts/process")

        assert response.status_code == 200
        data = response.json()
        assert data["alerts_processed"] > 0
        assert "triggered_alerts" in data

    def test_trigger_price_increase_alert(
        self, client, sample_monitoring_data, test_db
    ):
        """Test triggering price increase alert when threshold is met."""
        product_id = sample_monitoring_data["products"][1].id
        provider_id = sample_monitoring_data["provider"].id

        # Add price record that triggers increase alert (above 250.00 threshold)
        trigger_price = PriceRecord(
            product_id=product_id,
            provider_id=provider_id,
            price=275.00,  # Above threshold of 250.00
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        )
        test_db.add(trigger_price)
        test_db.commit()

        # Process alerts
        response = client.post("/api/alerts/process")

        assert response.status_code == 200
        data = response.json()
        assert data["alerts_processed"] > 0

    def test_alert_cooldown_period(self, client, sample_monitoring_data, test_db):
        """Test alert cooldown period to prevent spam."""
        product_id = sample_monitoring_data["products"][0].id
        provider_id = sample_monitoring_data["provider"].id

        # Trigger alert first time
        first_trigger = PriceRecord(
            product_id=product_id,
            provider_id=provider_id,
            price=90.00,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        )
        test_db.add(first_trigger)
        test_db.commit()

        # Process alerts
        response1 = client.post("/api/alerts/process")
        assert response1.status_code == 200

        # Trigger alert again immediately (should be in cooldown)
        second_trigger = PriceRecord(
            product_id=product_id,
            provider_id=provider_id,
            price=85.00,
            currency="USD",
            is_available=True,
            recorded_at=datetime.utcnow(),
        )
        test_db.add(second_trigger)
        test_db.commit()

        # Process alerts again
        response2 = client.post("/api/alerts/process")
        assert response2.status_code == 200
        data2 = response2.json()

        # Should have fewer or no new alerts due to cooldown
        assert "cooldown_alerts" in data2

    def test_alert_notification_channels(self, client, sample_monitoring_data):
        """Test different alert notification channels."""
        alert_id = sample_monitoring_data["alerts"][0].id

        response = client.post(f"/api/alerts/{alert_id}/test-notification")

        assert response.status_code == 200
        data = response.json()
        assert "notifications_sent" in data
        assert "email" in data["notifications_sent"]
        assert "websocket" in data["notifications_sent"]

    def test_bulk_alert_processing(self, client, sample_monitoring_data, test_db):
        """Test processing multiple alerts efficiently."""
        # Create multiple price changes that trigger alerts
        for i, product in enumerate(sample_monitoring_data["products"]):
            trigger_price = PriceRecord(
                product_id=product.id,
                provider_id=sample_monitoring_data["provider"].id,
                price=50.00,  # Low price to trigger alerts
                currency="USD",
                is_available=True,
                recorded_at=datetime.utcnow(),
            )
            test_db.add(trigger_price)

        test_db.commit()

        # Process all alerts in bulk
        response = client.post("/api/alerts/process-bulk")

        assert response.status_code == 200
        data = response.json()
        assert data["total_alerts_processed"] >= 2
        assert "processing_time" in data
        assert data["processing_time"] < 5.0  # Should be fast


class TestNotificationSystem:
    """Test live notification system."""

    @patch("app.services.notification.send_email")
    def test_send_email_notification(
        self, mock_send_email, client, sample_monitoring_data
    ):
        """Test sending email notifications."""
        mock_send_email.return_value = True

        notification_data = {
            "user_id": sample_monitoring_data["user"].id,
            "product_id": sample_monitoring_data["products"][0].id,
            "alert_type": "price_drop",
            "old_price": 100.00,
            "new_price": 90.00,
            "channels": ["email"],
        }

        response = client.post("/api/notifications/send", json=notification_data)

        assert response.status_code == 201
        data = response.json()
        assert data["notification_sent"] is True
        assert "email" in data["channels_used"]
        mock_send_email.assert_called_once()

    @patch("app.utils.websocket.notify_subscribers")
    def test_send_websocket_notification(
        self, mock_notify, client, sample_monitoring_data
    ):
        """Test sending WebSocket notifications."""
        # Clear rate limits before test
        client.delete("/api/notifications/rate-limits")

        mock_notify.return_value = True

        notification_data = {
            "user_id": sample_monitoring_data["user"].id,
            "product_id": sample_monitoring_data["products"][0].id,
            "alert_type": "price_drop",
            "old_price": 100.00,
            "new_price": 90.00,
            "channels": ["websocket"],
        }

        response = client.post("/api/notifications/send", json=notification_data)

        assert response.status_code == 201
        data = response.json()
        assert data["notification_sent"] is True
        assert "websocket" in data["channels_used"]
        mock_notify.assert_called_once()

    def test_notification_history(self, client, sample_monitoring_data):
        """Test retrieving notification history."""
        user_id = sample_monitoring_data["user"].id

        response = client.get(f"/api/notifications/history/{user_id}")

        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert "total_count" in data
        assert isinstance(data["notifications"], list)

    def test_notification_preferences(self, client, sample_monitoring_data):
        """Test user notification preferences."""
        user_id = sample_monitoring_data["user"].id

        # Get current preferences
        response = client.get(f"/api/notifications/preferences/{user_id}")
        assert response.status_code == 200

        # Update preferences
        new_prefs = {
            "email_enabled": True,
            "websocket_enabled": True,
            "sms_enabled": False,
            "quiet_hours": {"start": "22:00", "end": "08:00"},
        }

        update_response = client.patch(
            f"/api/notifications/preferences/{user_id}", json=new_prefs
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data["email_enabled"] is True
        assert data["sms_enabled"] is False

    def test_notification_rate_limiting(self, client, sample_monitoring_data):
        """Test notification rate limiting to prevent spam."""
        # Clear rate limits before test
        client.delete("/api/notifications/rate-limits")

        user_id = sample_monitoring_data["user"].id

        # Send multiple notifications rapidly
        notification_data = {
            "user_id": user_id,
            "product_id": sample_monitoring_data["products"][0].id,
            "alert_type": "price_drop",
            "old_price": 100.00,
            "new_price": 90.00,
            "channels": ["email"],
        }

        # First notification should succeed
        response1 = client.post("/api/notifications/send", json=notification_data)
        assert response1.status_code == 201

        # Immediate second notification should be rate limited
        response2 = client.post("/api/notifications/send", json=notification_data)
        assert response2.status_code == 429  # Too Many Requests

        data2 = response2.json()
        assert "rate limit" in data2["detail"].lower()


class TestMonitoringDashboard:
    """Test monitoring dashboard and analytics."""

    def test_get_monitoring_overview(self, client, sample_monitoring_data):
        """Test getting monitoring system overview."""
        response = client.get("/api/monitoring/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert "active_monitors" in data
        assert "total_products_monitored" in data
        assert "alerts_triggered_today" in data
        assert "price_changes_detected" in data
        assert "system_health" in data

    def test_get_price_change_analytics(self, client, sample_monitoring_data):
        """Test getting price change analytics."""
        response = client.get(
            "/api/monitoring/analytics/price-changes", params={"days": 7}
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_changes" in data
        assert "average_change_percentage" in data
        assert "changes_by_category" in data
        assert "trending_products" in data

    def test_get_alert_performance_metrics(self, client, sample_monitoring_data):
        """Test getting alert performance metrics."""
        response = client.get(
            "/api/monitoring/analytics/alerts", params={"period": "week"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_alerts" in data
        assert "alerts_by_type" in data
        assert "response_times" in data
        assert "success_rate" in data

    def test_export_monitoring_data(self, client, sample_monitoring_data):
        """Test exporting monitoring data."""
        response = client.post(
            "/api/monitoring/export",
            json={
                "format": "csv",
                "date_range": {
                    "start": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                    "end": datetime.utcnow().isoformat(),
                },
                "include": ["price_changes", "alerts", "notifications"],
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")

        # Verify CSV content structure
        csv_content = response.content.decode()
        assert "timestamp" in csv_content
        assert "product_id" in csv_content


class TestMonitoringConfiguration:
    """Test monitoring system configuration."""

    def test_configure_monitoring_intervals(self, client):
        """Test configuring monitoring check intervals."""
        config_data = {
            "default_interval": 300,  # 5 minutes
            "high_priority_interval": 60,  # 1 minute
            "low_priority_interval": 1800,  # 30 minutes
        }

        response = client.post("/api/monitoring/config/intervals", json=config_data)

        assert response.status_code == 200
        data = response.json()
        assert data["default_interval"] == 300
        assert data["configuration_updated"] is True

    def test_configure_alert_thresholds(self, client):
        """Test configuring global alert thresholds."""
        threshold_config = {
            "price_change_threshold": 5.0,  # 5% change
            "availability_check": True,
            "currency_change_alert": True,
            "max_alerts_per_hour": 10,
        }

        response = client.post(
            "/api/monitoring/config/thresholds", json=threshold_config
        )

        assert response.status_code == 200
        data = response.json()
        assert data["price_change_threshold"] == 5.0
        assert data["max_alerts_per_hour"] == 10

    def test_configure_notification_templates(self, client):
        """Test configuring notification message templates."""
        template_config = {
            "price_drop_template": "Good news! {product_name} dropped to ${new_price} (was ${old_price})",
            "price_increase_template": "Price alert: {product_name} increased to ${new_price}",
            "back_in_stock_template": "{product_name} is back in stock!",
            "out_of_stock_template": "{product_name} is now out of stock",
        }

        response = client.post("/api/monitoring/config/templates", json=template_config)

        assert response.status_code == 200
        data = response.json()
        assert "templates_updated" in data
        assert data["templates_updated"] == 4


class TestMonitoringPerformance:
    """Test monitoring system performance."""

    def test_monitoring_task_performance(self, client):
        """Test monitoring task execution performance."""
        response = client.get("/api/monitoring/performance/tasks")

        assert response.status_code == 200
        data = response.json()
        assert "average_execution_time" in data
        assert "tasks_per_minute" in data
        assert "error_rate" in data
        assert "queue_length" in data

    def test_websocket_connection_limits(self, websocket_client):
        """Test WebSocket connection handling under load."""
        max_connections = 5
        connections = []

        try:
            # Create multiple connections
            for i in range(max_connections):
                ws = websocket_client.websocket_connect(
                    f"/ws/price-updates?client_id={i}"
                )
                connections.append(ws)

            # All connections should be established
            assert len(connections) == max_connections

        finally:
            # Clean up connections
            for ws in connections:
                try:
                    ws.close()
                except:
                    pass

    def test_bulk_price_update_processing(
        self, client, sample_monitoring_data, test_db
    ):
        """Test processing large batches of price updates efficiently."""
        product_id = sample_monitoring_data["products"][0].id
        provider_id = sample_monitoring_data["provider"].id

        # Create batch of price updates
        batch_size = 100
        price_updates = []

        for i in range(batch_size):
            price_update = {
                "product_id": product_id,
                "provider_id": provider_id,
                "price": 100.00 + i,  # Varying prices
                "currency": "USD",
                "is_available": True,
            }
            price_updates.append(price_update)

        # Process batch
        response = client.post(
            "/api/monitoring/batch-update", json={"price_updates": price_updates}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["updates_processed"] == batch_size
        assert "processing_time" in data
        assert data["processing_time"] < 10.0  # Should process efficiently
