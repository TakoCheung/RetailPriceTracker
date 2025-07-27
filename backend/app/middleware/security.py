"""
Security Middleware for FastAPI applications.
Provides comprehensive security features including CORS,
security headers, request validation, and threat protection.
"""

from typing import Callable, Dict, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.services.security import SecurityService


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive security protection."""

    def __init__(
        self, app: ASGIApp, security_service: Optional[SecurityService] = None
    ):
        super().__init__(app)
        self.security_service = security_service or SecurityService()

        # Configuration
        self.enable_cors = True
        self.enable_security_headers = True
        self.enable_request_validation = True
        self.enable_size_limits = True

        # CORS configuration
        self.allowed_origins = ["*"]
        self.allowed_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allowed_headers = ["*"]

        # Size limits
        self.max_request_size = 10 * 1024 * 1024  # 10MB
        self.max_file_size = 100 * 1024 * 1024  # 100MB

        # Security headers
        self.security_headers = self._get_default_security_headers()

    def _get_default_security_headers(self) -> Dict[str, str]:
        """Get default security headers."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": self._get_default_csp(),
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

    def _get_default_csp(self) -> str:
        """Get default Content Security Policy."""
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through security middleware."""
        # Pre-request security checks
        security_response = await self._perform_security_checks(request)
        if security_response:
            return security_response

        # Process the request
        response = await call_next(request)

        # Post-request security enhancements
        response = self._add_security_headers(response)

        return response

    async def _perform_security_checks(self, request: Request) -> Optional[Response]:
        """Perform comprehensive security checks on incoming request."""
        # Check request size limits
        if self.enable_size_limits:
            if await self._check_request_size(request):
                return self._create_security_response("Request size exceeds limit", 413)

        # Validate request content
        if self.enable_request_validation:
            validation_error = await self._validate_request_content(request)
            if validation_error:
                return self._create_security_response(validation_error, 400)

        # Check for suspicious requests
        if self._is_suspicious_request(request):
            # Log security event
            self.security_service.log_security_event(
                event_type="suspicious_request",
                ip_address=self._get_client_ip(request),
                details={
                    "path": str(request.url.path),
                    "method": request.method,
                    "user_agent": request.headers.get("user-agent", ""),
                },
            )
            return self._create_security_response(
                "Request blocked due to suspicious activity", 403
            )

        return None

    async def _check_request_size(self, request: Request) -> bool:
        """Check if request size exceeds limits."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                return size > self.max_request_size
            except ValueError:
                return False
        return False

    async def _validate_request_content(self, request: Request) -> Optional[str]:
        """Validate request content for security threats."""
        # Check URL path
        path = str(request.url.path)
        if self.security_service.detect_path_traversal(path):
            return "Path traversal attempt detected"

        # Check query parameters
        for param, value in request.query_params.items():
            if isinstance(value, str):
                if self.security_service.detect_sql_injection(value):
                    return f"SQL injection attempt detected in parameter: {param}"
                if self.security_service.detect_xss_attempt(value):
                    return f"XSS attempt detected in parameter: {param}"
                if self.security_service.detect_command_injection(value):
                    return f"Command injection attempt detected in parameter: {param}"

        # Check headers
        for header, value in request.headers.items():
            if self.security_service.detect_header_injection(value):
                return f"Header injection attempt detected in header: {header}"

        return None

    def _is_suspicious_request(self, request: Request) -> bool:
        """Check if request matches suspicious patterns."""
        request_data = {
            "path": str(request.url.path),
            "method": request.method,
            "user_agent": request.headers.get("user-agent", ""),
            "headers": dict(request.headers),
        }

        return self.security_service.detect_suspicious_request(request_data)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        # Check for forwarded headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        if hasattr(request.client, "host"):
            return request.client.host

        return "unknown"

    def _add_security_headers(self, response: Response) -> Response:
        """Add security headers to response."""
        if self.enable_security_headers:
            for header, value in self.security_headers.items():
                response.headers[header] = value

        return response

    def _create_security_response(self, message: str, status_code: int) -> JSONResponse:
        """Create security-related error response."""
        return JSONResponse(
            status_code=status_code,
            content={"error": "Security violation", "message": message},
            headers=self.security_headers,
        )

    def configure_cors(
        self,
        allowed_origins: List[str],
        allowed_methods: List[str],
        allowed_headers: List[str],
    ):
        """Configure CORS settings."""
        self.allowed_origins = allowed_origins
        self.allowed_methods = allowed_methods
        self.allowed_headers = allowed_headers

    def get_security_headers(self) -> Dict[str, str]:
        """Get current security headers configuration."""
        return self.security_headers.copy()

    def get_content_security_policy(self) -> str:
        """Get Content Security Policy string."""
        return self.security_headers.get("Content-Security-Policy", "")

    def configure_size_limits(self, max_request_size: int, max_file_size: int):
        """Configure request size limits."""
        self.max_request_size = max_request_size
        self.max_file_size = max_file_size

    def update_security_headers(self, headers: Dict[str, str]):
        """Update security headers configuration."""
        self.security_headers.update(headers)

    def set_content_security_policy(self, csp: str):
        """Set custom Content Security Policy."""
        self.security_headers["Content-Security-Policy"] = csp
