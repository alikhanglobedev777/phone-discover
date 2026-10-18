# Patch 14 — Release hardening and verification

This patch builds on **Patch 13 and the 12A correction**. It does not enable
paid Gemini web grounding, create catalog records, add migrations, replace your
API key, expose passwords, or turn the development Docker Compose setup into a
production deployment. Its scope is **security defaults and verifiable
readiness**, not a claim that the site is ready for public traffic.

## What changed

- Production admin accounts use Django's standard password validators. The
  Windows native development behavior stays unchanged while `DJANGO_DEBUG=1`.
- Explicit, opt-in HTTPS redirect, short HSTS and trusted-proxy configuration.
  These settings must be reviewed with your real HTTPS reverse proxy before
  enabling; do not enable redirect on plain HTTP localhost.
- `X-Frame-Options: DENY`, strict origin/referrer policy and HTTP-only session
  cookies.
- Optional shared Redis cache, used by DRF's IP-scoped throttles across web
  workers; local development uses the existing in-process cache. Throttling
  mitigates accidental/automated use but is **not** complete anti-abuse or
  billing protection.
- Read-only `manage.py release_check` with redacted error messages, optional
  live DB/migration check, cache check and catalog evidence check.
- `scripts/verify-release.ps1` runs backend checks/tests, readiness preflight,
  frontend tests/type checking/build and Git whitespace verification.
- Ten focused Django tests covering these safeguards with external services
  mocked. Existing catalog eligibility rules remain unchanged.

## 1. Windows developer verification (do this first)

From the repository root **after Patch 13 is committed** and Patch 14 applied:

```powershell
cd "C:\Users\ak821\Desktop\phone-discover"
.\scripts\verify-release.ps1
```

This expects the PostgreSQL service and migrations to be running, Python
virtualenv to be installed at `backend/.venv`, and `frontend/node_modules`
installed. It does **not** call Gemini or Redis unless Redis production checks
are explicitly requested. It does not require any catalog data to exist.

Or run the lightweight command manually from the `backend` directory:

```powershell
.\.venv\Scripts\python.exe manage.py release_check
.\.venv\Scripts\python.exe manage.py release_check --database
.\.venv\Scripts\python.exe manage.py release_check --database --require-market-data
```

The third command intentionally **fails** if there are no publishable, fresh,
reviewed price observations linked to published devices. That's a catalog
content issue, not a Gemini or Django connectivity issue.

## 2. Production settings (only behind an audited HTTPS proxy)

**Do not copy these production values into your localhost `.env.local` now.**
Your normal Windows runserver setup should keep `DJANGO_DEBUG=1`, with no
HTTPS redirect or HSTS. For a future *real deployment*, use private environment
variables managed by the hosting platform (example hostnames only):

```dotenv
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=phones.example.com
CORS_ALLOWED_ORIGINS=https://phones.example.com
CSRF_TRUSTED_ORIGINS=https://phones.example.com
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_HSTS_SECONDS=300
DJANGO_USE_REDIS_CACHE=1
REDIS_URL=redis://127.0.0.1:6379/0
DJANGO_TRUST_PROXY_HEADERS=1
GEMINI_WEB_RESEARCH_ENABLED=0
RESEARCH_JOB_QUEUE_ENABLED=0
```

Keep a freshly generated strong `DJANGO_SECRET_KEY` and genuine DB credentials
only in private configuration. In an actual multi-host deployment, Redis must
be reachable from all Django workers and secured with access controls/TLS as
appropriate; the shown Redis URL is just a localhost example. Set
`DJANGO_TRUST_PROXY_HEADERS=1` **only** when a trusted HTTPS proxy strips
client `X-Forwarded-Proto` headers and sets its own. Otherwise leave it off;
with offload-to-HTTP proxies, redirect may loop unless protocol detection is
correct. Incorrect proxy trust can weaken HTTPS assurances; HSTS should be increased cautiously after TLS is verified.

Run this in a correctly configured production environment:

```powershell
.\.venv\Scripts\python.exe manage.py release_check --production --database --cache --require-market-data
.\.venv\Scripts\python.exe manage.py check --deploy
```

`--production` alone will fail unless `--cache` is also specified. This checks
configuration and selected services; it does **not** prove all public-release
security, privacy, or data-source requirements are met. `check --deploy` can
raise additional Django warnings that must be reviewed separately.

## 3. Catalog and privacy expectations

For the local market to display prices, administrators must independently
review source reuse rights, listing freshness, device/variant identity,
condition/grade, and PTA evidence, then publish records. Pending AI research
and unreviewed citations are **not** prices. A catalog with zero eligible PKR
observations is permitted for development but not a credible populated market
launch. Do not represent self-reported PTA status as IMEI verification.

Run existing retention cleanup commands periodically in your **own scheduler**
for your deployment's privacy policy; Patch 14 does not silently schedule them:

```powershell
.\.venv\Scripts\python.exe manage.py purge_conversation_contexts
.\.venv\Scripts\python.exe manage.py purge_recommendation_queries
.\.venv\Scripts\python.exe manage.py purge_research_jobs
```

The deletion commands are **examples to run intentionally under your own retention policy**.
No deletion occurs as part of `release_check` or `verify-release.ps1`.

## 4. Before a public launch

1. Use a real HTTPS server/reverse proxy and a production WSGI/ASGI process;
   **never** `manage.py runserver` or the existing developer Docker Compose
   service as a public production server.
2. Rotate any credentials previously shared or committed and review Git
   history and deployment logs for accidental disclosures.
3. Take a tested PostgreSQL backup and document rollback/recovery procedures.
4. Review access controls, admin permissions, auditability, backups, live rate
   limits, on-call alerts, legal/source reuse checks, and your privacy policy.
5. Test with real published eligible price evidence and realistic absent-data
   cases. Check frontend errors and system load before exposing it publicly.

## Changes intentionally not included

No database migration, actual infrastructure deployment, certificate
management, live billing enablement, Celery worker scheduling or automated
catalog ingestion. They require separate operational choices. The app remains
**local/development verified** until real production deployment testing passes.
