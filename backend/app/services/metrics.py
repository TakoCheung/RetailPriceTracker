"""
Error metrics and monitoring service.
Tracks error rates, trends, and provides alerting capabilities.
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services.logging import get_logger


class ErrorMetricsService:
    """Service for tracking and analyzing error metrics."""

    def __init__(self):
        self.logger = get_logger("error_metrics")

        # Error tracking storage (in production, use Redis or database)
        self.error_counts = defaultdict(
            lambda: defaultdict(int)
        )  # error_type -> time_bucket -> count
        self.error_history = defaultdict(
            lambda: deque(maxlen=1000)
        )  # error_type -> list of timestamps
        self.error_contexts = defaultdict(list)  # error_type -> list of context data
        self.thresholds = {}  # error_type -> threshold config

    def track_error(
        self, error_type: str, component: str, context: Optional[Dict[str, Any]] = None
    ):
        """Track an error occurrence."""
        now = datetime.now(timezone.utc)
        timestamp = now.timestamp()

        # Update counters
        time_bucket = self._get_time_bucket(now, minutes=5)
        self.error_counts[error_type][time_bucket] += 1

        # Add to history
        self.error_history[error_type].append(timestamp)

        # Store context
        if context:
            self.error_contexts[error_type].append(
                {"timestamp": timestamp, "component": component, "context": context}
            )

        self.logger.info(
            "Error tracked", error_type=error_type, component=component, context=context
        )

    def track_error_with_context(
        self, error_type: str, component: str, context: Dict[str, Any]
    ):
        """Track error with additional context for correlation analysis."""
        self.track_error(error_type, component, context)

    def get_error_rates(
        self, time_window_minutes: int = 60
    ) -> Dict[str, Dict[str, Any]]:
        """Get error rates for the specified time window."""
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=time_window_minutes)
        cutoff_timestamp = cutoff_time.timestamp()

        error_rates = {}

        for error_type, timestamps in self.error_history.items():
            # Count errors in time window
            recent_errors = [ts for ts in timestamps if ts >= cutoff_timestamp]

            error_rates[error_type] = {
                "count": len(recent_errors),
                "rate_per_minute": len(recent_errors) / time_window_minutes,
                "window_minutes": time_window_minutes,
            }

        return error_rates

    def get_error_trends(self, hours: int = 24) -> Dict[str, Dict[str, Any]]:
        """Analyze error trends over the specified time period."""
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=hours)
        cutoff_timestamp = cutoff_time.timestamp()

        trends = {}

        for error_type, timestamps in self.error_history.items():
            recent_errors = [ts for ts in timestamps if ts >= cutoff_timestamp]

            if len(recent_errors) < 2:
                trend = "insufficient_data"
            else:
                # Simple trend analysis - compare first and second half
                mid_point = cutoff_timestamp + (now.timestamp() - cutoff_timestamp) / 2
                first_half = len([ts for ts in recent_errors if ts < mid_point])
                second_half = len([ts for ts in recent_errors if ts >= mid_point])

                if second_half > first_half * 1.2:
                    trend = "increasing"
                elif second_half < first_half * 0.8:
                    trend = "decreasing"
                else:
                    trend = "stable"

            trends[error_type] = {
                "trend": trend,
                "total_count": len(recent_errors),
                "average_per_hour": len(recent_errors) / hours,
            }

        return trends

    def set_error_threshold(
        self, error_type: str, count: int, time_window_minutes: int
    ):
        """Set alerting threshold for an error type."""
        self.thresholds[error_type] = {
            "count": count,
            "time_window_minutes": time_window_minutes,
        }

        self.logger.info(
            "Error threshold configured",
            error_type=error_type,
            threshold_count=count,
            time_window_minutes=time_window_minutes,
        )

    def check_thresholds(self) -> List[Dict[str, Any]]:
        """Check if any error thresholds have been exceeded."""
        alerts = []

        for error_type, threshold in self.thresholds.items():
            rates = self.get_error_rates(threshold["time_window_minutes"])

            if error_type in rates:
                current_count = rates[error_type]["count"]

                if current_count >= threshold["count"]:
                    alert = {
                        "error_type": error_type,
                        "current_count": current_count,
                        "threshold_count": threshold["count"],
                        "time_window_minutes": threshold["time_window_minutes"],
                        "severity": "critical"
                        if current_count >= threshold["count"] * 2
                        else "warning",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    alerts.append(alert)

                    self.logger.warning("Error threshold exceeded", **alert)

        return alerts

    def analyze_error_correlations(self, error_type: str) -> Dict[str, Any]:
        """Analyze correlations between errors and system metrics."""
        contexts = self.error_contexts.get(error_type, [])

        if not contexts:
            return {}

        # Analyze context data for patterns
        correlations = {}

        # Collect all context keys
        all_keys = set()
        for ctx_data in contexts:
            if "context" in ctx_data:
                all_keys.update(ctx_data["context"].keys())

        # Calculate averages for numeric values
        for key in all_keys:
            values = []
            for ctx_data in contexts:
                if "context" in ctx_data and key in ctx_data["context"]:
                    value = ctx_data["context"][key]
                    if isinstance(value, (int, float)):
                        values.append(value)

            if values:
                correlations[key] = {
                    "average": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "sample_count": len(values),
                }

        return correlations

    def _get_time_bucket(self, dt: datetime, minutes: int = 5) -> str:
        """Get time bucket for grouping errors."""
        # Round down to nearest time bucket
        bucket_start = dt.replace(
            minute=(dt.minute // minutes) * minutes, second=0, microsecond=0
        )
        return bucket_start.isoformat()

    def get_error_summary(self) -> Dict[str, Any]:
        """Get overall error summary statistics."""
        now = datetime.now(timezone.utc)

        # Get error counts for different time windows
        last_hour = self.get_error_rates(60)
        last_day = self.get_error_rates(24 * 60)

        total_errors_hour = sum(data["count"] for data in last_hour.values())
        total_errors_day = sum(data["count"] for data in last_day.values())

        return {
            "timestamp": now.isoformat(),
            "total_error_types": len(self.error_history),
            "errors_last_hour": total_errors_hour,
            "errors_last_day": total_errors_day,
            "top_error_types": self._get_top_errors(last_hour),
            "active_alerts": len(self.check_thresholds()),
        }

    def _get_top_errors(
        self, error_rates: Dict[str, Dict[str, Any]], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top error types by count."""
        sorted_errors = sorted(
            error_rates.items(), key=lambda x: x[1]["count"], reverse=True
        )

        return [
            {"error_type": error_type, "count": data["count"]}
            for error_type, data in sorted_errors[:limit]
        ]
