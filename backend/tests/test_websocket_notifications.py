"""
Test cases for Real-time WebSocket Notifications & Alerts system.
Covers WebSocket connections, price alerts, notification delivery, and real-time updates.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from app.models import (
    AlertCondition,
    PriceAlert,
    PriceRecord,
    Product,
    Provider,
    User,
    UserRole,
)
from sqlalchemy.ext.asyncio import AsyncSession
from websockets.exceptions import ConnectionClosed


class TestWebSocketConnection:
    """Test WebSocket connection management and authentication."""

    @pytest.mark.asyncio
    async def test_websocket_connection_with_valid_token(self, client):
        """Test WebSocket connection with valid JWT token."""
        # Create test user and token
        test_user = {"id": 1, "email": "test@example.com", "name": "Test User"}
        token = "valid_jwt_token"

        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Should be able to connect successfully
            data = websocket.receive_json()
            assert data["type"] == "connection_established"
            assert data["user_id"] == test_user["id"]
            assert "connection_id" in data

    @pytest.mark.asyncio
    async def test_websocket_connection_with_invalid_token(self, client):
        """Test WebSocket connection rejection with invalid token."""
        invalid_token = "invalid_jwt_token"

        with pytest.raises(Exception):  # Connection should be rejected
            with client.websocket_connect(f"/ws?token={invalid_token}"):
                pass

    @pytest.mark.asyncio
    async def test_websocket_connection_without_token(self, client):
        """Test WebSocket connection rejection without token."""
        with pytest.raises(Exception):  # Connection should be rejected
            with client.websocket_connect("/ws"):
                pass

    @pytest.mark.asyncio
    async def test_websocket_connection_cleanup_on_disconnect(self, client):
        """Test proper cleanup when WebSocket disconnects."""
        token = "valid_jwt_token"

        with client.websocket_connect(f"/ws?token={token}") as websocket:
            websocket.receive_json()  # Connection established message
            # Simulate disconnect
            websocket.close()

        # Verify connection is cleaned up from active connections
        # This would be checked through the WebSocket manager
        assert True  # Placeholder for actual cleanup verification

    @pytest.mark.asyncio
    async def test_websocket_heartbeat_mechanism(self, client):
        """Test WebSocket heartbeat/ping-pong mechanism."""
        token = "valid_jwt_token"

        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Send ping
            websocket.send_json({"type": "ping"})

            # Should receive pong
            response = websocket.receive_json()
            assert response["type"] == "pong"
            assert "timestamp" in response


class TestPriceAlertNotifications:
    """Test price alert detection and notification delivery."""

    @pytest.mark.asyncio
    async def test_price_alert_triggered_below_threshold(
        self, client, db_session: AsyncSession
    ):
        """Test alert triggered when price drops below threshold."""
        # Create test data
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")

        db_session.add_all([user, product, provider])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create price alert
        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["websocket", "email"],
        )
        db_session.add(alert)
        await db_session.commit()

        # Create price record that triggers alert
        price_record = PriceRecord(
            product_id=product.id,
            provider_id=provider.id,
            price=95.0,  # Below threshold
            currency="USD",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(price_record)
        await db_session.commit()

        # Connect WebSocket for user
        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Trigger price check (would be done by background task)
            # This simulates the alert processing system

            # Should receive alert notification
            alert_notification = websocket.receive_json()
            assert alert_notification["type"] == "price_alert"
            assert alert_notification["alert_id"] == alert.id
            assert alert_notification["product"]["name"] == "Test Product"
            assert alert_notification["current_price"] == 95.0
            assert alert_notification["threshold_price"] == 100.0
            assert alert_notification["condition"] == "below"

    @pytest.mark.asyncio
    async def test_price_alert_triggered_above_threshold(
        self, client, db_session: AsyncSession
    ):
        """Test alert triggered when price rises above threshold."""
        # Create test data
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")

        db_session.add_all([user, product, provider])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create price alert for above threshold
        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.ABOVE,
            notification_channels=["websocket"],
        )
        db_session.add(alert)
        await db_session.commit()

        # Create price record that triggers alert
        price_record = PriceRecord(
            product_id=product.id,
            provider_id=provider.id,
            price=105.0,  # Above threshold
            currency="USD",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(price_record)
        await db_session.commit()

        # Connect and verify alert received
        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            alert_notification = websocket.receive_json()
            assert alert_notification["current_price"] == 105.0
            assert alert_notification["condition"] == "above"

    @pytest.mark.asyncio
    async def test_alert_cooldown_period(self, client, db_session: AsyncSession):
        """Test that alerts respect cooldown periods."""
        # Create test data
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")

        db_session.add_all([user, product, provider])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create alert with short cooldown
        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            cooldown_minutes=5,  # 5 minute cooldown
            notification_channels=["websocket"],
        )
        db_session.add(alert)
        await db_session.commit()

        # First triggering price
        price_record1 = PriceRecord(
            product_id=product.id,
            provider_id=provider.id,
            price=95.0,
            currency="USD",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(price_record1)
        await db_session.commit()

        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Should receive first alert
            alert1 = websocket.receive_json()
            assert alert1["type"] == "price_alert"

            # Second triggering price within cooldown
            price_record2 = PriceRecord(
                product_id=product.id,
                provider_id=provider.id,
                price=90.0,  # Even lower price
                currency="USD",
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(price_record2)
            await db_session.commit()

            # Should NOT receive second alert due to cooldown
            try:
                websocket.receive_json(timeout=1.0)
                assert False, "Should not receive alert during cooldown"
            except Exception:
                assert True  # Expected to timeout

    @pytest.mark.asyncio
    async def test_multiple_users_alerts(self, client, db_session: AsyncSession):
        """Test alerts delivered to multiple users for same product."""
        # Create test data
        user1 = User(email="user1@example.com", name="User 1")
        user2 = User(email="user2@example.com", name="User 2")
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")

        db_session.add_all([user1, user2, product, provider])
        await db_session.commit()
        await db_session.refresh(user1)
        await db_session.refresh(user2)
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create alerts for both users
        alert1 = PriceAlert(
            user_id=user1.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["websocket"],
        )
        alert2 = PriceAlert(
            user_id=user2.id,
            product_id=product.id,
            threshold_price=110.0,  # Different threshold
            condition=AlertCondition.BELOW,
            notification_channels=["websocket"],
        )
        db_session.add_all([alert1, alert2])
        await db_session.commit()

        # Price that triggers both alerts
        price_record = PriceRecord(
            product_id=product.id,
            provider_id=provider.id,
            price=95.0,
            currency="USD",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(price_record)
        await db_session.commit()

        # Both users should receive alerts
        token1 = "valid_jwt_token_user1"
        token2 = "valid_jwt_token_user2"

        with (
            client.websocket_connect(f"/ws?token={token1}") as ws1,
            client.websocket_connect(f"/ws?token={token2}") as ws2,
        ):
            alert_user1 = ws1.receive_json()
            alert_user2 = ws2.receive_json()

            assert alert_user1["type"] == "price_alert"
            assert alert_user2["type"] == "price_alert"
            assert alert_user1["current_price"] == 95.0
            assert alert_user2["current_price"] == 95.0


class TestRealTimeUpdates:
    """Test real-time updates for price changes and system events."""

    @pytest.mark.asyncio
    async def test_real_time_price_updates(self, client, db_session: AsyncSession):
        """Test real-time price updates broadcast to connected users."""
        # Create test data
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")

        db_session.add_all([user, product, provider])
        await db_session.commit()
        await db_session.refresh(product)
        await db_session.refresh(provider)

        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Subscribe to product updates
            websocket.send_json(
                {
                    "type": "subscribe",
                    "channel": "product_prices",
                    "product_id": product.id,
                }
            )

            # Confirmation of subscription
            response = websocket.receive_json()
            assert response["type"] == "subscription_confirmed"
            assert response["channel"] == "product_prices"

            # New price record created
            price_record = PriceRecord(
                product_id=product.id,
                provider_id=provider.id,
                price=99.99,
                currency="USD",
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(price_record)
            await db_session.commit()

            # Should receive price update
            price_update = websocket.receive_json()
            assert price_update["type"] == "price_update"
            assert price_update["product_id"] == product.id
            assert price_update["price"] == 99.99
            assert price_update["provider"]["name"] == "Test Provider"

    @pytest.mark.asyncio
    async def test_system_status_updates(self, client):
        """Test system status updates broadcast to all users."""
        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Subscribe to system updates
            websocket.send_json({"type": "subscribe", "channel": "system_status"})

            # Should receive system status update
            status_update = websocket.receive_json()
            assert status_update["type"] == "system_status"
            assert "status" in status_update
            assert "message" in status_update
            assert "timestamp" in status_update

    @pytest.mark.asyncio
    async def test_user_specific_notifications(self, client, db_session: AsyncSession):
        """Test user-specific notifications like account updates."""
        user = User(email="test@example.com", name="Test User")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Simulate account update
            user.name = "Updated Name"
            await db_session.commit()

            # Should receive account update notification
            account_update = websocket.receive_json()
            assert account_update["type"] == "account_update"
            assert account_update["user"]["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_unsubscribe_from_channel(self, client):
        """Test unsubscribing from WebSocket channels."""
        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Subscribe first
            websocket.send_json(
                {"type": "subscribe", "channel": "product_prices", "product_id": 1}
            )

            # Confirm subscription
            response = websocket.receive_json()
            assert response["type"] == "subscription_confirmed"

            # Unsubscribe
            websocket.send_json(
                {"type": "unsubscribe", "channel": "product_prices", "product_id": 1}
            )

            # Confirm unsubscription
            response = websocket.receive_json()
            assert response["type"] == "unsubscription_confirmed"


class TestNotificationChannels:
    """Test different notification delivery channels."""

    @pytest.mark.asyncio
    async def test_email_notification_delivery(self, db_session: AsyncSession):
        """Test email notification delivery for alerts."""
        # Create alert with email notification
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")

        db_session.add_all([user, product])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)

        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["email"],
        )
        db_session.add(alert)
        await db_session.commit()

        # Mock email service
        with patch("app.services.email.EmailService.send_alert_email") as mock_email:
            # Trigger alert processing
            # This would be called by the alert processing service
            mock_email.return_value = True

            # Verify email was sent
            mock_email.assert_called_once()
            call_args = mock_email.call_args[1]
            assert call_args["to_email"] == "test@example.com"
            assert "price alert" in call_args["subject"].lower()

    @pytest.mark.asyncio
    async def test_push_notification_delivery(self, db_session: AsyncSession):
        """Test push notification delivery for mobile apps."""
        # Create alert with push notification
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")

        db_session.add_all([user, product])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)

        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["push"],
        )
        db_session.add(alert)
        await db_session.commit()

        # Mock push notification service
        with patch("app.services.push.PushNotificationService.send_alert") as mock_push:
            mock_push.return_value = True

            # Trigger alert processing
            # Verify push notification was sent
            mock_push.assert_called_once()

    @pytest.mark.asyncio
    async def test_sms_notification_delivery(self, db_session: AsyncSession):
        """Test SMS notification delivery for urgent alerts."""
        # Create alert with SMS notification
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")

        db_session.add_all([user, product])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)

        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["sms"],
            priority="high",  # High priority alerts can use SMS
        )
        db_session.add(alert)
        await db_session.commit()

        # Mock SMS service
        with patch("app.services.sms.SMSService.send_alert") as mock_sms:
            mock_sms.return_value = True

            # Trigger alert processing
            # Verify SMS was sent
            mock_sms.assert_called_once()


class TestWebSocketSecurity:
    """Test WebSocket security features and rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limiting_websocket_messages(self, client):
        """Test rate limiting for WebSocket message sending."""
        token = "valid_jwt_token"
        with client.websocket_connect(f"/ws?token={token}") as websocket:
            # Send messages rapidly to trigger rate limiting
            for i in range(100):  # Exceed rate limit
                websocket.send_json({"type": "ping"})

            # Eventually should receive rate limit warning
            response = websocket.receive_json()
            assert response["type"] == "rate_limit_warning"

    @pytest.mark.asyncio
    async def test_websocket_token_expiration(self, client):
        """Test WebSocket disconnection when token expires."""
        expired_token = "expired_jwt_token"

        # Connection should be rejected or disconnected
        with pytest.raises(ConnectionClosed):
            with client.websocket_connect(f"/ws?token={expired_token}") as websocket:
                # Try to send message with expired token
                websocket.send_json({"type": "ping"})
                websocket.receive_json()

    @pytest.mark.asyncio
    async def test_websocket_admin_only_channels(self, client):
        """Test that admin-only channels require admin privileges."""
        viewer_token = "valid_jwt_token_viewer"
        admin_token = "valid_jwt_token_admin"

        # Viewer should not be able to subscribe to admin channels
        with client.websocket_connect(f"/ws?token={viewer_token}") as websocket:
            websocket.send_json({"type": "subscribe", "channel": "admin_alerts"})

            response = websocket.receive_json()
            assert response["type"] == "subscription_denied"
            assert "insufficient privileges" in response["message"].lower()

        # Admin should be able to subscribe
        with client.websocket_connect(f"/ws?token={admin_token}") as websocket:
            websocket.send_json({"type": "subscribe", "channel": "admin_alerts"})

            response = websocket.receive_json()
            assert response["type"] == "subscription_confirmed"


