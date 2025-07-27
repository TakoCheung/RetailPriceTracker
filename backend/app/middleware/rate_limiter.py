"""
Rate Limiting Middleware for FastAPI.
Provides comprehensive rate limiting capabilities including per-user,
per-IP, per-endpoint, and global rate limiting.
"""

import time
from typing import Any, Callable, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.exceptions import RateLimitError
from app.services.rate_limiter import RateLimiterService


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for API rate limiting."""

    def __init__(self, app: ASGIApp, rate_limiter: Optional[RateLimiterService] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiterService()

        # Configure default rate limits
        self._configure_default_limits()

    def _configure_default_limits(self):
        """Configure default rate limits for common endpoints."""
        # Authentication endpoints - stricter limits
        self.rate_limiter.configure_endpoint_limit("/api/auth/login", 5, 10)
        self.rate_limiter.configure_endpoint_limit("/api/auth/register", 3, 5)
        self.rate_limiter.configure_endpoint_limit("/api/auth/reset-password", 2, 3)

        # API endpoints - standard limits
        self.rate_limiter.configure_endpoint_limit("/api/products", 100, 200)
        self.rate_limiter.configure_endpoint_limit("/api/alerts", 50, 100)
        self.rate_limiter.configure_endpoint_limit("/api/preferences", 30, 60)

        # Admin endpoints - moderate limits
        self.rate_limiter.configure_endpoint_limit("/api/admin/*", 20, 40)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through rate limiting."""
        # Get client identifier
        client_id = self.get_client_identifier(request)
        client_ip = self.get_client_ip(request)
        endpoint = request.url.path
        user_agent = request.headers.get("user-agent", "")
        api_key = self.extract_api_key(request)

        # Check for exemptions
        if self.rate_limiter.is_exempt_from_rate_limiting(
            client_ip=client_ip, user_agent=user_agent, api_key=api_key
        ):
            response = await call_next(request)
            return response

        # Apply rate limiting
        try:
            await self.apply_rate_limit(client_id, client_ip, endpoint, api_key)
        except RateLimitError as e:
            return self.create_rate_limit_response(str(e), client_id, endpoint)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        rate_limit_headers = self.rate_limiter.get_rate_limit_headers(
            client_id, endpoint
        )
        for header, value in rate_limit_headers.items():
            response.headers[header] = value

        return response

    async def apply_rate_limit(
        self,
        client_id: str,
        client_ip: str,
        endpoint: str,
        api_key: Optional[str] = None,
    ):
        """Apply various rate limiting checks."""
        # Check endpoint-specific rate limits
        if not await self.rate_limiter.check_rate_limit(client_id, endpoint):
            raise RateLimitError(f"Rate limit exceeded for endpoint {endpoint}")

        # Check IP-based rate limits
        if not await self.rate_limiter.check_ip_rate_limit(client_ip, endpoint):
            raise RateLimitError(f"IP rate limit exceeded for {client_ip}")

        # Check global rate limits
        if not await self.rate_limiter.check_global_rate_limit(client_id):
            raise RateLimitError("Global rate limit exceeded")

        # Check API key rate limits if applicable
        if api_key and not self.rate_limiter.check_api_key_rate_limit(api_key):
            raise RateLimitError(f"API key rate limit exceeded for {api_key}")

    def get_client_identifier(self, request: Request) -> str:
        """Get unique client identifier for rate limiting."""
        # Try to get user ID from JWT token
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # In production, decode JWT to get user ID
            # For now, use a hash of the token
            token = auth_header[7:]
            return f"user:{hash(token) % 1000000}"

        # Fall back to IP address
        return f"ip:{self.get_client_ip(request)}"

    def get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxies."""
        # Check for forwarded headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Get the first IP in the chain
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct connection IP
        if hasattr(request.client, "host"):
            return request.client.host

        return "unknown"

    def extract_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request headers."""
        # Check for API key in headers
        api_key = request.headers.get("x-api-key")
        if api_key:
            return api_key

        # Check for API key in query parameters
        return request.query_params.get("api_key")

    def create_rate_limit_response(
        self, message: str, client_id: str, endpoint: str
    ) -> JSONResponse:
        """Create rate limit exceeded response."""
        headers = self.rate_limiter.get_rate_limit_headers(client_id, endpoint)

        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": message,
                "retry_after": int(headers.get("X-RateLimit-Reset", time.time() + 60)),
            },
            headers=headers,
        )

    def configure_endpoint_limits(self, endpoint_limits: Dict[str, Dict[str, Any]]):
        """Configure custom endpoint rate limits."""
        for endpoint, limits in endpoint_limits.items():
            self.rate_limiter.configure_endpoint_limit(
                endpoint=endpoint,
                requests_per_minute=limits.get("requests_per_minute", 60),
                burst_limit=limits.get("burst_limit"),
                burst_window_seconds=limits.get("burst_window_seconds", 60),
            )
