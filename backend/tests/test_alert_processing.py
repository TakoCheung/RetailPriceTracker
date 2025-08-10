"""
Unit tests for Alert Processing Service.
Tests the core business logic without database dependencies.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from app.models import AlertCondition
from app.services.alert_processor import AlertProcessingService


class TestAlertProcessingService:
    """Test AlertProcessingService business logic."""

    @pytest.fixture
    def mock_email_service(self):
        """Mock email service."""
        mock = AsyncMock()
        mock.send_alert_email = AsyncMock()
        return mock

    @pytest.fixture
    def mock_sms_service(self):
        """Mock SMS service."""
        mock = AsyncMock()
        mock.send_alert_sms = AsyncMock()
        return mock

    @pytest.fixture
    def mock_websocket_manager(self):
        """Mock WebSocket manager."""
        mock = AsyncMock()
        mock.send_alert_to_user = AsyncMock()
        return mock

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        mock = AsyncMock()
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        return mock

    @pytest.fixture
    def alert_processor(
        self, mock_email_service, mock_sms_service, mock_websocket_manager
    ):
        """Create AlertProcessingService with mocked dependencies."""
        processor = AlertProcessingService()
        # Replace the services with mocks
        processor.email_service = mock_email_service
        processor.sms_service = mock_sms_service
        processor.websocket_manager = mock_websocket_manager
        return processor

    @pytest.mark.asyncio
    async def test_should_trigger_alert_below_threshold(self, alert_processor):
        """Test alert triggering when price drops below threshold."""
        # Create test data
        current_price = 90.0

        alert = Mock()
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.BELOW
        alert.last_triggered_at = None

        # Test alert should trigger
        result = alert_processor._should_trigger_alert(alert, current_price)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_trigger_alert_above_threshold(self, alert_processor):
        """Test alert triggering when price goes above threshold."""
        # Create test data
        current_price = 110.0

        alert = Mock()
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.ABOVE
        alert.last_triggered_at = None

        # Test alert should trigger
        result = alert_processor._should_trigger_alert(alert, current_price)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_trigger_alert_wrong_condition(self, alert_processor):
        """Test alert not triggering when condition is not met."""
        # Create test data
        current_price = 110.0

        alert = Mock()
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.BELOW  # Price is above, but condition is below
        alert.last_triggered_at = None

        # Test alert should not trigger
        result = alert_processor._should_trigger_alert(alert, current_price)
        assert result is False

    @pytest.mark.asyncio
    async def test_alert_cooldown_period(self, alert_processor):
        """Test alert cooldown prevents rapid re-triggering."""
        # Create test data
        alert = Mock()
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.BELOW
        # Alert was triggered recently (within cooldown)
        alert.updated_at = datetime.now(timezone.utc)
        alert.cooldown_minutes = 30

        # Test cooldown check
        result = alert_processor._is_in_cooldown(alert)
        assert result is True

    @pytest.mark.asyncio
    async def test_multi_channel_notification_trigger(
        self,
        alert_processor,
        mock_email_service,
        mock_sms_service,
        mock_websocket_manager,
        mock_db_session,
    ):
        """Test triggering notifications across multiple channels."""
        # Create test data
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.name = "Test User"

        product = Mock()
        product.id = 1
        product.name = "Test Product"

        alert = Mock()
        alert.id = 1
        alert.user = user
        alert.product = product
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.BELOW
        alert.notification_channels = ["email", "sms", "websocket"]
        alert.priority = "high"

        current_price = 90.0

        # Trigger alert notification
        await alert_processor._trigger_alert(mock_db_session, alert, current_price)

        # Verify all notification channels were called
        mock_email_service.send_alert_email.assert_called_once_with(
            user_email=user.email,
            user_name=user.name,
            product_name=product.name,
            current_price=current_price,
            subject=f"Price Alert: {product.name}",
            threshold_price=alert.threshold_price,
            condition=alert.condition.value,
        )

        mock_sms_service.send_alert_sms.assert_called_once_with(
            phone_number=None,  # Will be None in mock
            message=f"Price Alert: {product.name} is now ${current_price} (target: ${alert.threshold_price})",
        )

        mock_websocket_manager.send_alert_to_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_only_notification(
        self,
        alert_processor,
        mock_email_service,
        mock_sms_service,
        mock_websocket_manager,
        mock_db_session,
    ):
        """Test triggering email-only notifications."""
        # Create test data
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.name = "Test User"

        product = Mock()
        product.id = 1
        product.name = "Test Product"

        alert = Mock()
        alert.id = 1
        alert.user = user
        alert.product = product
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.BELOW
        alert.notification_channels = ["email"]  # Only email
        alert.priority = "medium"

        current_price = 90.0

        # Trigger alert notification
        await alert_processor._trigger_alert(mock_db_session, alert, current_price)

        # Verify only email was called
        mock_email_service.send_alert_email.assert_called_once()
        mock_sms_service.send_alert_sms.assert_not_called()
        mock_websocket_manager.send_alert_to_user.assert_called_once()  # WebSocket always called
