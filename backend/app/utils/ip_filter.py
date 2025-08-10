"""
IP Filtering Service for blocking and managing IP addresses.
Provides IP blocking, allowlisting, geolocation filtering,
automatic blocking, and reputation checking.
"""

import ipaddress
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from app.services.logging import LoggingService


class IPFilterService:
    """Service for IP filtering and blocking operations."""

    def __init__(self, logging_service: Optional[LoggingService] = None):
        self.logging_service = logging_service or LoggingService()

        # IP storage
        self.blocked_ips: Dict[str, Dict[str, Any]] = {}
        self.allowed_ips: Set[str] = set()
        self.rate_limited_ips: Dict[str, datetime] = {}

        # Temporary blocking
        self.temp_blocked_ips: Dict[str, Dict[str, Any]] = {}

        # Failed attempts tracking
        self.failed_attempts: Dict[str, deque] = defaultdict(deque)

        # Auto-blocking configuration
        self.auto_blocking_config = {
            "enabled": False,
            "failed_attempts_threshold": 5,
            "time_window_minutes": 10,
            "block_duration_hours": 1,
        }

        # Country blocking
        self.blocked_countries: Set[str] = set()

        # Threat intelligence cache
        self.threat_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl_hours = 24

    def block_ip(
        self, ip_address: str, reason: str, duration_hours: Optional[int] = None
    ):
        """Block an IP address permanently or temporarily."""
        block_data = {
            "reason": reason,
            "blocked_at": datetime.now(timezone.utc),
            "blocked_until": None,
            "permanent": duration_hours is None,
        }

        if duration_hours:
            block_data["blocked_until"] = datetime.now(timezone.utc) + timedelta(
                hours=duration_hours
            )
            block_data["permanent"] = False

        self.blocked_ips[ip_address] = block_data

        # Log the blocking action
        self.logging_service.log_security_event(
            event_type="ip_blocked",
            ip_address=ip_address,
            details={
                "reason": reason,
                "duration_hours": duration_hours,
                "permanent": block_data["permanent"],
            },
        )

    def unblock_ip(self, ip_address: str):
        """Unblock an IP address."""
        if ip_address in self.blocked_ips:
            del self.blocked_ips[ip_address]

            self.logging_service.log_security_event(
                event_type="ip_unblocked", ip_address=ip_address
            )

    def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if an IP address is currently blocked."""
        current_time = datetime.now(timezone.utc)

        # Check permanent blocks
        if ip_address in self.blocked_ips:
            block_data = self.blocked_ips[ip_address]

            # Check if temporary block has expired
            if not block_data["permanent"] and block_data["blocked_until"]:
                if current_time > block_data["blocked_until"]:
                    # Block has expired, remove it
                    del self.blocked_ips[ip_address]
                    return False

            return True

        # Check temporary blocks
        if ip_address in self.temp_blocked_ips:
            block_data = self.temp_blocked_ips[ip_address]
            if current_time > block_data["blocked_until"]:
                del self.temp_blocked_ips[ip_address]
                return False
            return True

        return False

    def get_block_reason(self, ip_address: str) -> Optional[str]:
        """Get the reason why an IP was blocked."""
        if ip_address in self.blocked_ips:
            return self.blocked_ips[ip_address]["reason"]
        if ip_address in self.temp_blocked_ips:
            return self.temp_blocked_ips[ip_address]["reason"]
        return None

    def add_to_allowlist(self, ip_address: str, note: str = ""):
        """Add IP to allowlist (always allowed)."""
        self.allowed_ips.add(ip_address)

        self.logging_service.log_security_event(
            event_type="ip_allowlisted", ip_address=ip_address, details={"note": note}
        )

    def remove_from_allowlist(self, ip_address: str):
        """Remove IP from allowlist."""
        self.allowed_ips.discard(ip_address)

    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if IP is in allowlist."""
        # Check exact match
        if ip_address in self.allowed_ips:
            return True

        # Check if IP is in any allowlisted network
        for allowed_ip in self.allowed_ips:
            if self._ip_in_network(ip_address, allowed_ip):
                return True

        return False

    def configure_country_blocking(self, blocked_countries: List[str]):
        """Configure country-based IP blocking."""
        self.blocked_countries = set(blocked_countries)

    def is_ip_blocked_by_country(self, ip_address: str) -> bool:
        """Check if IP is blocked based on country."""
        country = self.get_ip_country(ip_address)
        return country in self.blocked_countries

    def get_ip_country(self, ip_address: str) -> str:
        """Get country code for IP address (mock implementation)."""
        # In production, use GeoIP database or service
        mock_ip_countries = {
            "192.168.1.100": "US",
            "10.0.0.1": "CA",
            "1.2.3.4": "XX",  # Blocked country
        }
        return mock_ip_countries.get(ip_address, "US")

    def configure_auto_blocking(
        self,
        failed_attempts_threshold: int,
        time_window_minutes: int,
        block_duration_hours: int,
    ):
        """Configure automatic IP blocking based on failed attempts."""
        self.auto_blocking_config.update(
            {
                "enabled": True,
                "failed_attempts_threshold": failed_attempts_threshold,
                "time_window_minutes": time_window_minutes,
                "block_duration_hours": block_duration_hours,
            }
        )

    def record_failed_attempt(self, ip_address: str, reason: str):
        """Record a failed attempt from an IP address."""
        current_time = datetime.now(timezone.utc)

        # Add to failed attempts
        self.failed_attempts[ip_address].append(current_time)

        # Clean old attempts outside time window
        if self.auto_blocking_config["enabled"]:
            time_window = timedelta(
                minutes=self.auto_blocking_config["time_window_minutes"]
            )
            cutoff_time = current_time - time_window

            # Remove old attempts
            while (
                self.failed_attempts[ip_address]
                and self.failed_attempts[ip_address][0] < cutoff_time
            ):
                self.failed_attempts[ip_address].popleft()

            # Check if threshold exceeded
            if (
                len(self.failed_attempts[ip_address])
                >= self.auto_blocking_config["failed_attempts_threshold"]
            ):
                self.block_ip(
                    ip_address,
                    f"Automatic block: {len(self.failed_attempts[ip_address])} failed attempts - {reason}",
                    duration_hours=self.auto_blocking_config["block_duration_hours"],
                )

                # Clear failed attempts for this IP
                self.failed_attempts[ip_address].clear()

    def check_ip_reputation(self, ip_address: str) -> Dict[str, Any]:
        """Check IP reputation against threat intelligence."""
        # Check cache first
        if ip_address in self.threat_cache:
            cache_entry = self.threat_cache[ip_address]
            cache_time = cache_entry["cached_at"]
            if datetime.now(timezone.utc) - cache_time < timedelta(
                hours=self.cache_ttl_hours
            ):
                return cache_entry["data"]

        # Query threat intelligence
        reputation_data = self.check_threat_intelligence(ip_address)

        # Cache the result
        self.threat_cache[ip_address] = {
            "data": reputation_data,
            "cached_at": datetime.now(timezone.utc),
        }

        return reputation_data

    def check_threat_intelligence(self, ip_address: str) -> Dict[str, Any]:
        """Query threat intelligence feeds (mock implementation)."""
        # Mock threat intelligence data
        mock_threats = {
            "5.6.7.8": {
                "is_malicious": True,
                "categories": ["botnet", "spam"],
                "confidence": 0.95,
                "last_seen": "2024-01-15T10:30:00Z",
            }
        }

        return mock_threats.get(
            ip_address,
            {
                "is_malicious": False,
                "categories": [],
                "confidence": 0.1,
                "last_seen": None,
            },
        )

    def block_ip_temporarily(self, ip_address: str, block_until: datetime, reason: str):
        """Block IP temporarily until specified time."""
        self.temp_blocked_ips[ip_address] = {
            "reason": reason,
            "blocked_at": datetime.now(timezone.utc),
            "blocked_until": block_until,
        }

        self.logging_service.log_security_event(
            event_type="ip_temp_blocked",
            ip_address=ip_address,
            details={"reason": reason, "blocked_until": block_until.isoformat()},
        )

    def get_blocked_ips_summary(self) -> Dict[str, Any]:
        """Get summary of blocked IPs."""
        current_time = datetime.now(timezone.utc)

        permanent_blocks = sum(
            1 for data in self.blocked_ips.values() if data["permanent"]
        )
        temp_blocks = sum(
            1 for data in self.blocked_ips.values() if not data["permanent"]
        )

        # Count active temporary blocks
        active_temp_blocks = 0
        for data in self.temp_blocked_ips.values():
            if current_time < data["blocked_until"]:
                active_temp_blocks += 1

        return {
            "total_blocked": len(self.blocked_ips) + active_temp_blocks,
            "permanent_blocks": permanent_blocks,
            "temporary_blocks": temp_blocks + active_temp_blocks,
            "allowlisted_ips": len(self.allowed_ips),
            "auto_blocking_enabled": self.auto_blocking_config["enabled"],
        }

    def cleanup_expired_blocks(self):
        """Clean up expired temporary blocks."""
        current_time = datetime.now(timezone.utc)

        # Clean expired blocks from main list
        expired_ips = []
        for ip, data in self.blocked_ips.items():
            if (
                not data["permanent"]
                and data["blocked_until"]
                and current_time > data["blocked_until"]
            ):
                expired_ips.append(ip)

        for ip in expired_ips:
            del self.blocked_ips[ip]

        # Clean expired temporary blocks
        expired_temp_ips = []
        for ip, data in self.temp_blocked_ips.items():
            if current_time > data["blocked_until"]:
                expired_temp_ips.append(ip)

        for ip in expired_temp_ips:
            del self.temp_blocked_ips[ip]

        # Clean old threat intelligence cache
        expired_cache_ips = []
        for ip, cache_data in self.threat_cache.items():
            if current_time - cache_data["cached_at"] > timedelta(
                hours=self.cache_ttl_hours
            ):
                expired_cache_ips.append(ip)

        for ip in expired_cache_ips:
            del self.threat_cache[ip]

    def _ip_in_network(self, ip_address: str, network: str) -> bool:
        """Check if IP address is in network range."""
        try:
            if "/" in network:
                # CIDR notation
                return ipaddress.ip_address(ip_address) in ipaddress.ip_network(
                    network, strict=False
                )
            else:
                # Single IP
                return ip_address == network
        except (ipaddress.AddressValueError, ValueError):
            return False

    def get_failed_attempts_count(self, ip_address: str, minutes: int = None) -> int:
        """Get count of failed attempts for IP in time window."""
        if ip_address not in self.failed_attempts:
            return 0

        if minutes is None:
            return len(self.failed_attempts[ip_address])

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return sum(
            1
            for attempt_time in self.failed_attempts[ip_address]
            if attempt_time > cutoff_time
        )

    def reset_failed_attempts(self, ip_address: str):
        """Reset failed attempts counter for IP."""
        if ip_address in self.failed_attempts:
            self.failed_attempts[ip_address].clear()

    def export_blocked_ips(self) -> List[Dict[str, Any]]:
        """Export list of blocked IPs for backup/analysis."""
        blocked_list = []

        # Permanent and temporary blocks
        for ip, data in self.blocked_ips.items():
            blocked_list.append(
                {
                    "ip_address": ip,
                    "reason": data["reason"],
                    "blocked_at": data["blocked_at"].isoformat(),
                    "blocked_until": data["blocked_until"].isoformat()
                    if data["blocked_until"]
                    else None,
                    "permanent": data["permanent"],
                    "type": "main_block",
                }
            )

        # Temporary blocks
        for ip, data in self.temp_blocked_ips.items():
            blocked_list.append(
                {
                    "ip_address": ip,
                    "reason": data["reason"],
                    "blocked_at": data["blocked_at"].isoformat(),
                    "blocked_until": data["blocked_until"].isoformat(),
                    "permanent": False,
                    "type": "temp_block",
                }
            )

        return blocked_list

    def import_blocked_ips(self, blocked_list: List[Dict[str, Any]]):
        """Import blocked IPs from backup/external source."""
        for block_data in blocked_list:
            ip_address = block_data["ip_address"]

            if block_data["type"] == "main_block":
                self.blocked_ips[ip_address] = {
                    "reason": block_data["reason"],
                    "blocked_at": datetime.fromisoformat(block_data["blocked_at"]),
                    "blocked_until": datetime.fromisoformat(block_data["blocked_until"])
                    if block_data["blocked_until"]
                    else None,
                    "permanent": block_data["permanent"],
                }
            elif block_data["type"] == "temp_block":
                self.temp_blocked_ips[ip_address] = {
                    "reason": block_data["reason"],
                    "blocked_at": datetime.fromisoformat(block_data["blocked_at"]),
                    "blocked_until": datetime.fromisoformat(
                        block_data["blocked_until"]
                    ),
                }
