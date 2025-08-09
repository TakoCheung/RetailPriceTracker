"""
Health check service for monitoring system components.
Provides health status for database, cache, external services, and overall system health.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.services.cache import CacheService
from app.services.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthCheckService:
    """Service for checking the health of system components."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.checks: List[Dict[str, Any]] = []
        self.logger = get_logger("health_check")

    async def check_database_health(self, db_session: AsyncSession) -> Dict[str, Any]:
        """Check database connectivity and performance."""
        start_time = time.time()

        try:
            # Simple query to test connectivity
            result = await db_session.execute(text("SELECT 1"))
            result.fetchone()

            response_time = (time.time() - start_time) * 1000

            return {
                "component": "database",
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "details": {"connection": "ok", "query_execution": "ok"},
            }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000

            self.logger.error(
                "Database health check failed",
                error=str(e),
                response_time_ms=response_time,
            )

            return {
                "component": "database",
                "status": "unhealthy",
                "response_time_ms": round(response_time, 2),
                "error": str(e),
                "details": {"connection": "failed"},
            }

    async def check_cache_health(self) -> Dict[str, Any]:
        """Check cache service health."""
        start_time = time.time()

        try:
            cache_service = CacheService()
            await cache_service.connect()

            # Test basic cache operations
            test_key = "health_check_test"
            test_value = {"timestamp": datetime.now(timezone.utc).isoformat()}

            await cache_service.set(test_key, test_value, expire=10)
            retrieved_value = await cache_service.get(test_key)

            await cache_service.disconnect()

            response_time = (time.time() - start_time) * 1000

            if retrieved_value == test_value:
                return {
                    "component": "cache",
                    "status": "healthy",
                    "response_time_ms": round(response_time, 2),
                    "details": {"connection": "ok", "read_write": "ok"},
                }
            else:
                return {
                    "component": "cache",
                    "status": "unhealthy",
                    "response_time_ms": round(response_time, 2),
                    "error": "Cache read/write test failed",
                    "details": {"connection": "ok", "read_write": "failed"},
                }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000

            self.logger.error(
                "Cache health check failed",
                error=str(e),
                response_time_ms=response_time,
            )

            return {
                "component": "cache",
                "status": "unhealthy",
                "response_time_ms": round(response_time, 2),
                "error": str(e),
                "details": {"connection": "failed"},
            }

    async def check_external_service_health(self, service_name: str) -> Dict[str, Any]:
        """Check external service health."""
        start_time = time.time()

        try:
            # This would typically make HTTP requests to external services
            # For now, we'll simulate the check
            if service_name == "price_scraper_api":
                # Simulate external API check
                await asyncio.sleep(0.1)  # Simulate network request

                response_time = (time.time() - start_time) * 1000

                return {
                    "component": service_name,
                    "status": "healthy",
                    "response_time_ms": round(response_time, 2),
                    "details": {"endpoint": "reachable", "authentication": "ok"},
                }
            else:
                # Unknown service
                return {
                    "component": service_name,
                    "status": "unknown",
                    "response_time_ms": 0,
                    "error": f"Unknown service: {service_name}",
                }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000

            self.logger.error(
                "External service health check failed",
                service=service_name,
                error=str(e),
                response_time_ms=response_time,
            )

            return {
                "component": service_name,
                "status": "unhealthy",
                "response_time_ms": round(response_time, 2),
                "error": str(e),
            }

    async def run_all_checks(self, db_session: AsyncSession) -> Dict[str, Any]:
        """Run all health checks and return comprehensive status."""
        start_time = time.time()

        try:
            # Run all checks with timeout
            check_tasks = [
                asyncio.wait_for(self.check_database_health(db_session), self.timeout),
                asyncio.wait_for(self.check_cache_health(), self.timeout),
                asyncio.wait_for(
                    self.check_external_service_health("price_scraper_api"),
                    self.timeout,
                ),
            ]

            results = await asyncio.gather(*check_tasks, return_exceptions=True)

            # Process results
            components = []
            overall_healthy = True

            for result in results:
                if isinstance(result, Exception):
                    # Handle timeout or other exceptions
                    component_result = {
                        "component": "unknown",
                        "status": "timeout",
                        "error": str(result),
                    }
                    overall_healthy = False
                else:
                    component_result = result
                    if result["status"] != "healthy":
                        overall_healthy = False

                components.append(component_result)

            total_time = (time.time() - start_time) * 1000

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_status": "healthy" if overall_healthy else "unhealthy",
                "response_time_ms": round(total_time, 2),
                "components": components,
            }

        except Exception as e:
            self.logger.error("Health check execution failed", error=str(e))

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_status": "unhealthy",
                "error": str(e),
                "components": [],
            }
