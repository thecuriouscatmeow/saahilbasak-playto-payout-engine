import os
import urllib.parse as _urlparse
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-prod")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
    "apps.merchants",
    "apps.payouts",
]

MIDDLEWARE = [
    "observability.middleware.CorrelationIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

_db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:playto@localhost:5432/playto")
_parsed = _urlparse.urlparse(_db_url)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _parsed.path.lstrip("/"),
        "USER": _parsed.username or "postgres",
        "PASSWORD": _parsed.password or "",
        "HOST": _parsed.hostname or "localhost",
        "PORT": str(_parsed.port or 5432),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.payouts.api.exceptions.custom_exception_handler",
}

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 30
CELERY_BEAT_SCHEDULE = {
    "sweep-stale": {
        "task": "payouts.sweep_stale",
        "schedule": 10.0,
    },
    "expire-idempotency": {
        "task": "payouts.expire_idempotency",
        "schedule": crontab(hour=3, minute=0),
    },
}

CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# Configure structlog at settings load time
from observability.logging import configure_logging
configure_logging()
