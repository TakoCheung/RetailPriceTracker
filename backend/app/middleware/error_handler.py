"""
Global error handling middleware for the Retail Price Tracker application.
Provides consistent error response formatting, logging, and error tracking.
"""

import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from app.exceptions import BaseAPIException, RateLimitError
from app.services.logging import get_logger
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for handling all application exceptions."""

    def __init__(self, app):
        super().__init__(app)
        self.logger = get_logger("error_handler")

    async def dispatch(self, request: Request, call_next):
        """Process request and handle any exceptions."""
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return await self.handle_exception(request, exc)

    async def handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        """Handle and format exceptions into proper HTTP responses."""
        error_id = generate_error_id()

        # Log the error with context
        await self.log_error(
            exc,
            {
                "request_id": getattr(request.state, "request_id", None),
                "error_id": error_id,
                "path": str(request.url.path),
                "method": request.method,
                "user_agent": request.headers.get("user-agent"),
                "ip_address": request.client.host if request.client else None,
            },
        )

        # Format error response
        if isinstance(exc, BaseAPIException):
            response_data = self.format_custom_error_response(exc, error_id)
            status_code = exc.status_code
            headers = self.get_error_headers(exc)
        else:
            response_data = self.format_unexpected_error_response(exc, error_id)
            status_code = 500
            headers = {}

        return JSONResponse(
            status_code=status_code, content=response_data, headers=headers
        )

    def format_custom_error_response(
        self, exc: BaseAPIException, error_id: str
    ) -> Dict[str, Any]:
        """Format custom exception into error response."""
        response = {
            "error_code": exc.error_code,
            "message": exc.message,
            "error_id": error_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Add specific details for different error types
        if exc.details:
            response["details"] = exc.details

        # Add validation errors if present
        if hasattr(exc, "validation_errors"):
            response["validation_errors"] = exc.validation_errors

        # Add retry information for rate limit errors
        if isinstance(exc, RateLimitError):
            response["retry_after"] = exc.retry_after

        return response

    def format_unexpected_error_response(
        self, exc: Exception, error_id: str
    ) -> Dict[str, Any]:
        """Format unexpected exception into error response."""
        return {
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred",
            "error_id": error_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def format_error_response(self, exc: Exception) -> Dict[str, Any]:
        """Format any exception into error response (for testing)."""
        error_id = generate_error_id()

        if isinstance(exc, BaseAPIException):
            return self.format_custom_error_response(exc, error_id)
        else:
            return self.format_unexpected_error_response(exc, error_id)

    def get_error_headers(self, exc: BaseAPIException) -> Dict[str, str]:
        """Get additional headers for error responses."""
        headers = {}

        if isinstance(exc, RateLimitError):
            headers["Retry-After"] = str(exc.retry_after)

        return headers

    async def log_error(self, exc: Exception, context: Dict[str, Any]):
        """Log error with full context information."""
        if isinstance(exc, BaseAPIException):
            # Log custom exceptions as warnings or errors based on status code
            if exc.status_code >= 500:
                log_level = "error"
            else:
                log_level = "warning"
        else:
            # Log unexpected errors as errors
            log_level = "error"

        log_data = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            **context,
        }

        # Add stack trace for unexpected errors
        if not isinstance(exc, BaseAPIException):
            log_data["stack_trace"] = traceback.format_exc()

        log_method = getattr(self.logger, log_level)
        log_method(f"Exception occurred: {str(exc)}", **log_data)


def generate_error_id() -> str:
    """Generate unique error ID for tracking."""
    return f"error-{uuid.uuid4().hex[:8]}"
