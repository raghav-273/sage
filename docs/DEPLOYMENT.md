# SAGE — Deployment Guide

## Deployment model

Single Docker Compose stack, single host, no orchestration layer. This
is a deliberate architectural choice for a single-developer, single-
operator system — not a placeholder for "real" infrastructure to be
added later. Scaling beyond one host is explicitly out of scope; see
"Known single-instance limitations" below for what that costs.

```bash
docker compose up --build
```

is the entire deployment command, in both development and demo contexts.
What changes between them is `.env`, not the command.

## Demo / production-style configuration

Before demonstrating to reviewers, set in `.env`:

```bash
DEBUG=False
DJANGO_RUN_SERVER_MODE=gunicorn
DJANGO_SECRET_KEY=<a real, freshly generated random value — never the dev placeholder>
ALLOWED_HOSTS=<your actual hostname or IP>
```

`DEBUG=False` enforces `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` (see
Milestone 9) and switches Django's own error pages to the branded
`errors/404.html`/`500.html` templates instead of the debug traceback
page. `DJANGO_RUN_SERVER_MODE=gunicorn` switches the web service from
Django's development server to gunicorn (3 worker processes) — see the
note on `runserver` below for why this matters.

## Why gunicorn is opt-in, not the default

Django's `runserver` is explicitly documented as unsuitable for anything
beyond local development — no real process management, limited
concurrency. For a live multi-person demo, that's a genuine (if modest)
reliability risk worth closing, which is why gunicorn is included at all.
It's gated behind `DJANGO_RUN_SERVER_MODE` rather than replacing
`runserver` outright because `runserver`'s auto-reload-on-file-change is
what makes the bind-mounted dev workflow (`volumes: - .:/app`) useful —
gunicorn doesn't reload by default, and forcing that loss onto every
future development session for a benefit that only matters during an
actual demo would be the wrong trade.

## Static files

`whitenoise` serves CSS/JS directly from the Django process, regardless
of `DEBUG`. This exists to close a real gap: Django's `runserver` only
auto-serves static files when `DEBUG=True` — without whitenoise, setting
`DEBUG=False` for the demo would silently break every page's styling.
`collectstatic` runs automatically at container startup (chained into
the `web` service's command), so this requires no manual step.

**When vendoring any new minified asset:** always fetch its matching
`.map` file too. A missing referenced source map is a fatal
`collectstatic` error under WhiteNoise, not a warning — see the
Milestone 12 bug report for the exact failure mode this caused.

## Included vs. explicitly deferred

This system implements meaningful security and reliability practices
within its scope, but the following were named from the outset as
"document, don't implement" — listed here so a reviewer or future
maintainer sees the boundary stated plainly, not discovered by surprise:

| Capability | Status | Why deferred |
|---|---|---|
| TLS / HTTPS | Not implemented | Requires a certificate and either a reverse proxy or app-level TLS termination — out of scope for a single-operator internship deployment; cookies are still configured correctly for when TLS is added (`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` already conditional on `DEBUG`) |
| Reverse proxy (nginx/Caddy) | Not implemented | Explicitly excluded from the architecture from Milestone 1 onward; whitenoise covers the one job a proxy would otherwise do (serving static files) without adding a second service |
| Encryption at rest | Not implemented | PostgreSQL data and `media/` files are stored unencrypted on the host's filesystem. Acceptable for a non-sensitive demo dataset; would need host-level disk encryption or PostgreSQL TDE for real deployment |
| Audit logging | Not implemented | Considered explicitly during the document-details design (Milestone 11) and deliberately scoped down to current-status-only, to avoid a parallel migration and a half-built audit trail. Application-level structured logging (every service module) exists and covers debugging; it is not a tamper-evident audit log |
| Monitoring / alerting | Not implemented | The dashboard's system health section (Postgres/Redis/Celery liveness) is a manual-refresh check, not monitoring. Celery Flower exists as a commented-out stub in `docker-compose.yml` — uncomment if task-level visibility is ever needed; still not alerting |

## Known single-instance limitations

Two features rely on Django's local-memory cache for correctness, not
just performance: the adaptive login challenge (Milestone 9) and the
portal query rate limiter (Milestone 11). Both assume exactly one `web`
process sees all requests. If this is ever scaled to multiple replicas,
each replica would track failures/rate-limit counts independently —
silently weakening both protections without any visible error. This was
flagged as an accepted limitation when each feature was built, not
discovered now; restated here as the permanent, central place this
constraint is documented.

## Known external dependency: Gemini API capacity issues

Gemini's Flash-tier models, including the free tier, intermittently
return `503 UNAVAILABLE` ("high demand") errors. This is a real,
widely-reported, ongoing issue on Google's side — confirmed via Google's
own developer forum and the `google-genai` SDK's GitHub issue tracker —
not specific to this deployment, this API key, or this codebase. It
affects free and paid tiers equally.

Two mitigations are built into `GeminiGenerationClient`:

1. After the existing 5-attempt exponential-backoff retry is exhausted
   against the primary model, one additional retry cycle runs against a
   separate fallback model (`GEMINI_FALLBACK_MODEL`) — a different model
   has an independent capacity pool.
2. An outer, SDK-independent timeout (`GEMINI_REQUEST_TIMEOUT_SECONDS`)
   guards against a separately-documented SDK issue where a request can
   stall indefinitely at the socket level under load, with no exception
   raised at all. Without this, that specific failure mode would hang a
   query page's loading spinner forever rather than showing the clean
   error message the rest of this system is designed to surface.

Neither mitigation eliminates the underlying issue — it's outside this
project's control. They bound its impact: any failure now surfaces as a
clean, finite-time error rather than an indefinite hang or a total loss
of service.


## Secrets

`GEMINI_API_KEY` and `DJANGO_SECRET_KEY` are the only values in this
system that qualify as real secrets. Both are read from `.env`, which is
gitignored. There is no secrets manager integration — for a
single-operator deployment with no cloud infrastructure, that would be
complexity without a corresponding benefit.

## Logs

```bash
docker compose logs -f web
docker compose logs -f celery_worker
```

`DJANGO_LOG_LEVEL` controls verbosity (see
`docs/ENVIRONMENT_VARIABLES.md`).

---

**Critical dependency: secure cookies require real TLS.** Setting
`DEBUG=False` defaults `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` to
`True` — which, served over plain HTTP (this project implements no TLS
termination), breaks login into an infinite redirect loop: the cookie is
set but the browser refuses to ever send it back. If demonstrating over
HTTP without TLS, explicitly override:

```bash
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
```

This is a real, intentional security tradeoff — only acceptable for a
local or trusted-network demo, never for anything reachable over the
open internet without HTTPS.