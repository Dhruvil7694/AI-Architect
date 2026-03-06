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
    "rest_framework",
    "tp_ingestion",
    "rules_engine",
    "envelope_engine",
    "placement_engine",
    "floor_skeleton",
    "residential_layout",
    "architecture",
    "ai_layer",
]

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

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# URL configuration
ROOT_URLCONF = "backend.urls"
