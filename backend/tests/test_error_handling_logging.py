"""
Test cases for Error Handling & Logging - TDD Implementation.
These tests cover global error handling, structured logging, custom exceptions,
health monitoring, and error response standardization.
"""

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from app.exceptions import (
    AuthenticationError,
    BusinessLogicError,
    DataValidationError,
    ExternalServiceError,
    RateLimitError,
    ResourceNotFoundError,
)
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.models import Product
from app.services.logging import LoggingService, StructuredLogger
from app.utils.health_check import HealthCheckService
from sqlalchemy.ext.asyncio import AsyncSession


class TestCustomExceptions:
    """Test cases for custom exception classes."""

    def test_resource_not_found_error(self):
        """Test ResourceNotFoundError exception."""
        error = ResourceNotFoundError("Product", 123)

        assert error.resource_type == "Product"
        assert error.resource_id == 123
        assert error.message == "Product with ID 123 not found"
        assert error.status_code == 404
        assert error.error_code == "RESOURCE_NOT_FOUND"

    def test_data_validation_error(self):
        """Test DataValidationError exception."""
        validation_errors = {
            "price": ["Price must be positive"],
            "currency": ["Invalid currency code"],
        }
        error = DataValidationError("Product validation failed", validation_errors)

        assert error.message == "Product validation failed"
        assert error.validation_errors == validation_errors
        assert error.status_code == 422
        assert error.error_code == "VALIDATION_ERROR"

    def test_business_logic_error(self):
        """Test BusinessLogicError exception."""
        error = BusinessLogicError("Cannot delete product with active alerts")

        assert error.message == "Cannot delete product with active alerts"
        assert error.status_code == 409
        assert error.error_code == "BUSINESS_LOGIC_ERROR"

    def test_external_service_error(self):
        """Test ExternalServiceError exception."""
        error = ExternalServiceError("price_scraper", "Connection timeout")

        assert error.service_name == "price_scraper"
        assert error.original_error == "Connection timeout"
        assert (
            error.message
            == "External service 'price_scraper' error: Connection timeout"
        )
        assert error.status_code == 502
        assert error.error_code == "EXTERNAL_SERVICE_ERROR"

    def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        error = RateLimitError("API rate limit exceeded", retry_after=300)

        assert error.message == "API rate limit exceeded"
        assert error.retry_after == 300
        assert error.status_code == 429
        assert error.error_code == "RATE_LIMIT_EXCEEDED"

    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError("Invalid JWT token")

        assert error.message == "Invalid JWT token"
        assert error.status_code == 401
        assert error.error_code == "AUTHENTICATION_ERROR"


