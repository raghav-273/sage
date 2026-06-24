# SAGE — Local Setup Guide

Get a fresh clone running end-to-end.

## Prerequisites

- Docker Desktop (Apple Silicon native; this project has only been
  validated on macOS/arm64)
- A free Gemini API key from Google AI Studio (no credit card required
  for the free tier — see `docs/ENVIRONMENT_VARIABLES.md`)

## Steps

```bash
# 1. Clone and enter the repository
git clone <your-repo-url> sage
cd sage

# 2. Environment configuration
cp .env.example .env
# Open .env and fill in:
#   DJANGO_SECRET_KEY   — any long random string for local dev
#   GEMINI_API_KEY       — from https://aistudio.google.com/

# 3. Required local directories (gitignored; must exist before the bind mount works)
mkdir -p media/documents media/images

# 4. Vendored frontend assets — only needed if these aren't already
#    committed in your checkout
mkdir -p apps/portal/static/portal/vendor/bootstrap
curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css \
  -o apps/portal/static/portal/vendor/bootstrap/bootstrap.min.css
curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css.map \
  -o apps/portal/static/portal/vendor/bootstrap/bootstrap.min.css.map
curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js \
  -o apps/portal/static/portal/vendor/bootstrap/bootstrap.bundle.min.js
curl -fsSL https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js.map \
  -o apps/portal/static/portal/vendor/bootstrap/bootstrap.bundle.min.js.map

mkdir -p apps/portal/static/portal/vendor/htmx
curl -fsSL https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js \
  -o apps/portal/static/portal/vendor/htmx/htmx.min.js
curl -fsSL https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js.map \
  -o apps/portal/static/portal/vendor/htmx/htmx.min.js.map || true

# Minified .css/.js files commonly reference a companion .map file via a
# sourceMappingURL comment. WhiteNoise's collectstatic post-processing
# treats a missing referenced file as fatal (this exact bug crashed the
# web container under DEBUG=False) — always fetch the matching .map
# alongside any new minified asset you vendor.

# 5. Build and start the full stack
docker compose up --build
```

That last command now does everything: builds the image, pre-caches the
local embedding model and tokenizer (image build step), starts
PostgreSQL/Redis/web/celery_worker, applies migrations, collects static
files, and starts the server — genuinely one command, per the project's
stated deployment goal.

```bash
# 6. Create your operator account (one-time, interactive — not automated
#    on purpose; see docs/DEPLOYMENT.md for why)
docker compose exec web python manage.py createsuperuser

# 7. Confirm everything is healthy
docker compose exec web python manage.py test tests.unit tests.integration --keepdb -v 2
```

## Using the app

- Portal (primary interface): http://localhost:8000/
- DRF browsable API (development/debugging): http://localhost:8000/api-auth/login/
- Django admin: http://localhost:8000/admin/

Log in with the superuser account from step 6, upload a PDF, watch it
move through `QUEUED → EXTRACTING → CHUNKING → EMBEDDING → READY` on its
detail page, then ask it a question.

## Common issues

| Symptom | Cause |
|---|---|
| Login page loads with no styling | Vendored assets missing — re-run step 4 |
| `collectstatic` errors at startup | A static file referenced in a template doesn't exist on disk — check step 4 completed |
| Celery worker shows unhealthy / tasks never run | `docker compose logs celery_worker` — usually a missing `GEMINI_API_KEY` surfacing at generation time, not at startup |
| Document stuck at `EMBEDDING` forever | First-ever embedding call downloads the model if the image build's pre-cache step didn't run — check `docker compose logs web` for HuggingFace Hub network errors |