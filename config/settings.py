"""
config/settings.py

SAGE Django settings.
All configuration is driven by environment variables.
Copy .env.example → .env and populate before starting the stack.

Environment variable reference: .env.example
Django settings reference: https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from pathlib import Path
import environ


# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent


# ── Environment ───────────────────────────────────────────────────────────────
# django-environ reads typed values from os.environ.
# In Docker, variables arrive via docker-compose env_file.
# The .env file is also present via the bind mount (.:/app), so read_env()
# works both inside and outside the container.
# overwrite=False: docker-compose-injected values always take precedence.

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_LOG_LEVEL=(str, "INFO"),
)

environ.Env.read_env(BASE_DIR / ".env", overwrite=False)


# ── Security ──────────────────────────────────────────────────────────────────

SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")


# ── Application definition ────────────────────────────────────────────────────

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
]

LOCAL_APPS = [
    "apps.documents",
    "apps.chunks",
    "apps.ingestion",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ── URL and WSGI ──────────────────────────────────────────────────────────────

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ── Templates ─────────────────────────────────────────────────────────────────
# Required by Django admin and the DRF browsable API.

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


# ── Database ──────────────────────────────────────────────────────────────────
# Parsed from DATABASE_URL.
#
# Required format:  postgres://USER:PASSWORD@HOST:PORT/NAME
# Development:      postgres://sage:sage_dev_password@db:5432/sage
#
# django-environ maps postgres:// → django.db.backends.postgresql (psycopg2).
# pgvector requires no custom engine. VectorField integrates with the standard
# postgresql backend via the pgvector Python package.
#
# Exact vector search is used for MVP (no IVFFlat index).
# IVFFlat indexing is deferred to Phase 2 after retrieval accuracy is validated.

DATABASES = {
    "default": env.db("DATABASE_URL")
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ── Password validation ───────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ── Django REST Framework ─────────────────────────────────────────────────────
# The DRF browsable API is the primary interface for the MVP.
# AllowAny is intentional for development velocity.
# Tighten DEFAULT_PERMISSION_CLASSES before any external deployment.

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # SessionAuthentication: powers the DRF browsable API login/logout.
        "rest_framework.authentication.SessionAuthentication",
        # TokenAuthentication: powers programmatic API access.
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        # Open for development. Replace with IsAuthenticated for production.
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        # BrowsableAPIRenderer: enables the HTML browsable API.
        # Remove in production if not needed.
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        # MultiPartParser and FormParser: required for PDF file uploads.
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}


# ── Celery ────────────────────────────────────────────────────────────────────
# All CELERY_ prefixed settings are loaded by config/celery.py via:
#   app.config_from_object('django.conf:settings', namespace='CELERY')

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/0")

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# Celery timezone must match Django's TIME_ZONE.
CELERY_TIMEZONE = "Asia/Kolkata"

# Track when a task moves from PENDING → STARTED.
# Required for accurate progress monitoring in Flower and the status API.
CELERY_TASK_TRACK_STARTED = True

# Hard limit: the OS sends SIGKILL after this many seconds.
# PDF ingestion for a 300-page document must complete within 10 minutes.
CELERY_TASK_TIME_LIMIT = 600

# Soft limit: raises SoftTimeLimitExceeded, allowing the task to clean up.
# Set 60 seconds below the hard limit to allow graceful shutdown.
CELERY_TASK_SOFT_TIME_LIMIT = 540

# Disable prefetch: each worker processes one task at a time.
# Required for long-running PDF ingestion tasks that hold DB connections.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Suppress Celery 5.3+ deprecation warning about broker connection retry behaviour.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# ── Static files ──────────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# ── Media files ───────────────────────────────────────────────────────────────
# Uploaded PDFs   → MEDIA_ROOT/documents/<uuid>.pdf
# Extracted images → MEDIA_ROOT/images/page_<N>_img_<xref>.png
#
# Served by Django runserver in development (config/urls.py).
# In production: serve via nginx or a CDN. Never via Django.

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Subdirectory names referenced in upload validators and the extraction pipeline.
DOCUMENTS_UPLOAD_DIR = "documents"
IMAGES_UPLOAD_DIR = "images"


# ── File upload limits ────────────────────────────────────────────────────────
# Architecture target: PDFs up to 500 pages. 100 MB covers the realistic range.

MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024   # 100 MB

# Django's in-memory upload threshold and maximum in-memory size.
# Files larger than FILE_UPLOAD_MAX_MEMORY_SIZE are written to a temp file.
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES


# ── Internationalisation ──────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# ── pgvector ──────────────────────────────────────────────────────────────────
# The vector extension is activated in PostgreSQL by:
#   infrastructure/postgres/init.sql → CREATE EXTENSION IF NOT EXISTS vector;
#
# This constant is the single source of truth for embedding dimensionality.
# Changing it requires a migration that drops and recreates the embedding column.
#
# text-embedding-3-small (OpenAI): 1536 dimensions
# text-embedding-004 (Gemini):      768 dimensions
#
# Embedding generation is implemented in Week 2. This constant is defined now
# so the ContentChunk migration can reference it without hardcoding.

PGVECTOR_EMBEDDING_DIMENSIONS = 1536


# ── Logging ───────────────────────────────────────────────────────────────────
# Structured console logging for development.
#
# Logger hierarchy:
#   root              → WARNING (suppresses third-party noise)
#   django            → controlled by DJANGO_LOG_LEVEL env var (default INFO)
#   django.db.backends → WARNING (set to DEBUG to log every SQL query)
#   apps.*            → DEBUG  (full visibility into application code)
#   services.*        → DEBUG  (full visibility into service layer)
#   celery            → INFO   (task lifecycle events)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} pid={process:d}: {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "[{asctime}] {levelname} {module}: {message}",
            "style": "{",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL"),
            "propagate": False,
        },
        "django.db.backends": {
            # Set to DEBUG to log every SQL query. Useful when debugging
            # slow queries in the retrieval pipeline.
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            # Covers apps.documents, apps.chunks, apps.ingestion, etc.
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "services": {
            # Covers services.extractors, services.chunkers, services.llm_client.
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}