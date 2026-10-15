import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "django-insecure-test-key-for-agent-audit-prototype"

# Set DEBUG to False so that unhandled exceptions trigger 500 error handlers and middleware
DEBUG = False

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "demo_app",
    "core_audit",
]

MIDDLEWARE = [
    "core_audit.middleware.AuditExceptionMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "demo_app.urls"

WSGI_APPLICATION = "wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Logging configuration integrating our custom AuditLoggingHandler
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
        "audit_agent_handler": {
            "class": "core_audit.handlers.AuditLoggingHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console", "audit_agent_handler"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