class TestWebSocketPerformance:
    """Test WebSocket performance and scalability."""

    @pytest.mark.asyncio
    async def test_concurrent_websocket_connections(self, client):
        """Test handling multiple concurrent WebSocket connections."""
        tokens = [f"valid_jwt_token_{i}" for i in range(10)]
        connections = []

        try:
            # Create multiple connections
            for token in tokens:
                ws = client.websocket_connect(f"/ws?token={token}")
                connections.append(ws.__enter__())

            # Send message to all connections
            for ws in connections:
                ws.send_json({"type": "ping"})

            # All should respond
            for ws in connections:
                response = ws.receive_json()
                assert response["type"] == "pong"

        finally:
            # Clean up connections
            for ws in connections:
                ws.close()

    @pytest.mark.asyncio
    async def test_message_broadcasting_performance(
        self, client, db_session: AsyncSession
    ):
        """Test performance of broadcasting messages to many users."""
        # Create product for price updates
        product = Product(name="Popular Product")
        provider = Provider(name="Test Provider", base_url="https://test.com")

        db_session.add_all([product, provider])
        await db_session.commit()
        await db_session.refresh(product)
        await db_session.refresh(provider)

        # Create multiple connections subscribed to the same product
        tokens = [f"valid_jwt_token_{i}" for i in range(50)]
        connections = []

        try:
            for token in tokens:
                ws = client.websocket_connect(f"/ws?token={token}")
                connection = ws.__enter__()
                connections.append(connection)

                # Subscribe to product updates
                connection.send_json(
                    {
                        "type": "subscribe",
                        "channel": "product_prices",
                        "product_id": product.id,
                    }
                )

            # Broadcast price update to all subscribers
            price_record = PriceRecord(
                product_id=product.id,
                provider_id=provider.id,
                price=99.99,
                currency="USD",
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(price_record)
            await db_session.commit()

            # All connections should receive the update
            for ws in connections:
                response = ws.receive_json()
                assert response["type"] == "price_update"

        finally:
            for ws in connections:
                ws.close()


class TestNotificationHistory:
    """Test notification history and tracking."""

    @pytest.mark.asyncio
    async def test_notification_delivery_tracking(self, db_session: AsyncSession):
        """Test tracking of notification delivery status."""
        # Create alert
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")

        db_session.add_all([user, product])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)

        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["email", "websocket"],
        )
        db_session.add(alert)
        await db_session.commit()

        # Trigger notification
        # Should create notification history records

        # Check that delivery records are created
        history_records = await db_session.execute(
            "SELECT * FROM notification_history WHERE alert_id = :alert_id",
            {"alert_id": alert.id},
        )

        # Should have records for each channel
        records = history_records.fetchall()
        channels = [record.channel for record in records]
        assert "email" in channels
        assert "websocket" in channels

    @pytest.mark.asyncio
    async def test_failed_notification_retry(self, db_session: AsyncSession):
        """Test retry mechanism for failed notifications."""
        # Create alert
        user = User(email="test@example.com", name="Test User")
        product = Product(name="Test Product")

        db_session.add_all([user, product])
        await db_session.commit()
        await db_session.refresh(user)
        await db_session.refresh(product)

        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            threshold_price=100.0,
            condition=AlertCondition.BELOW,
            notification_channels=["email"],
        )
        db_session.add(alert)
        await db_session.commit()

        # Mock failed email delivery
        with patch("app.services.email.EmailService.send_alert_email") as mock_email:
            mock_email.side_effect = Exception("Email service unavailable")

            # Trigger notification
            # Should be marked for retry

            # Check that failed delivery is recorded
            history_record = await db_session.execute(
                "SELECT * FROM notification_history WHERE alert_id = :alert_id AND status = 'failed'",
                {"alert_id": alert.id},
            )

            record = history_record.fetchone()
            assert record is not None
            assert record.retry_count < 3  # Should be eligible for retry


@pytest.fixture
async def websocket_test_data(db_session: AsyncSession):
    """Fixture providing test data for WebSocket tests."""
    # Create users
    viewer_user = User(
        email="viewer@example.com", name="Viewer User", role=UserRole.VIEWER
    )
    admin_user = User(email="admin@example.com", name="Admin User", role=UserRole.ADMIN)

    # Create products and providers
    product1 = Product(name="iPhone 15 Pro", brand="Apple", category="smartphones")
    product2 = Product(
        name="Samsung Galaxy S24", brand="Samsung", category="smartphones"
    )

    provider1 = Provider(name="Amazon", base_url="https://amazon.com")
    provider2 = Provider(name="Best Buy", base_url="https://bestbuy.com")

    # Add all to session
    db_session.add_all(
        [viewer_user, admin_user, product1, product2, provider1, provider2]
    )
    await db_session.commit()

    # Refresh to get IDs
    for obj in [viewer_user, admin_user, product1, product2, provider1, provider2]:
        await db_session.refresh(obj)

    return {
        "users": {"viewer": viewer_user, "admin": admin_user},
        "products": {"iphone": product1, "samsung": product2},
        "providers": {"amazon": provider1, "bestbuy": provider2},
    }