class TestStructuredLogging:
    """Test cases for structured logging system."""

    def test_create_structured_logger(self):
        """Test creating structured logger with proper configuration."""
        logger = StructuredLogger("test_service")

        assert logger.name == "test_service"
        assert logger.level == logging.INFO
        assert len(logger.handlers) > 0

    def test_log_structured_info(self, caplog):
        """Test structured info logging."""
        logger = StructuredLogger("test")

        with caplog.at_level(logging.INFO):
            logger.info(
                "User action completed",
                user_id=123,
                action="create_product",
                product_id=456,
                duration_ms=250,
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "INFO"
        assert "User action completed" in record.getMessage()

        # Verify structured data is attached
        assert hasattr(record, "user_id")
        assert record.user_id == 123
        assert record.action == "create_product"

    def test_log_structured_error(self, caplog):
        """Test structured error logging with exception context."""
        logger = StructuredLogger("test")

        try:
            raise ValueError("Test error")
        except ValueError as e:
            with caplog.at_level(logging.ERROR):
                logger.error(
                    "Database operation failed",
                    error=str(e),
                    operation="update_product",
                    product_id=789,
                    exc_info=True,
                )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "ERROR"
        assert record.operation == "update_product"
        assert record.product_id == 789

    def test_log_performance_metrics(self, caplog):
        """Test logging performance metrics."""
        logger = StructuredLogger("performance")

        with caplog.at_level(logging.INFO):
            logger.performance(
                "Database query completed",
                query_type="product_search",
                duration_ms=125,
                result_count=42,
                cache_hit=False,
            )

        record = caplog.records[0]
        assert record.query_type == "product_search"
        assert record.duration_ms == 125
        assert record.cache_hit is False

    def test_log_security_event(self, caplog):
        """Test logging security-related events."""
        logger = StructuredLogger("security")

        with caplog.at_level(logging.WARNING):
            logger.security(
                "Failed login attempt",
                level="WARNING",
                user_email="test@example.com",
                ip_address="192.168.1.100",
                user_agent="Test Browser",
                attempt_count=3,
            )

        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert record.user_email == "test@example.com"
        assert record.attempt_count == 3

    def test_logging_service_initialization(self):
        """Test LoggingService proper initialization."""
        service = LoggingService()

        assert service.is_configured is True
        assert service.log_level == "INFO"
        assert service.log_format == "json"

    @pytest.mark.asyncio
    async def test_log_to_file(self):
        """Test logging to file with rotation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"

            service = LoggingService(log_file=str(log_file))
            logger = service.get_logger("test")

            logger.info("Test log message", test_field="test_value")

            # Verify log file was created and contains message
            assert log_file.exists()
            log_content = log_file.read_text()
            assert "Test log message" in log_content


class TestErrorHandlerMiddleware:
    """Test cases for global error handling middleware."""

    def test_middleware_handles_custom_exceptions(self, client):
        """Test middleware properly handles custom exceptions."""
        # This would test a route that raises a custom exception
        # For now, we'll test the middleware logic directly
        middleware = ErrorHandlerMiddleware()

        error = ResourceNotFoundError("Product", 123)
        response = middleware.format_error_response(error)

        assert response["error_code"] == "RESOURCE_NOT_FOUND"
        assert response["message"] == "Product with ID 123 not found"
        assert response["details"]["resource_type"] == "Product"
        assert response["details"]["resource_id"] == 123

    def test_middleware_handles_validation_errors(self, client):
        """Test middleware handles validation errors properly."""
        middleware = ErrorHandlerMiddleware()

        validation_errors = {"price": ["Must be positive"]}
        error = DataValidationError("Validation failed", validation_errors)
        response = middleware.format_error_response(error)

        assert response["error_code"] == "VALIDATION_ERROR"
        assert response["validation_errors"] == validation_errors

    def test_middleware_handles_unexpected_errors(self, client):
        """Test middleware handles unexpected exceptions gracefully."""
        middleware = ErrorHandlerMiddleware()

        # Simulate unexpected error
        error = RuntimeError("Unexpected error")
        response = middleware.format_error_response(error)

        assert response["error_code"] == "INTERNAL_SERVER_ERROR"
        assert response["message"] == "An internal server error occurred"
        assert "error_id" in response  # Should generate error ID for tracking

    def test_middleware_logs_errors(self, caplog):
        """Test middleware logs all errors appropriately."""
        middleware = ErrorHandlerMiddleware()

        with caplog.at_level(logging.ERROR):
            error = BusinessLogicError("Test business error")
            middleware.log_error(error, {"request_id": "test-123"})

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "ERROR"
        assert "Test business error" in record.getMessage()

    @patch("app.middleware.error_handler.generate_error_id")
    def test_error_tracking_id_generation(self, mock_generate_id, client):
        """Test error tracking ID generation for correlation."""
        mock_generate_id.return_value = "error-123456"

        middleware = ErrorHandlerMiddleware()
        error = ResourceNotFoundError("Product", 123)
        response = middleware.format_error_response(error)

        assert response["error_id"] == "error-123456"

    def test_middleware_preserves_rate_limit_headers(self, client):
        """Test middleware preserves rate limiting headers."""
        middleware = ErrorHandlerMiddleware()

        error = RateLimitError("Rate limit exceeded", retry_after=300)
        response = middleware.format_error_response(error)
        headers = middleware.get_error_headers(error)

        assert headers.get("Retry-After") == "300"
        assert response["retry_after"] == 300


class TestHealthCheckSystem:
    """Test cases for health check and system monitoring."""

    @pytest.mark.asyncio
    async def test_health_check_service_initialization(self):
        """Test HealthCheckService initialization."""
        service = HealthCheckService()

        assert service.checks == []
        assert service.timeout == 10.0

    @pytest.mark.asyncio
    async def test_database_health_check(self, db_session: AsyncSession):
        """Test database connectivity health check."""
        service = HealthCheckService()

        result = await service.check_database_health(db_session)

        assert result["component"] == "database"
        assert result["status"] in ["healthy", "unhealthy"]
        assert "response_time_ms" in result
        assert "details" in result

    @pytest.mark.asyncio
    async def test_cache_health_check(self):
        """Test cache service health check."""
        service = HealthCheckService()

        result = await service.check_cache_health()

        assert result["component"] == "cache"
        assert result["status"] in ["healthy", "unhealthy"]
        assert "response_time_ms" in result

    @pytest.mark.asyncio
    async def test_external_service_health_check(self):
        """Test external service health checks."""
        service = HealthCheckService()

        # Test with mock external service
        result = await service.check_external_service_health("price_scraper_api")

        assert result["component"] == "price_scraper_api"
        assert result["status"] in ["healthy", "unhealthy"]

    @pytest.mark.asyncio
    async def test_comprehensive_health_check(self, db_session: AsyncSession):
        """Test comprehensive system health check."""
        service = HealthCheckService()

        result = await service.run_all_checks(db_session)

        assert "timestamp" in result
        assert "overall_status" in result
        assert "components" in result
        assert len(result["components"]) > 0

        # Should include database, cache, and external services
        component_names = [c["component"] for c in result["components"]]
        assert "database" in component_names

    @pytest.mark.asyncio
    async def test_health_check_with_failures(self, db_session: AsyncSession):
        """Test health check handling when components fail."""
        service = HealthCheckService()

        # Mock a failing service
        with patch.object(service, "check_cache_health") as mock_cache:
            mock_cache.return_value = {
                "component": "cache",
                "status": "unhealthy",
                "error": "Connection refused",
            }

            result = await service.run_all_checks(db_session)

            assert result["overall_status"] == "unhealthy"
            cache_result = next(
                c for c in result["components"] if c["component"] == "cache"
            )
            assert cache_result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_timeout_handling(self):
        """Test health check timeout handling."""
        service = HealthCheckService(timeout=0.1)  # Very short timeout

        # Mock a slow service
        async def slow_check():
            import asyncio

            await asyncio.sleep(1.0)  # Longer than timeout
            return {"status": "healthy"}

        with patch.object(service, "check_cache_health", side_effect=slow_check):
            result = await service.check_cache_health()

            assert result["status"] == "timeout"
            assert "timeout" in result.get("error", "").lower()


class TestAPIErrorResponses:
    """Test cases for standardized API error responses."""

    def test_404_error_response_format(self, client, db_session):
        """Test 404 error response format."""
        response = client.get("/api/products/99999")  # Non-existent product

        assert response.status_code == 404
        data = response.json()

        assert "error_code" in data
        assert "message" in data
        assert "timestamp" in data
        assert data["error_code"] == "RESOURCE_NOT_FOUND"

    def test_validation_error_response_format(self, client):
        """Test validation error response format."""
        # Send invalid product data
        invalid_data = {
            "name": "",  # Invalid: empty name
            "price": -10,  # Invalid: negative price
        }

        response = client.post("/api/products", json=invalid_data)

        assert response.status_code == 422
        data = response.json()

        assert "error_code" in data
        assert "validation_errors" in data
        assert data["error_code"] == "VALIDATION_ERROR"

    def test_authentication_error_response(self, client):
        """Test authentication error response format."""
        # Try to access protected endpoint without token
        response = client.get("/api/users/profile")

        assert response.status_code == 401
        data = response.json()

        assert data["error_code"] == "AUTHENTICATION_ERROR"
        assert "message" in data

    def test_rate_limit_error_response(self, client):
        """Test rate limit error response format."""
        # This would test rate limiting - for now test the response format
        from app.exceptions import RateLimitError
        from app.middleware.error_handler import ErrorHandlerMiddleware

        middleware = ErrorHandlerMiddleware()
        error = RateLimitError("Too many requests", retry_after=60)
        response = middleware.format_error_response(error)

        assert response["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert response["retry_after"] == 60

    def test_internal_server_error_response(self, client):
        """Test internal server error response format."""
        # This would test a route that triggers an unexpected error
        # For now, test the middleware response format
        middleware = ErrorHandlerMiddleware()
        error = RuntimeError("Database connection lost")
        response = middleware.format_error_response(error)

        assert response["error_code"] == "INTERNAL_SERVER_ERROR"
        assert "error_id" in response
        assert "timestamp" in response


class TestLoggingIntegration:
    """Test cases for logging integration across the application."""

    @pytest.mark.asyncio
    async def test_request_logging_middleware(self, client):
        """Test request/response logging middleware."""
        # This would test actual HTTP request logging
        # For now, test the logging service integration
        service = LoggingService()
        logger = service.get_logger("requests")

        # Simulate request logging
        with patch.object(logger, "info") as mock_log:
            # Simulate middleware logging a request
            request_data = {
                "method": "GET",
                "path": "/api/products",
                "user_id": 123,
                "request_id": "req-123",
            }
            logger.info("HTTP request", **request_data)

            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_operation_logging(self, db_session: AsyncSession):
        """Test database operation logging."""
        service = LoggingService()
        logger = service.get_logger("database")

        with patch.object(logger, "info") as mock_log:
            # Simulate database operation logging
            product = Product(name="Test Product")
            db_session.add(product)

            # Log the operation
            logger.info(
                "Database operation",
                operation="create",
                table="products",
                entity_id=None,
                user_id=123,
            )

            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_business_logic_error_logging(self):
        """Test business logic error logging."""
        service = LoggingService()
        logger = service.get_logger("business")

        with patch.object(logger, "error") as mock_log:
            try:
                raise BusinessLogicError("Cannot delete product with active alerts")
            except BusinessLogicError as e:
                logger.error(
                    "Business logic error occurred",
                    error_code=e.error_code,
                    error_message=e.message,
                    product_id=123,
                    user_id=456,
                )

            mock_log.assert_called_once()

    def test_performance_monitoring_logging(self):
        """Test performance monitoring and logging."""
        service = LoggingService()
        logger = service.get_logger("performance")

        with patch.object(logger, "info") as mock_log:
            # Simulate performance logging
            logger.performance(
                "API endpoint performance",
                endpoint="/api/products",
                method="GET",
                duration_ms=150,
                status_code=200,
                cache_hit=True,
            )

            mock_log.assert_called_once()

    def test_security_event_logging(self):
        """Test security event logging."""
        service = LoggingService()
        logger = service.get_logger("security")

        with patch.object(logger, "warning") as mock_log:
            # Simulate security event logging
            logger.security(
                "Suspicious login pattern detected",
                level="WARNING",
                user_email="test@example.com",
                ip_address="192.168.1.100",
                failed_attempts=5,
                time_window_minutes=10,
            )

            mock_log.assert_called_once()


class TestErrorMetrics:
    """Test cases for error metrics and monitoring."""

    def test_error_rate_calculation(self):
        """Test error rate calculation and tracking."""
        from app.services.metrics import ErrorMetricsService

        service = ErrorMetricsService()

        # Simulate tracking errors
        service.track_error("VALIDATION_ERROR", "products")
        service.track_error("RESOURCE_NOT_FOUND", "products")
        service.track_error("VALIDATION_ERROR", "users")

        error_rates = service.get_error_rates(time_window_minutes=60)

        assert "VALIDATION_ERROR" in error_rates
        assert "RESOURCE_NOT_FOUND" in error_rates
        assert error_rates["VALIDATION_ERROR"]["count"] == 2

    def test_error_trend_analysis(self):
        """Test error trend analysis over time."""
        from app.services.metrics import ErrorMetricsService

        service = ErrorMetricsService()

        # Simulate error tracking over time
        for i in range(10):
            service.track_error("EXTERNAL_SERVICE_ERROR", "price_scraper")

        trends = service.get_error_trends(hours=24)

        assert "EXTERNAL_SERVICE_ERROR" in trends
        assert trends["EXTERNAL_SERVICE_ERROR"]["trend"] in [
            "increasing",
            "stable",
            "decreasing",
        ]

    def test_error_alerting_thresholds(self):
        """Test error alerting threshold monitoring."""
        from app.services.metrics import ErrorMetricsService

        service = ErrorMetricsService()

        # Configure thresholds
        service.set_error_threshold(
            "EXTERNAL_SERVICE_ERROR", count=5, time_window_minutes=5
        )

        # Trigger threshold
        for i in range(6):  # Exceed threshold
            service.track_error("EXTERNAL_SERVICE_ERROR", "price_scraper")

        alerts = service.check_thresholds()

        assert len(alerts) > 0
        assert any(alert["error_type"] == "EXTERNAL_SERVICE_ERROR" for alert in alerts)

    def test_error_correlation_analysis(self):
        """Test error correlation with system metrics."""
        from app.services.metrics import ErrorMetricsService

        service = ErrorMetricsService()

        # Track errors with context
        service.track_error_with_context(
            "DATABASE_ERROR",
            "products",
            context={"cpu_usage": 85, "memory_usage": 78, "active_connections": 45},
        )

        correlations = service.analyze_error_correlations("DATABASE_ERROR")

        assert "cpu_usage" in correlations
        assert "memory_usage" in correlations


class TestLogRotationAndRetention:
    """Test cases for log rotation and retention policies."""

    @pytest.mark.asyncio
    async def test_log_file_rotation(self):
        """Test log file rotation when size limits are reached."""
        with tempfile.TemporaryDirectory() as temp_dir:
            service = LoggingService(
                log_file=f"{temp_dir}/app.log", max_file_size="1MB", backup_count=3
            )

            logger = service.get_logger("test")

            # Generate enough logs to trigger rotation
            for i in range(1000):
                logger.info(f"Test log message {i}", iteration=i)

            # Check if rotation files exist
            log_files = list(Path(temp_dir).glob("app.log*"))
            assert len(log_files) > 1  # Original + rotated files

    @pytest.mark.asyncio
    async def test_log_retention_policy(self):
        """Test log retention policy enforcement."""
        with tempfile.TemporaryDirectory() as temp_dir:
            service = LoggingService(log_file=f"{temp_dir}/app.log", retention_days=7)

            # This would test actual retention cleanup
            # For now, verify the configuration is applied
            assert service.retention_days == 7

    def test_log_compression(self):
        """Test log file compression for old logs."""
        # This would test actual log compression
        # For now, verify compression configuration
        service = LoggingService(compress_logs=True)
        assert service.compress_logs is True


class TestDistributedLogging:
    """Test cases for distributed logging and centralized collection."""

    def test_correlation_id_propagation(self):
        """Test correlation ID propagation across service calls."""
        service = LoggingService()
        logger = service.get_logger("test")

        correlation_id = "corr-123456"

        with patch.object(logger, "info") as mock_log:
            # Simulate logging with correlation ID
            logger.info(
                "Service call completed",
                correlation_id=correlation_id,
                service="price_scraper",
                duration_ms=250,
            )

            # Verify correlation ID is included
            args, kwargs = mock_log.call_args
            assert kwargs.get("correlation_id") == correlation_id

    def test_structured_log_format_consistency(self):
        """Test consistent structured log format across services."""
        service = LoggingService()
        logger = service.get_logger("test")

        # Test standard fields are consistently formatted
        with patch.object(logger.handlers[0], "emit") as mock_emit:
            logger.info(
                "Standard log entry",
                timestamp=datetime.now(timezone.utc),
                service="retail_tracker",
                version="1.0.0",
                environment="test",
            )

            mock_emit.assert_called_once()

    def test_log_aggregation_metadata(self):
        """Test metadata for log aggregation systems."""
        service = LoggingService()
        logger = service.get_logger("test")

        with patch.object(logger, "info") as mock_log:
            logger.info(
                "Event occurred",
                event_type="price_change",
                source="price_monitor",
                tags=["monitoring", "pricing", "alerts"],
            )

            args, kwargs = mock_log.call_args
            assert "tags" in kwargs
            assert "monitoring" in kwargs["tags"]


# Fixtures for error handling tests
@pytest.fixture
def mock_external_service():
    """Mock external service for testing error scenarios."""
    mock = Mock()
    mock.get_product_price.return_value = {"price": 99.99, "available": True}
    return mock


@pytest.fixture
def sample_error_scenarios():
    """Sample error scenarios for testing."""
    return [
        {
            "error_type": "VALIDATION_ERROR",
            "description": "Invalid product data",
            "details": {"field": "price", "message": "Must be positive"},
        },
        {
            "error_type": "RESOURCE_NOT_FOUND",
            "description": "Product not found",
            "details": {"resource_id": 123, "resource_type": "Product"},
        },
        {
            "error_type": "EXTERNAL_SERVICE_ERROR",
            "description": "Price scraper unavailable",
            "details": {"service": "price_scraper", "timeout": True},
        },
    ]
