"""
Custom exception classes for the Retail Price Tracker application.
These exceptions provide structured error handling with proper HTTP status codes,
error codes, and detailed error information.
"""

from typing import Any, Dict, Optional


class BaseAPIException(Exception):
    """Base exception class for all API exceptions."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class ResourceNotFoundError(BaseAPIException):
    """Exception raised when a requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: Any):
        self.resource_type = resource_type
        self.resource_id = resource_id
        message = f"{resource_type} with ID {resource_id} not found"
        details = {"resource_type": resource_type, "resource_id": resource_id}
        super().__init__(
            message=message,
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
            details=details,
        )


class DataValidationError(BaseAPIException):
    """Exception raised when data validation fails."""

    def __init__(self, message: str, validation_errors: Dict[str, Any]):
        self.validation_errors = validation_errors
        super().__init__(
            message=message,
            status_code=422,
            error_code="VALIDATION_ERROR",
            details={"validation_errors": validation_errors},
        )


class BusinessLogicError(BaseAPIException):
    """Exception raised when business logic constraints are violated."""

    def __init__(self, message: str):
        super().__init__(
            message=message, status_code=409, error_code="BUSINESS_LOGIC_ERROR"
        )


class ExternalServiceError(BaseAPIException):
    """Exception raised when an external service fails."""

    def __init__(self, service_name: str, original_error: str):
        self.service_name = service_name
        self.original_error = original_error
        message = f"External service '{service_name}' error: {original_error}"
        details = {"service_name": service_name, "original_error": original_error}
        super().__init__(
            message=message,
            status_code=502,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=details,
        )


class RateLimitError(BaseAPIException):
    """Exception raised when rate limits are exceeded."""

    def __init__(self, message: str, retry_after: int = 60):
        self.retry_after = retry_after
        details = {"retry_after": retry_after}
        super().__init__(
            message=message,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
        )


class AuthenticationError(BaseAPIException):
    """Exception raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message, status_code=401, error_code="AUTHENTICATION_ERROR"
        )


class AuthorizationError(BaseAPIException):
    """Exception raised when authorization fails."""

    def __init__(self, message: str = "Access forbidden"):
        super().__init__(
            message=message, status_code=403, error_code="AUTHORIZATION_ERROR"
        )


class DatabaseError(BaseAPIException):
    """Exception raised when database operations fail."""

    def __init__(self, message: str, operation: str):
        self.operation = operation
        details = {"operation": operation}
        super().__init__(
            message=message,
            status_code=500,
            error_code="DATABASE_ERROR",
            details=details,
        )


class ConfigurationError(BaseAPIException):
    """Exception raised when configuration is invalid or missing."""

    def __init__(self, message: str, config_key: str):
        self.config_key = config_key
        details = {"config_key": config_key}
        super().__init__(
            message=message,
            status_code=500,
            error_code="CONFIGURATION_ERROR",
            details=details,
        )


# Data Ingestion & Processing Exceptions
class ScrapingError(BaseAPIException):
    """Exception raised when web scraping operations fail."""

    def __init__(self, message: str, url: Optional[str] = None):
        self.url = url
        details = {"url": url} if url else {}
        super().__init__(
            message=message,
            status_code=502,
            error_code="SCRAPING_ERROR",
            details=details,
        )


class ParsingError(BaseAPIException):
    """Exception raised when data parsing fails."""

    def __init__(self, message: str, data_type: str):
        self.data_type = data_type
        details = {"data_type": data_type}
        super().__init__(
            message=message,
            status_code=422,
            error_code="PARSING_ERROR",
            details=details,
        )


class ETLError(BaseAPIException):
    """Exception raised when ETL pipeline operations fail."""

    def __init__(self, message: str, stage: str):
        self.stage = stage
        details = {"stage": stage}
        super().__init__(
            message=message,
            status_code=500,
            error_code="ETL_ERROR",
            details=details,
        )


class DataQualityError(BaseAPIException):
    """Exception raised when data quality validation fails."""

    def __init__(self, message: str, quality_issues: Dict[str, Any]):
        self.quality_issues = quality_issues
        super().__init__(
            message=message,
            status_code=422,
            error_code="DATA_QUALITY_ERROR",
            details={"quality_issues": quality_issues},
        )


class ProviderError(BaseAPIException):
    """Exception raised when provider-specific operations fail."""

    def __init__(self, message: str, provider_name: str):
        self.provider_name = provider_name
        details = {"provider_name": provider_name}
        super().__init__(
            message=message,
            status_code=502,
            error_code="PROVIDER_ERROR",
            details=details,
        )
