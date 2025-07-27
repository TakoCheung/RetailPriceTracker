"""
Rate Limiting Service for API protection and throttling.
Implements multiple rate limiting strategies including per-user, per-IP,
per-endpoint, and global rate limiting.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from app.models import UserRole


class RateLimitType(Enum):
    """Types of rate limiting."""

    PER_USER = "per_user"
    PER_IP = "per_ip"
    PER_ENDPOINT = "per_endpoint"
    GLOBAL = "global"
    API_KEY = "api_key"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting rules."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 100
    burst_window_seconds: int = 60
    enabled: bool = True


@dataclass
class RequestRecord:
    """Record of a request for rate limiting."""

    timestamp: float
    endpoint: str
    client_id: str
    request_size: Optional[int] = None


class RateLimiterService:
    """Service for handling API rate limiting."""

    def __init__(self):
        self.default_requests_per_minute = 60
        self.default_burst_limit = 100
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        self.user_requests: Dict[str, deque] = defaultdict(deque)
        self.ip_requests: Dict[str, deque] = defaultdict(deque)
        self.endpoint_requests: Dict[str, deque] = defaultdict(deque)
        self.global_requests: deque = deque()
        self.api_key_requests: Dict[str, deque] = defaultdict(deque)

        # Role-based limits
        self.role_limits: Dict[UserRole, RateLimitConfig] = {}

        # Configuration
        self.global_config = RateLimitConfig()
        self.ip_config = RateLimitConfig()
        self.enable_adaptive_limiting = False
        self.adaptive_config = {}

        # Exemptions
        self.exempt_ips: List[str] = []
        self.exempt_user_agents: List[str] = []
        self.exempt_api_keys: List[str] = []

    def configure_endpoint_limit(
        self,
        endpoint: str,
        requests_per_minute: int,
        burst_limit: Optional[int] = None,
        burst_window_seconds: int = 60,
    ):
        """Configure rate limits for a specific endpoint."""
        self.rate_limits[endpoint] = {
            "requests_per_minute": requests_per_minute,
            "burst_limit": burst_limit or requests_per_minute * 2,
            "burst_window_seconds": burst_window_seconds,
        }

    def configure_role_based_limits(self, role_limits: Dict[UserRole, Dict[str, int]]):
        """Configure rate limits based on user roles."""
        for role, limits in role_limits.items():
            self.role_limits[role] = RateLimitConfig(
                requests_per_minute=limits.get("requests_per_minute", 60),
                requests_per_hour=limits.get("requests_per_hour", 1000),
                burst_limit=limits.get("burst_limit", 100),
            )

    def configure_ip_rate_limit(self, requests_per_minute: int, burst_limit: int):
        """Configure rate limits for IP addresses."""
        self.ip_config = RateLimitConfig(
            requests_per_minute=requests_per_minute, burst_limit=burst_limit
        )

    def configure_global_rate_limit(
        self, requests_per_second: int, max_concurrent: int
    ):
        """Configure global rate limits."""
        self.global_config = RateLimitConfig(
            requests_per_minute=requests_per_second * 60, burst_limit=max_concurrent
        )

    def configure_api_key_limits(self, api_key: str, requests_per_hour: int):
        """Configure rate limits for specific API keys."""
        self.rate_limits[f"api_key:{api_key}"] = {
            "requests_per_hour": requests_per_hour,
            "requests": deque(),
        }

    def get_user_rate_limits(self, user_role: UserRole) -> Dict[str, int]:
        """Get rate limits for a user role."""
        if user_role in self.role_limits:
            config = self.role_limits[user_role]
            return {
                "requests_per_minute": config.requests_per_minute,
                "requests_per_hour": config.requests_per_hour,
                "burst_limit": config.burst_limit,
            }

        return {
            "requests_per_minute": self.default_requests_per_minute,
            "requests_per_hour": 1000,
            "burst_limit": self.default_burst_limit,
        }

    async def check_rate_limit(self, client_id: str, endpoint: str) -> bool:
        """Check if request is allowed under rate limits."""
        current_time = time.time()

        # Get endpoint-specific limits
        endpoint_limits = self.rate_limits.get(endpoint)
        if not endpoint_limits:
            return True

        requests_per_minute = endpoint_limits["requests_per_minute"]
        burst_limit = endpoint_limits["burst_limit"]

        # Create unique key for client-endpoint combination
        key = f"{client_id}:{endpoint}"

        # Clean old requests (older than 1 minute)
        self._clean_old_requests(self.user_requests[key], current_time, 60)

        # Simple burst limit check - allow up to burst_limit requests
        current_request_count = len(self.user_requests[key])

        if current_request_count >= burst_limit:
            return False

        # Record the request
        self.user_requests[key].append(current_time)
        return True

    async def check_ip_rate_limit(self, ip_address: str, endpoint: str) -> bool:
        """Check rate limits for IP address."""
        current_time = time.time()

        # Clean old requests
        self._clean_old_requests(self.ip_requests[ip_address], current_time, 60)

        # Check IP rate limits
        recent_requests = len(self.ip_requests[ip_address])

        if recent_requests >= self.ip_config.requests_per_minute:
            return False

        # Record the request
        self.ip_requests[ip_address].append(current_time)
        return True

    async def check_global_rate_limit(self, client_id: str) -> bool:
        """Check global rate limits."""
        current_time = time.time()

        # Clean old requests
        self._clean_old_requests(
            self.global_requests, current_time, 1
        )  # 1 second for global

        # Check global rate limits
        if (
            len(self.global_requests) >= self.global_config.requests_per_minute / 60
        ):  # per second
            return False

        # Record the request
        self.global_requests.append(current_time)
        return True

    def check_api_key_rate_limit(self, api_key: str) -> bool:
        """Check rate limits for API key."""
        current_time = time.time()
        key = f"api_key:{api_key}"

        if key not in self.rate_limits:
            return True

        # Clean old requests (older than 1 hour)
        self._clean_old_requests(self.api_key_requests[api_key], current_time, 3600)

        requests_per_hour = self.rate_limits[key]["requests_per_hour"]
        recent_requests = len(self.api_key_requests[api_key])

        if recent_requests >= requests_per_hour:
            return False

        # Record the request
        self.api_key_requests[api_key].append(current_time)
        return True

    def get_rate_limit_headers(self, client_id: str, endpoint: str) -> Dict[str, str]:
        """Get rate limit headers for response."""
        endpoint_limits = self.rate_limits.get(endpoint, {})
        requests_per_minute = endpoint_limits.get(
            "requests_per_minute", self.default_requests_per_minute
        )

        key = f"{client_id}:{endpoint}"
        current_time = time.time()

        # Count recent requests
        recent_requests = sum(
            1 for req_time in self.user_requests[key] if current_time - req_time <= 60
        )

        remaining = max(0, requests_per_minute - recent_requests)
        reset_time = int(current_time) + 60

        return {
            "X-RateLimit-Limit": str(requests_per_minute),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }

    def _clean_old_requests(
        self, request_deque: deque, current_time: float, window_seconds: int
    ):
        """Remove old requests outside the time window."""
        cutoff_time = current_time - window_seconds
        while request_deque and request_deque[0] < cutoff_time:
            request_deque.popleft()

    def enable_adaptive_limiting(
        self,
        base_requests_per_minute: int,
        load_threshold: float,
        reduction_factor: float,
    ):
        """Enable adaptive rate limiting based on system load."""
        self.enable_adaptive_limiting = True
        self.adaptive_config = {
            "base_requests_per_minute": base_requests_per_minute,
            "load_threshold": load_threshold,
            "reduction_factor": reduction_factor,
        }

    def get_current_rate_limit(self, client_id: str, endpoint: str) -> int:
        """Get current rate limit considering adaptive limiting."""
        base_limit = self.rate_limits.get(endpoint, {}).get(
            "requests_per_minute", self.default_requests_per_minute
        )

        if not self.enable_adaptive_limiting:
            return base_limit

        # Simulate system load check (would integrate with actual monitoring)
        system_load = self.get_system_load()

        if system_load > self.adaptive_config["load_threshold"]:
            return int(base_limit * self.adaptive_config["reduction_factor"])

        return base_limit

    def get_system_load(self) -> float:
        """Get current system load (mock implementation)."""
        # In real implementation, this would check actual system metrics
        return 0.5

    def configure_exemptions(
        self,
        exempt_ips: List[str] = None,
        exempt_user_agents: List[str] = None,
        exempt_api_keys: List[str] = None,
    ):
        """Configure exemptions from rate limiting."""
        self.exempt_ips = exempt_ips or []
        self.exempt_user_agents = exempt_user_agents or []
        self.exempt_api_keys = exempt_api_keys or []

    def is_exempt_from_rate_limiting(
        self, client_ip: str = None, user_agent: str = None, api_key: str = None
    ) -> bool:
        """Check if request is exempt from rate limiting."""
        # Check IP exemption
        if client_ip:
            for exempt_ip in self.exempt_ips:
                if self._ip_matches_pattern(client_ip, exempt_ip):
                    return True

        # Check user agent exemption
        if user_agent and user_agent in self.exempt_user_agents:
            return True

        # Check API key exemption
        if api_key and api_key in self.exempt_api_keys:
            return True

        return False

    def _ip_matches_pattern(self, ip: str, pattern: str) -> bool:
        """Check if IP matches pattern (supports CIDR notation)."""
        if "/" in pattern:
            # Simple CIDR check (would use ipaddress module in production)
            network = pattern.split("/")[0]
            return ip.startswith(network.rsplit(".", 1)[0])
        return ip == pattern
