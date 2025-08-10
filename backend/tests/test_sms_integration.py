"""
Integration tests for SMS notifications with AlertProcessingService.
Tests the SMS integration without complex database dependencies.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from app.models import AlertCondition
from app.services.alert_processor import AlertProcessingService
from app.services.sms import SMSService


class TestSMSIntegration:
    """Test SMS service integration with alert processing."""

    @pytest.fixture
    def sms_service(self):
        """Create SMS service instance."""
        return SMSService()

    @pytest.mark.asyncio
    async def test_sms_service_send_alert_sms(self, sms_service):
        """Test SMS service sends alert SMS correctly."""
        phone_number = "+1234567890"
        message = "Price Alert: Test Product is now $90.0 (target: $100.0)"

        result = await sms_service.send_alert_sms(phone_number, message)
        assert result is True

    def test_sms_service_validate_phone_number(self, sms_service):
        """Test phone number validation."""
        # Valid numbers
        assert sms_service.validate_phone_number("+1234567890") is True
        assert sms_service.validate_phone_number("(123) 456-7890") is True
        assert sms_service.validate_phone_number("123-456-7890") is True

        # Invalid numbers
        assert sms_service.validate_phone_number("12345") is False
        assert sms_service.validate_phone_number("abcdefghij") is False

    def test_sms_service_format_phone_number(self, sms_service):
        """Test phone number formatting."""
        assert sms_service.format_phone_number("1234567890") == "+11234567890"
        assert sms_service.format_phone_number("(123) 456-7890") == "+11234567890"
        assert sms_service.format_phone_number("+1 123 456 7890") == "+11234567890"

    @pytest.mark.asyncio
    async def test_alert_processor_sms_integration(self):
        """Test AlertProcessingService correctly integrates with SMS service."""

        # Create alert processor with mocked services
        alert_processor = AlertProcessingService()

        # Mock the SMS service
        mock_sms_service = AsyncMock()
        mock_sms_service.send_alert_sms = AsyncMock(return_value=True)
        alert_processor.sms_service = mock_sms_service

        # Mock other services
        alert_processor.email_service = AsyncMock()
        alert_processor.websocket_manager = AsyncMock()

        # Create test alert data
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.name = "Test User"
        user.phone_number = "+1234567890"

        product = Mock()
        product.id = 1
        product.name = "Test Product"

        alert = Mock()
        alert.id = 1
        alert.user_id = 1
        alert.product_id = 1
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.BELOW
        alert.notification_channels = ["sms"]
        alert.priority = "high"

        # Mock database session
        mock_db_session = AsyncMock()
        mock_execute_result = AsyncMock()
        mock_execute_result.scalar_one_or_none = AsyncMock()

        # Configure mock to return user and product
        def mock_execute(stmt):
            mock_result = AsyncMock()
            # Determine what to return based on the query
            if "users" in str(stmt).lower():
                mock_result.scalar_one_or_none.return_value = user
            else:
                mock_result.scalar_one_or_none.return_value = product
            return mock_result

        mock_db_session.execute.side_effect = mock_execute

        current_price = 90.0

        # Test SMS notification triggering
        await alert_processor._trigger_alert(mock_db_session, alert, current_price)

        # Verify SMS service was called
        expected_message = f"Price Alert: {product.name} is now ${current_price} (target: ${alert.threshold_price})"
        mock_sms_service.send_alert_sms.assert_called_once_with(
            phone_number=user.phone_number, message=expected_message
        )

    @pytest.mark.asyncio
    async def test_alert_processor_multi_channel_with_sms(self):
        """Test multi-channel notifications including SMS."""

        # Create alert processor with all mocked services
        alert_processor = AlertProcessingService()

        # Mock all services
        mock_sms_service = AsyncMock()
        mock_sms_service.send_alert_sms = AsyncMock(return_value=True)

        mock_email_service = AsyncMock()
        mock_email_service.send_alert_email = AsyncMock(return_value=True)

        mock_websocket_manager = AsyncMock()
        mock_websocket_manager.send_alert_to_user = AsyncMock()

        alert_processor.sms_service = mock_sms_service
        alert_processor.email_service = mock_email_service
        alert_processor.websocket_manager = mock_websocket_manager

        # Create test data
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.name = "Test User"
        user.phone_number = "+1234567890"

        product = Mock()
        product.id = 1
        product.name = "Test Product"

        alert = Mock()
        alert.id = 1
        alert.user_id = 1
        alert.product_id = 1
        alert.threshold_price = 100.0
        alert.condition = AlertCondition.BELOW
        alert.notification_channels = ["email", "sms", "websocket"]
        alert.priority = "high"

        # Mock database session
        mock_db_session = AsyncMock()

        def mock_execute(stmt):
            mock_result = AsyncMock()
            if "users" in str(stmt).lower():
                mock_result.scalar_one_or_none.return_value = user
            else:
                mock_result.scalar_one_or_none.return_value = product
            return mock_result

        mock_db_session.execute.side_effect = mock_execute

        current_price = 90.0

        # Test multi-channel notification
        await alert_processor._trigger_alert(mock_db_session, alert, current_price)

        # Verify all channels were triggered
        mock_email_service.send_alert_email.assert_called_once()
        mock_sms_service.send_alert_sms.assert_called_once()
        mock_websocket_manager.send_alert_to_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_sms_notification_without_phone_number(self):
        """Test SMS notification handling when user has no phone number."""

        alert_processor = AlertProcessingService()
        mock_sms_service = AsyncMock()
        alert_processor.sms_service = mock_sms_service
        alert_processor.email_service = AsyncMock()
        alert_processor.websocket_manager = AsyncMock()

        # User without phone number
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.name = "Test User"
        user.phone_number = None  # No phone number

        product = Mock()
        product.id = 1
        product.name = "Test Product"

        alert = Mock()
        alert.id = 1
        alert.user_id = 1
        alert.product_id = 1
        alert.notification_channels = ["sms"]

        # Mock database session
        mock_db_session = AsyncMock()

        def mock_execute(stmt):
            mock_result = AsyncMock()
            if "users" in str(stmt).lower():
                mock_result.scalar_one_or_none.return_value = user
            else:
                mock_result.scalar_one_or_none.return_value = product
            return mock_result

        mock_db_session.execute.side_effect = mock_execute

        # Test SMS notification with no phone number
        await alert_processor._trigger_alert(mock_db_session, alert, 90.0)

        # SMS service should still be called but with None phone number
        mock_sms_service.send_alert_sms.assert_called_once_with(
            phone_number=None,
            message="Price Alert: Test Product is now $90.0 (target: None)",
        )
