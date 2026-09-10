"""
Gunicorn production server configuration for LabTrack.
"""

import multiprocessing
import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8001")
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.getenv("GUNICORN_THREADS", 2))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")

timeout = int(os.getenv("GUNICORN_TIMEOUT", 60))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))

# Prevent memory leaks with periodic worker restarts
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 100))

# Logging configuration
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# Security settings
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
