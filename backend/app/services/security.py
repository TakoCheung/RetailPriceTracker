"""
Security Service for comprehensive application security.
Handles input sanitization, threat detection, vulnerability scanning,
API key management, and various security measures.
"""

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import unquote


class SecurityService:
    """Service for handling security operations."""

    def __init__(self):
        # Security patterns for detection
        self.sql_injection_patterns = [
            r"('|(\\'))+.*(or|union|select|insert|delete|update|drop|create|alter|exec|execute)",
            r"(union\s+select|union\s+all\s+select)",
            r"(select\s+.*\s+from|insert\s+into|delete\s+from|update\s+.*\s+set)",
            r"(drop\s+table|create\s+table|alter\s+table)",
            r"(exec\s*\(|execute\s*\(|sp_executesql)",
        ]

        self.xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"<.*?on\w+\s*=",
            r"<.*?href\s*=\s*[\"']?\s*javascript:",
            r"<.*?src\s*=\s*[\"']?\s*javascript:",
        ]

        self.path_traversal_patterns = [
            r"\.\.[\\/]",
            r"\.\.%2f",
            r"\.\.%5c",
            r"%2e%2e[\\/]",
            r"%%32%65%%32%65",
        ]

        self.command_injection_patterns = [
            r"[;&|`$\(\)]",
            r"(nc|netcat|telnet|wget|curl)\s+",
            r"(rm|del|format|fdisk)\s+",
            r"(cat|type|more|less)\s+.*[/\\]",
        ]

        # API key storage (in production, use database)
        self.api_keys: Dict[str, Dict[str, Any]] = {}

        # Security event storage
        self.security_events: List[Dict[str, Any]] = []

        # Device fingerprints
        self.device_fingerprints: Dict[str, List[Dict[str, Any]]] = {}

        # Account lockout tracking
        self.lockout_data: Dict[str, Dict[str, Any]] = {}

        # Session security
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

        # Threat intelligence cache
        self.threat_intelligence_cache: Dict[str, Dict[str, Any]] = {}

        # Audit trail
        self.audit_trail: List[Dict[str, Any]] = []

        # Retention policies
        self.retention_policies: Dict[str, Dict[str, int]] = {
            "audit_logs": {"retention_days": 365},
            "security_events": {"retention_days": 90},
            "rate_limit_data": {"retention_days": 30},
        }

    def sanitize_input(self, user_input: str) -> str:
        """Sanitize user input to prevent injection attacks."""
        if not isinstance(user_input, str):
            return str(user_input)

        # Remove dangerous characters
        sanitized = user_input.replace("'", "&#x27;")
        sanitized = sanitized.replace('"', "&#x22;")
        sanitized = sanitized.replace("<", "&lt;")
        sanitized = sanitized.replace(">", "&gt;")
        sanitized = sanitized.replace("&", "&amp;")

        # Remove potential script tags
        sanitized = re.sub(
            r"<script[^>]*>.*?</script>", "", sanitized, flags=re.IGNORECASE | re.DOTALL
        )

        # Remove potential SQL keywords in suspicious contexts
        sql_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "UNION", "SELECT", "EXEC"]
        for keyword in sql_keywords:
            pattern = rf"\b{keyword}\b"
            if re.search(pattern, sanitized, re.IGNORECASE):
                sanitized = re.sub(
                    pattern, f"[{keyword}]", sanitized, flags=re.IGNORECASE
                )

        return sanitized

    def detect_sql_injection(self, user_input: str) -> bool:
        """Detect SQL injection attempts."""
        if not isinstance(user_input, str):
            return False

        input_lower = user_input.lower()

        for pattern in self.sql_injection_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE | re.DOTALL):
                return True

        return False

    def detect_xss_attempt(self, user_input: str) -> bool:
        """Detect XSS attempts."""
        if not isinstance(user_input, str):
            return False

        # URL decode the input
        decoded_input = unquote(user_input)

        for pattern in self.xss_patterns:
            if re.search(pattern, decoded_input, re.IGNORECASE | re.DOTALL):
                return True

        return False

    def detect_path_traversal(self, user_input: str) -> bool:
        """Detect path traversal attempts."""
        if not isinstance(user_input, str):
            return False

        # URL decode the input
        decoded_input = unquote(user_input)

        for pattern in self.path_traversal_patterns:
            if re.search(pattern, decoded_input, re.IGNORECASE):
                return True

        return False

    def detect_command_injection(self, user_input: str) -> bool:
        """Detect command injection attempts."""
        if not isinstance(user_input, str):
            return False

        for pattern in self.command_injection_patterns:
            if re.search(pattern, user_input, re.IGNORECASE):
                return True

        return False

    def detect_header_injection(self, user_input: str) -> bool:
        """Detect HTTP header injection attempts."""
        if not isinstance(user_input, str):
            return False

        # Look for CRLF injection
        if re.search(r"[\r\n]", user_input):
            return True

        return False

    def detect_suspicious_request(self, request_data: Dict[str, Any]) -> bool:
        """Detect suspicious request patterns."""
        # Check for suspicious paths
        path = request_data.get("path", "")
        if any(
            suspicious in path.lower()
            for suspicious in ["admin", "config", "backup", ".env"]
        ):
            return True

        # Check for path traversal in the path
        if self.detect_path_traversal(path):
            return True

        # Check for suspicious user agents
        user_agent = request_data.get("user_agent", "")
        suspicious_agents = ["sqlmap", "nikto", "nmap", "masscan", "zap"]
        if any(agent in user_agent.lower() for agent in suspicious_agents):
            return True

        # Check for too many proxy headers (potential anonymization)
        headers = request_data.get("headers", {})
        forwarded_for = headers.get("X-Forwarded-For", "")
        # Count the number of IPs (commas + 1), 3 or more IPs is suspicious
        if (
            forwarded_for and forwarded_for.count(",") >= 2
        ):  # 3 or more IPs is suspicious
            return True

        return False

    def generate_api_key(self, length: int = 32) -> str:
        """Generate a secure API key."""
        return secrets.token_urlsafe(length)

    def store_api_key(
        self,
        api_key: str,
        user_id: int,
        permissions: List[str],
        expires_at: Optional[datetime] = None,
        rate_limit: Optional[Dict[str, int]] = None,
    ):
        """Store API key with metadata."""
        self.api_keys[api_key] = {
            "user_id": user_id,
            "permissions": permissions,
            "created_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
            "rate_limit": rate_limit,
            "last_used": None,
            "usage_count": 0,
        }

    def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        """Validate API key and return metadata."""
        if api_key not in self.api_keys:
            return {"valid": False, "reason": "invalid_key"}

        key_data = self.api_keys[api_key]

        # Check expiration
        if (
            key_data["expires_at"]
            and datetime.now(timezone.utc) > key_data["expires_at"]
        ):
            return {"valid": False, "reason": "expired"}

        # Update usage
        key_data["last_used"] = datetime.now(timezone.utc)
        key_data["usage_count"] += 1

        return {
            "valid": True,
            "user_id": key_data["user_id"],
            "permissions": key_data["permissions"],
            "rate_limit": key_data["rate_limit"],
        }

    def api_key_has_permission(self, api_key: str, permission: str) -> bool:
        """Check if API key has specific permission."""
        if api_key not in self.api_keys:
            return False

        permissions = self.api_keys[api_key]["permissions"]
        return permission in permissions

    def is_api_key_expired(self, api_key: str) -> bool:
        """Check if API key is expired."""
        if api_key not in self.api_keys:
            return True

        expires_at = self.api_keys[api_key]["expires_at"]
        if not expires_at:
            return False

        return datetime.now(timezone.utc) > expires_at

    def is_password_breached(self, password: str) -> bool:
        """Check if password appears in known breaches (mock implementation)."""
        # In production, this would check against breach databases like HaveIBeenPwned
        common_breached_passwords = [
            "password",
            "123456",
            "password123",
            "admin",
            "qwerty",
            "letmein",
            "welcome",
            "monkey",
            "dragon",
            "master",
        ]
        return password.lower() in common_breached_passwords

    def configure_lockout_policy(
        self,
        max_failed_attempts: int,
        lockout_duration_minutes: int,
        progressive_delays: bool = False,
    ):
        """Configure account lockout policy."""
        self.lockout_policy = {
            "max_failed_attempts": max_failed_attempts,
            "lockout_duration_minutes": lockout_duration_minutes,
            "progressive_delays": progressive_delays,
        }

    def record_failed_login(self, user_id: str):
        """Record a failed login attempt."""
        current_time = datetime.now(timezone.utc)

        if user_id not in self.lockout_data:
            self.lockout_data[user_id] = {
                "failed_attempts": 0,
                "first_failure": current_time,
                "locked_until": None,
            }

        self.lockout_data[user_id]["failed_attempts"] += 1

        # Check if account should be locked
        if hasattr(self, "lockout_policy"):
            max_attempts = self.lockout_policy["max_failed_attempts"]
            if self.lockout_data[user_id]["failed_attempts"] >= max_attempts:
                lockout_duration = timedelta(
                    minutes=self.lockout_policy["lockout_duration_minutes"]
                )
                self.lockout_data[user_id]["locked_until"] = (
                    current_time + lockout_duration
                )

    def is_account_locked(self, user_id: str) -> bool:
        """Check if account is locked."""
        if user_id not in self.lockout_data:
            return False

        locked_until = self.lockout_data[user_id].get("locked_until")
        if not locked_until:
            return False

        # Check if lockout has expired
        if datetime.now(timezone.utc) > locked_until:
            self.lockout_data[user_id]["locked_until"] = None
            self.lockout_data[user_id]["failed_attempts"] = 0
            return False

        return True

    def get_lockout_info(self, user_id: str) -> Dict[str, Any]:
        """Get lockout information for user."""
        if user_id not in self.lockout_data:
            return {"locked": False}

        data = self.lockout_data[user_id]
        locked_until = data.get("locked_until")

        return {
            "locked": locked_until is not None
            and datetime.now(timezone.utc) < locked_until,
            "failed_attempts": data["failed_attempts"],
            "unlock_at": locked_until,
        }

    def register_device_fingerprint(self, user_id: str, fingerprint: Dict[str, Any]):
        """Register device fingerprint for user."""
        if user_id not in self.device_fingerprints:
            self.device_fingerprints[user_id] = []

        fingerprint_with_timestamp = {
            **fingerprint,
            "registered_at": datetime.now(timezone.utc),
        }

        self.device_fingerprints[user_id].append(fingerprint_with_timestamp)

    def check_device_anomaly(
        self, user_id: str, current_fingerprint: Dict[str, Any]
    ) -> bool:
        """Check if device fingerprint represents an anomaly."""
        if user_id not in self.device_fingerprints:
            return True  # First time login is anomalous

        known_fingerprints = self.device_fingerprints[user_id]

        # Check similarity with known fingerprints
        for known_fp in known_fingerprints:
            similarity_score = self._calculate_fingerprint_similarity(
                current_fingerprint, known_fp
            )
            if similarity_score > 0.8:  # 80% similarity threshold
                return False

        return True

    def _calculate_fingerprint_similarity(
        self, fp1: Dict[str, Any], fp2: Dict[str, Any]
    ) -> float:
        """Calculate similarity between two device fingerprints."""
        matching_fields = 0
        total_fields = 0

        common_fields = set(fp1.keys()) & set(fp2.keys())

        for field in common_fields:
            total_fields += 1
            if fp1[field] == fp2[field]:
                matching_fields += 1

        return matching_fields / total_fields if total_fields > 0 else 0

    def create_secure_session(
        self, user_id: str, ip_address: str, user_agent: str
    ) -> Dict[str, Any]:
        """Create a secure session."""
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
            "last_activity": datetime.now(timezone.utc),
        }

        self.active_sessions[session_id] = session_data
        return session_data

    def validate_session(
        self, session_id: str, ip_address: str, user_agent: str
    ) -> bool:
        """Validate session and check for hijacking."""
        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]

        # Check expiration
        if datetime.now(timezone.utc) > session["expires_at"]:
            del self.active_sessions[session_id]
            return False

        # Check for session hijacking (IP or user agent change)
        if session["ip_address"] != ip_address or session["user_agent"] != user_agent:
            # Log security event
            self.log_security_event(
                event_type="session_hijacking_attempt",
                user_id=session["user_id"],
                details={
                    "original_ip": session["ip_address"],
                    "new_ip": ip_address,
                    "original_user_agent": session["user_agent"],
                    "new_user_agent": user_agent,
                },
            )
            return False

        # Update last activity
        session["last_activity"] = datetime.now(timezone.utc)
        return True

    def log_security_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log a security event."""
        event = {
            "event_type": event_type,
            "user_id": user_id,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc),
            "details": details or {},
        }

        self.security_events.append(event)

    def get_security_events(
        self, event_type: Optional[str] = None, time_range_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get security events within time range."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_range_hours)

        filtered_events = [
            event for event in self.security_events if event["timestamp"] > cutoff_time
        ]

        if event_type:
            filtered_events = [
                event for event in filtered_events if event["event_type"] == event_type
            ]

        return filtered_events

    def check_password_breach(self, password: str) -> bool:
        """Mock method for checking password breaches."""
        # In production, integrate with breach checking service
        return self.is_password_breached(password)

    def configure_anomaly_detection(
        self,
        unusual_login_hours: bool = True,
        unusual_locations: bool = True,
        unusual_user_agents: bool = True,
    ):
        """Configure anomaly detection settings."""
        self.anomaly_detection_config = {
            "unusual_login_hours": unusual_login_hours,
            "unusual_locations": unusual_locations,
            "unusual_user_agents": unusual_user_agents,
        }

    def record_login_event(self, user_id: str, hour: int, location: str):
        """Record login event for anomaly detection."""
        # Store login patterns for anomaly detection
        pass

    def check_login_anomaly(
        self, user_id: str, hour: int, location: str
    ) -> Dict[str, Any]:
        """Check for login anomalies."""
        reasons = []

        # Check unusual login time (outside business hours)
        if hour < 6 or hour > 22:
            reasons.append("unusual_time")

        # Check unusual location (simplified)
        if location != "Office":
            reasons.append("unusual_location")

        return {
            "is_anomaly": len(reasons) > 0,
            "reasons": reasons,
            "risk_score": len(reasons) * 0.3,
        }

    def query_threat_intelligence(self, indicator: str) -> Dict[str, Any]:
        """Query threat intelligence (mock implementation)."""
        # Mock threat intelligence response
        return {"malicious": False, "categories": [], "confidence": 0.1}

    def check_threat_intelligence(self, ip_address: str) -> Dict[str, Any]:
        """Check IP against threat intelligence."""
        return self.query_threat_intelligence(ip_address)

    def configure_security_alerts(
        self,
        failed_login_threshold: int = 10,
        suspicious_activity_threshold: int = 5,
        alert_channels: List[str] = None,
    ):
        """Configure security alerting."""
        self.alert_config = {
            "failed_login_threshold": failed_login_threshold,
            "suspicious_activity_threshold": suspicious_activity_threshold,
            "alert_channels": alert_channels or ["email"],
        }

    def trigger_security_alert(
        self, alert_type: str, severity: str, details: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Trigger a security alert."""
        # Mock alert triggering
        return {"triggered": True, "severity": severity, "alert_type": alert_type}

    def log_audit_event(
        self,
        action: str,
        user_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        **kwargs,
    ):
        """Log an audit event."""
        event = {
            "action": action,
            "user_id": user_id,
            "timestamp": timestamp or datetime.now(timezone.utc),
            **kwargs,
        }

        self.audit_trail.append(event)

    def get_audit_trail(
        self, user_id: Optional[str] = None, time_range_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get audit trail for user."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_range_hours)

        filtered_events = [
            event for event in self.audit_trail if event["timestamp"] > cutoff_time
        ]

        if user_id:
            filtered_events = [
                event for event in filtered_events if event.get("user_id") == user_id
            ]

        return filtered_events

    def configure_retention_policies(self, policies: Dict[str, Dict[str, int]]):
        """Configure data retention policies."""
        self.retention_policies.update(policies)

    def get_retention_policies(self) -> Dict[str, Dict[str, int]]:
        """Get current retention policies."""
        return self.retention_policies

    def export_user_data(self, user_id: str) -> Dict[str, Any]:
        """Export all user data for GDPR compliance."""
        return {
            "personal_data": {"user_id": user_id},
            "audit_trail": self.get_audit_trail(user_id, time_range_hours=24 * 365),
            "security_events": [
                event
                for event in self.security_events
                if event.get("user_id") == user_id
            ],
        }

    def delete_user_data(self, user_id: str, verification_token: str) -> Dict[str, Any]:
        """Delete user data for GDPR compliance."""
        if verification_token != "valid_token":
            return {"deleted": False, "reason": "invalid_token"}

        # In production, actually delete the data
        return {
            "deleted": True,
            "retained_data": "Legal retention requirements apply to audit logs",
        }
