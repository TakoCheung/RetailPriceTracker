"""
Structured logging service for the Retail Price Tracker application.
Provides centralized logging configuration with structured output,
performance monitoring, security event logging, and correlation tracking.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pythonjsonlogger import jsonlogger


class StructuredFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]):
        """Add custom fields to log records."""
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO format
        log_record['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        # Add service information
        log_record['service'] = 'retail-price-tracker'
        log_record['logger_name'] = record.name
        
        # Add correlation ID if available
        if hasattr(record, 'correlation_id'):
            log_record['correlation_id'] = record.correlation_id
        
        # Add request ID if available
        if hasattr(record, 'request_id'):
            log_record['request_id'] = record.request_id


class StructuredLogger:
    """Enhanced logger with structured logging capabilities."""
    
    def __init__(self, name: str, level: str = "INFO"):
        self.name = name
        self.level = getattr(logging, level.upper())
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.level)
        
        # Add structured formatter
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = StructuredFormatter(
                fmt='%(timestamp)s %(name)s %(levelname)s %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    @property
    def handlers(self):
        """Get logger handlers."""
        return self.logger.handlers
    
    def _log_with_extra(self, level: str, message: str, **kwargs):
        """Log message with extra structured data."""
        extra = {}
        for key, value in kwargs.items():
            if key not in ['exc_info', 'stack_info', 'stacklevel']:
                extra[key] = value
        
        log_method = getattr(self.logger, level.lower())
        log_method(message, extra=extra, **{k: v for k, v in kwargs.items() if k in ['exc_info']})
    
    def info(self, message: str, **kwargs):
        """Log info message with structured data."""
        self._log_with_extra('info', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message with structured data."""
        self._log_with_extra('error', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with structured data."""
        self._log_with_extra('warning', message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log debug message with structured data."""
        self._log_with_extra('debug', message, **kwargs)
    
    def performance(self, message: str, **kwargs):
        """Log performance metrics."""
        kwargs['log_type'] = 'performance'
        self.info(message, **kwargs)
    
    def security(self, message: str, level: str = "WARNING", **kwargs):
        """Log security events."""
        kwargs['log_type'] = 'security'
        log_method = getattr(self, level.lower())
        log_method(message, **kwargs)


class LoggingService:
    """Centralized logging service with configuration management."""
    
    def __init__(
        self,
        log_level: str = "INFO",
        log_format: str = "json",
        log_file: Optional[str] = None,
        max_file_size: str = "10MB",
        backup_count: int = 5,
        retention_days: int = 30,
        compress_logs: bool = True
    ):
        self.log_level = log_level
        self.log_format = log_format
        self.log_file = log_file
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.retention_days = retention_days
        self.compress_logs = compress_logs
        self.is_configured = False
        
        self._configure_logging()
    
    def _configure_logging(self):
        """Configure global logging settings."""
        # Set root logger level
        logging.getLogger().setLevel(getattr(logging, self.log_level.upper()))
        
        # Configure file logging if specified
        if self.log_file:
            self._setup_file_logging()
        
        self.is_configured = True
    
    def _setup_file_logging(self):
        """Set up file logging with rotation."""
        log_file_path = Path(self.log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Parse max file size
        max_bytes = self._parse_file_size(self.max_file_size)
        
        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_file,
            maxBytes=max_bytes,
            backupCount=self.backup_count
        )
        
        # Set formatter
        if self.log_format == "json":
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        file_handler.setFormatter(formatter)
        
        # Add to root logger
        logging.getLogger().addHandler(file_handler)
    
    def _parse_file_size(self, size_str: str) -> int:
        """Parse file size string to bytes."""
        size_str = size_str.upper()
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)  # Assume bytes
    
    def get_logger(self, name: str) -> StructuredLogger:
        """Get a structured logger instance."""
        return StructuredLogger(name, self.log_level)
    
    def configure_correlation_context(self, correlation_id: str, request_id: str = None):
        """Configure correlation context for request tracking."""
        # This would typically be used with context managers or middleware
        # to automatically add correlation IDs to all log messages
        pass


# Global logging service instance
_logging_service: Optional[LoggingService] = None


def get_logging_service() -> LoggingService:
    """Get the global logging service instance."""
    global _logging_service
    if _logging_service is None:
        _logging_service = LoggingService()
    return _logging_service


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return get_logging_service().get_logger(name)
