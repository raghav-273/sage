# SAGE — Environment Variable Reference

All variables are read from `.env` (gitignored; copy from `.env.example`).
Variables not set fall back to the default shown — where "required" is
listed, the application will start without it, but the dependent feature
fails clearly when actually used (not at startup).

## Django core

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | — (required) | Cryptographic signing key. Never reuse the development placeholder for a real demo. |
| `DEBUG` | `False` (schema default; dev `.env.example` ships `True`) | Controls secure cookies, branded error pages, and Django's debug toolbar-style error output. See `docs/DEPLOYMENT.md`. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated. Must include your real hostname/IP for any non-local access. |
| `DJANGO_LOG_LEVEL` | `INFO` (schema default; dev `.env.example` ships `DEBUG`) | Applies to the `django` logger only — `apps.*` and `services.*` are always `DEBUG`. |
| `DJANGO_RUN_SERVER_MODE` | `runserver` | Set to `gunicorn` for a demo/production-style run. See `docs/DEPLOYMENT.md`. |

## Database

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_DB` | — (required) | |
| `POSTGRES_USER` | — (required) | Also the PostgreSQL superuser in the `pgvector/pgvector:pg16` image |
| `POSTGRES_PASSWORD` | — (required) | |
| `POSTGRES_HOST` | — (required) | Must be `db` (the compose service name) when Django runs inside the container |
| `POSTGRES_PORT` | `5432` | |
| `DATABASE_URL` | — (required) | `postgres://USER:PASSWORD@HOST:PORT/NAME` — composed from the values above |

## Celery / Redis

| Variable | Default | Notes |
|---|---|---|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | |

## Answer generation (Gemini)

| Variable | Default | Notes |
|---|---|---|
| `GENERATION_PROVIDER` | — (required for generation) | Currently only `gemini` is supported. Unset or unrecognized values raise a clear `GenerationError` when a question is asked — the app itself still starts. |
| `GEMINI_API_KEY` | — (required when `GENERATION_PROVIDER=gemini`) | Free tier, no credit card required as of this writing — verify current terms at Google AI Studio, since free-tier policy has changed more than once during this project's build. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Confirmed on the free tier; do not switch to a newer model without independently re-confirming free-tier eligibility (see the Milestone-7 generation-provider discussion in project history — `gemini-3.5-flash` was checked and found to be paid-only as of its release). |

## Adaptive login verification (Milestone 9)

| Variable | Default | Notes |
|---|---|---|
| `LOGIN_CHALLENGE_FAILURE_THRESHOLD` | `5` | Failed attempts (per IP, within the window) before a verification challenge is required. |
| `LOGIN_CHALLENGE_WINDOW_SECONDS` | `900` (15 min) | Sliding window for counting failures. |
| `LOGIN_CHALLENGE_TOKEN_MAX_AGE` | `300` (5 min) | How long a generated challenge stays valid before expiring. |

## Portal query rate limiting (Milestone 11)

| Variable | Default | Notes |
|---|---|---|
| `PORTAL_QUERY_RATE_LIMIT_WINDOW_SECONDS` | `60` | |
| `PORTAL_QUERY_RATE_LIMIT_MAX_REQUESTS` | `8` | Deliberately at/below Gemini's free-tier per-minute ceiling — see the rate-limiting design note from Milestone 11. |

## Not user-configurable

`TIKTOKEN_CACHE_DIR` and `HF_HOME` are set inside the `Dockerfile`
itself, not `.env` — they control where build-time model/tokenizer
caches live inside the image and aren't meant to vary per deployment.