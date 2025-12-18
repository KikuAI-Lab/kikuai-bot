"""Prometheus metrics for payment monitoring."""

from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps
from typing import Callable
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Payment Metrics
# ============================================================================

# Counters
payment_requests_total = Counter(
    "kikuai_payment_requests_total",
    "Total payment requests",
    ["method", "status"]
)

webhook_events_total = Counter(
    "kikuai_webhook_events_total",
    "Total webhook events received",
    ["provider", "event_type", "status"]
)

payment_errors_total = Counter(
    "kikuai_payment_errors_total",
    "Total payment errors",
    ["method", "error_type"]
)

# Histograms
payment_processing_duration = Histogram(
    "kikuai_payment_processing_duration_seconds",
    "Payment processing duration in seconds",
    ["method"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

webhook_processing_duration = Histogram(
    "kikuai_webhook_processing_duration_seconds",
    "Webhook processing duration in seconds",
    ["provider"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)

api_request_duration = Histogram(
    "kikuai_external_api_duration_seconds",
    "External API request duration in seconds",
    ["provider", "endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

# Gauges
active_payments = Gauge(
    "kikuai_active_payments",
    "Number of pending payments",
    ["method"]
)


# ============================================================================
# Metric Helpers
# ============================================================================

def track_payment_request(method: str, status: str):
    """Track payment request."""
    payment_requests_total.labels(method=method, status=status).inc()


def track_webhook_event(provider: str, event_type: str, status: str):
    """Track webhook event."""
    webhook_events_total.labels(
        provider=provider,
        event_type=event_type,
        status=status
    ).inc()


def track_payment_error(method: str, error_type: str):
    """Track payment error."""
    payment_errors_total.labels(method=method, error_type=error_type).inc()


class PaymentTimer:
    """Context manager for timing payment operations."""
    
    def __init__(self, method: str):
        self.method = method
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        payment_processing_duration.labels(method=self.method).observe(duration)


class WebhookTimer:
    """Context manager for timing webhook processing."""
    
    def __init__(self, provider: str):
        self.provider = provider
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        webhook_processing_duration.labels(provider=self.provider).observe(duration)


def track_api_request(provider: str, endpoint: str):
    """Decorator to track external API requests."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                api_request_duration.labels(
                    provider=provider,
                    endpoint=endpoint
                ).observe(duration)
        return wrapper
    return decorator


# ============================================================================
# Dashboard Helpers
# ============================================================================

def get_payment_success_rate(method: str = None) -> float:
    """Calculate payment success rate."""
    try:
        if method:
            success = payment_requests_total.labels(method=method, status="success")._value.get()
            failed = payment_requests_total.labels(method=method, status="failed")._value.get()
        else:
            success = sum(
                payment_requests_total.labels(method=m, status="success")._value.get()
                for m in ["paddle", "telegram_stars"]
            )
            failed = sum(
                payment_requests_total.labels(method=m, status="failed")._value.get()
                for m in ["paddle", "telegram_stars"]
            )
        
        total = success + failed
        return (success / total * 100) if total > 0 else 0.0
    except Exception:
        return 0.0


def get_metrics_summary() -> dict:
    """Get summary of all metrics."""
    return {
        "payment_success_rate": get_payment_success_rate(),
        "paddle_success_rate": get_payment_success_rate("paddle"),
        "stars_success_rate": get_payment_success_rate("telegram_stars"),
    }
