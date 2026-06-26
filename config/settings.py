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

# After: (before it was just = not DEBUG, which is True in production)
# Independently overridable — DEBUG=False no longer forces this. Needed
# because this project has no TLS termination; setting these True
# without HTTPS breaks login into an infinite redirect loop (the cookie
# is set but the browser refuses to resend it over plain HTTP).
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)


SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Required for CSRF validation to succeed over HTTPS on a non-standard
# port — Django checks the request's Origin against this list for
# "secure" requests. Without it, every POST (login, upload, query) over
# https://localhost:8443 would fail CSRF validation.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:8000", "https://localhost:8443"]
)

# Cloudflare Turnstile — defaults are Cloudflare's official "always pass"
# TEST keys, safe for local dev with zero signup. These provide NO real
# bot protection — replace with real keys from a free Cloudflare account
# (dash.cloudflare.com -> Turnstile) before any real demo or deployment.
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY", default="1x00000000000000000000AA")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY", default="1x0000000000000000000000000000000AA")

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
    "apps.api",   # NEW
    "apps.portal",   # NEW
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Cache ─────────────────────────────────────────────────────────────────────

# Shared cache, backed by the Redis instance already running for Celery —
# required for correctness once DJANGO_RUN_SERVER_MODE=gunicorn runs
# multiple worker processes. Django's default LocMemCache is per-process
# and would silently fragment login-failure counts and the portal query
# rate limiter across workers. A separate Redis DB index (1, not Celery's
# 0) keeps the two workloads' keys cleanly separated.

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("DJANGO_CACHE_URL", default="redis://redis:6379/1"),
    }
}
# ── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
        "rest_framework.permissions.IsAuthenticated",
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
    
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],

    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "60/minute",
        "query": "8/minute",
    },
}

# Auth redirects
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Adaptive login verification — apps.portal.login_security
# No CAPTCHA on normal logins. After this many failures from the same IP
# within the window, a plain-text challenge is additionally required.
LOGIN_CHALLENGE_FAILURE_THRESHOLD = env.int("LOGIN_CHALLENGE_FAILURE_THRESHOLD", default=5)
LOGIN_CHALLENGE_WINDOW_SECONDS = env.int("LOGIN_CHALLENGE_WINDOW_SECONDS", default=900)   # 15 minutes
LOGIN_CHALLENGE_TOKEN_MAX_AGE = env.int("LOGIN_CHALLENGE_TOKEN_MAX_AGE", default=300)     # 5 minutes
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


# NEW  ──────────────────────────────────────────────────────────────
# CompressedManifestStaticFilesStorage requires collectstatic to have run
# before the server starts handling requests — {% static %} resolves
# filenames via the manifest it produces. This is why collectstatic is
# now chained into the web service's startup command (docker-compose.yml),
# not left as a separate manual step.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


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

# ── Rate Limiting ──────────────────────────────────────────────────────
# Rate limiting for the portal query endpoint. This is a second layer of protection

PORTAL_QUERY_RATE_LIMIT_WINDOW_SECONDS = env.int("PORTAL_QUERY_RATE_LIMIT_WINDOW_SECONDS", default=60)
PORTAL_QUERY_RATE_LIMIT_MAX_REQUESTS = env.int("PORTAL_QUERY_RATE_LIMIT_MAX_REQUESTS", default=8)

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
# using BAAI/bge-small-en-v1.5 (sentence-transformers): 384 dimensions
# Embedding generation is implemented in Week 2. This constant is defined now
# so the ContentChunk migration can reference it without hardcoding.

PGVECTOR_EMBEDDING_DIMENSIONS = 384  # BAAI/bge-small-en-v1.5 (sentence-transformers): 384 dimensions


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