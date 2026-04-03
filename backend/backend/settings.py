import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env so OPENAI_API_KEY and other env vars are available (e.g. for ai_layer)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# ── GDAL / GEOS path (Windows — cgohlke wheel bundles DLLs inside osgeo) ──
# Django searches for e.g. "gdal311.dll" by version number, but the cgohlke
# wheel ships a single "gdal.dll". Point GeoDjango directly to it.
import sys
_osgeo_dir = BASE_DIR / "venv" / "Lib" / "site-packages" / "osgeo"
if sys.platform == "win32" and _osgeo_dir.exists():
    GDAL_LIBRARY_PATH = str(_osgeo_dir / "gdal.dll")
    GEOS_LIBRARY_PATH = str(_osgeo_dir / "geos_c.dll")

SECRET_KEY = "django-insecure-tp-ingestion-dev-key-change-in-production"

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.gis",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "rest_framework",
    "users",
    "tp_ingestion",
    "rules_engine",
    "envelope_engine",
    "placement_engine",
    "floor_skeleton",
    "residential_layout",
    "architecture",
    "ai_layer",
]

# Custom user model
AUTH_USER_MODEL = "users.User"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": "architecture_ai",
        "USER": "postgres",
        "PASSWORD": "Dp#76001",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# CORS: allow frontend (Next.js dev server) to call API
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
CORS_ALLOW_CREDENTIALS = True

# DRF: session auth; default AllowAny so new endpoints don't break — protect explicitly
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

# Session cookie and lifecycle
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400  # 24 hours
# Idle timeout: extend session on every request
SESSION_SAVE_EVERY_REQUEST = True
# Cross-origin: frontend app.example.com + backend api.example.com need SameSite=None; Secure
_SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "").lower() in ("1", "true", "yes")
SESSION_COOKIE_SAMESITE = "None" if _SECURE_COOKIES else "Lax"
SESSION_COOKIE_SECURE = _SECURE_COOKIES
# DB session cleanup: run daily to avoid unbounded growth, e.g. cron: 0 3 * * * python manage.py clearsessions

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

# URL configuration
ROOT_URLCONF = "backend.urls"

# Templates configuration for Django admin
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Static files (for admin)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── Email Configuration (Gmail SMTP via App Password) ──
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or "noreply@aiarchitect.com"

# ── Cache Configuration (for OTP storage; sessions use Redis when REDIS_URL set) ──
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "otp-cache",
    }
}
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if REDIS_URL:
    # django-redis: TTL aligns with SESSION_COOKIE_AGE so stale sessions are evicted
    CACHES["sessions"] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "TIMEOUT": 86400,  # 24 hours, match SESSION_COOKIE_AGE
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "sessions"

# CSRF
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
