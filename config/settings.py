"""
Django settings for LabTrack production project.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv

CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-cart-every-10-minutes': {
        'task': 'inventory.tasks.cleanup_expired_reservations',
        'schedule': 600.0,  # every 10 minutes
    },
    'request-due-reminders-daily': {
        'task': 'requests_app.tasks.send_due_reminders',
        'schedule': 86400.0,  # daily
    },
    'request-overdue-status-daily': {
        'task': 'requests_app.tasks.update_overdue_requests',
        'schedule': 86400.0,  # daily
    },
}


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Production vs Development environment detection
ENVIRONMENT = os.getenv("DJANGO_ENV", "production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
if ("runserver" in sys.argv or "test" in sys.argv) and os.getenv("DJANGO_DEBUG") is None:
    DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG and ENVIRONMENT == "production":
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY environment variable is required in production mode."
        )
    SECRET_KEY = "lbt!9cvq7g6e2l@#5!f8cbl12uwvud1p=w*1b9#0gi3q!t$z6o"

_allowed_hosts_str = os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_str.split(",") if h.strip()]

_csrf_origins_str = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins_str.split(",") if o.strip()]

# Security hardening (HTTPS + cookies)
_default_ssl_redirect = not DEBUG and ENVIRONMENT == "production"
SECURE_SSL_REDIRECT = os.getenv(
    "DJANGO_SECURE_SSL_REDIRECT", str(_default_ssl_redirect)
).lower() == "true"
SECURE_HSTS_SECONDS = int(
    os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "True" if not DEBUG else "False").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "True" if not DEBUG else "False").lower() == "true"


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'users',
    'inventory',
    'requests_app',
    'notifications',
    'api',
]


MIDDLEWARE = [
    'config.middleware.RequestIDAndPerformanceMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'users.middleware.NoStoreForAuthenticatedPagesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# Supports PostgreSQL / MySQL via DATABASE_URL or defaults to SQLite with WAL mode

_db_url = os.getenv("DATABASE_URL")
if _db_url:
    DATABASES = {
        'default': dj_database_url.config(
            default=_db_url,
            conn_max_age=int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "60")),
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'CONN_MAX_AGE': int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "60")),
            'OPTIONS': {
                'timeout': 20,
                'transaction_mode': 'IMMEDIATE',
            },
        }
    }

# Cache backend (default: in-memory; production recommended: Redis)
_cache_backend = os.getenv("DJANGO_CACHE_BACKEND", "locmem").lower()
if _cache_backend == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("DJANGO_CACHE_URL", "redis://127.0.0.1:6379/1"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "labtrack-local-cache",
        }
    }

SESSION_ENGINE = os.getenv(
    "DJANGO_SESSION_ENGINE",
    "django.contrib.sessions.backends.cached_db",
)
SESSION_CACHE_ALIAS = "default"

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True

EMAIL_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_FROM_EMAIL", "labtrack@localhost")
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Authentication / OTP throttling (seconds + max attempts within window)
AUTH_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "600"))
SIGNUP_OTP_VERIFY_RATE_LIMIT = int(os.getenv("SIGNUP_OTP_VERIFY_RATE_LIMIT", "10"))
PASSWORD_RESET_OTP_VERIFY_RATE_LIMIT = int(os.getenv("PASSWORD_RESET_OTP_VERIFY_RATE_LIMIT", "10"))
PASSWORD_RESET_REQUEST_RATE_LIMIT = int(os.getenv("PASSWORD_RESET_REQUEST_RATE_LIMIT", "5"))
OTP_RESEND_RATE_LIMIT = int(os.getenv("OTP_RESEND_RATE_LIMIT", "5"))
API_TOKEN_ISSUE_RATE_LIMIT = int(os.getenv("API_TOKEN_ISSUE_RATE_LIMIT", "20"))
API_TOKEN_MAX_AGE_DAYS = int(os.getenv("API_TOKEN_MAX_AGE_DAYS", "30"))
API_TOKEN_IDLE_TIMEOUT_SECONDS = int(os.getenv("API_TOKEN_IDLE_TIMEOUT_SECONDS", "1209600"))


# Celery Configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE


# Static and Media files configuration
STATIC_URL = os.getenv("DJANGO_STATIC_URL", "/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

MEDIA_URL = os.getenv("DJANGO_MEDIA_URL", "/media/")
MEDIA_ROOT = BASE_DIR / "media"


# Structured Production Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO' if not DEBUG else 'DEBUG',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'users': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'inventory': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'requests_app': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'api': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
