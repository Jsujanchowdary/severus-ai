"""
Prometheus metrics for Severus AI application.

This module defines and exposes metrics for monitoring:
- User activity (logins, chats, messages)
- Ollama API calls
- HTTP requests and errors
- Application uptime
- Active sessions
"""

import os
# Must be set BEFORE prometheus_client imports any metrics
if "prometheus_multiproc_dir" not in os.environ:
    os.environ["prometheus_multiproc_dir"] = "/app/data/metrics"

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import time

# ======================================================
# COUNTERS - Monotonically increasing values
# ======================================================

# User activity
LOGIN_COUNT = Counter(
    "severus_login_total",
    "Total number of successful logins"
)

LOGIN_FAILURES = Counter(
    "severus_login_failures_total",
    "Total number of failed login attempts",
    ["reason"]  # Labels: invalid_credentials, user_not_found
)

SIGNUP_COUNT = Counter(
    "severus_signup_total",
    "Total number of user signups"
)

# Chat activity
CHAT_CREATED = Counter(
    "severus_chat_created_total",
    "Total number of chats created"
)

MESSAGES_SENT = Counter(
    "severus_messages_sent_total",
    "Total number of messages sent",
    ["role"]  # Labels: user, assistant
)

CHAT_DELETED = Counter(
    "severus_chat_deleted_total",
    "Total number of chats deleted"
)

# File uploads
FILE_UPLOADS = Counter(
    "severus_file_uploads_total",
    "Total number of files uploaded",
    ["file_type"]  # Labels: pdf, csv, image, etc.
)

# Ollama API
OLLAMA_CALLS = Counter(
    "severus_ollama_calls_total",
    "Total number of Ollama API calls",
    ["model", "status"]  # Labels: model name, success/error
)

# HTTP requests
HTTP_REQUESTS = Counter(
    "severus_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

# Errors
ERRORS_TOTAL = Counter(
    "severus_errors_total",
    "Total application errors",
    ["error_type"]  # Labels: ollama_error, file_error, db_error, etc.
)

# Certificate verification
CERT_VERIFICATION_SUCCESS = Counter(
    "severus_cert_verification_success_total",
    "Total successful certificate verifications"
)

CERT_VERIFICATION_FAILURE = Counter(
    "severus_cert_verification_failure_total",
    "Total failed certificate verifications",
    ["reason"]  # Labels: missing, invalid_signature, expired, etc.
)

# ======================================================
# HISTOGRAMS - Distribution of values
# ======================================================

OLLAMA_REQUEST_DURATION = Histogram(
    "severus_ollama_request_duration_seconds",
    "Duration of Ollama API requests in seconds",
    ["model"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
)

HTTP_REQUEST_DURATION = Histogram(
    "severus_http_request_duration_seconds",
    "Duration of HTTP requests in seconds",
    ["endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# ======================================================
# GAUGES - Values that can go up or down
# ======================================================

ACTIVE_USERS = Gauge(
    "severus_active_users",
    "Number of currently active users (sessions)"
)

ACTIVE_CHATS = Gauge(
    "severus_active_chats",
    "Total number of active chats in the system"
)

POD_UPTIME = Gauge(
    "severus_pod_uptime_seconds",
    "Time since application started in seconds"
)

# Track application start time
APP_START_TIME = time.time()

# ======================================================
# HELPER FUNCTIONS
# ======================================================

def update_uptime():
    """Update the pod uptime metric."""
    POD_UPTIME.set(time.time() - APP_START_TIME)

def get_metrics():
    """
    Generate Prometheus metrics in text format.
    
    Returns:
        tuple: (metrics_data, content_type)
    """
    update_uptime()
    return generate_latest(), CONTENT_TYPE_LATEST

def track_login_success():
    """Track successful login."""
    LOGIN_COUNT.inc()

def track_login_failure(reason="invalid_credentials"):
    """Track failed login attempt."""
    LOGIN_FAILURES.labels(reason=reason).inc()

def track_signup():
    """Track user signup."""
    SIGNUP_COUNT.inc()

def track_chat_created():
    """Track chat creation."""
    CHAT_CREATED.inc()

def track_message(role):
    """Track message sent."""
    MESSAGES_SENT.labels(role=role).inc()

def track_chat_deleted():
    """Track chat deletion."""
    CHAT_DELETED.inc()

def track_file_upload(file_type):
    """Track file upload."""
    FILE_UPLOADS.labels(file_type=file_type).inc()

def track_ollama_call(model, duration, success=True):
    """
    Track Ollama API call.
    
    Args:
        model: Model name
        duration: Request duration in seconds
        success: Whether the call was successful
    """
    status = "success" if success else "error"
    OLLAMA_CALLS.labels(model=model, status=status).inc()
    OLLAMA_REQUEST_DURATION.labels(model=model).observe(duration)

def track_error(error_type):
    """Track application error."""
    ERRORS_TOTAL.labels(error_type=error_type).inc()

def track_http_request(method, endpoint, status, duration):
    """Track HTTP request."""
    HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status=status).inc()
    HTTP_REQUEST_DURATION.labels(endpoint=endpoint).observe(duration)

def track_cert_verification_success():
    """Track successful certificate verification."""
    CERT_VERIFICATION_SUCCESS.inc()

def track_cert_verification_failure(reason="invalid"):
    """Track failed certificate verification."""
    CERT_VERIFICATION_FAILURE.labels(reason=reason).inc()

