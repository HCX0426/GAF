"""Gunicorn configuration for production deployment.

Tuned for GAF Django backend (WSGI). Tune via environment variables:
- GUNICORN_WORKERS (default: 4)
- GUNICORN_THREADS (default: 2)
- GUNICORN_TIMEOUT (default: 120)
- GUNICORN_MAX_REQUESTS (default: 1000)
- GUNICORN_PORT (default: 8000)
"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('GUNICORN_PORT', '8000')}"
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "50"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))

# Logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Process naming
proc_name = "gaf-gunicorn"

# Django settings module (must be set before WSGI load)
raw_env = ["DJANGO_SETTINGS_MODULE=config.settings.prod"]

# Security
limit_request_line = 8190
limit_request_fields = 100

# Preload app for faster worker boot and lower memory footprint
preload_app = True
