# Phone Discover — combined Patches 09 + 10

**Baseline:** Patch 07+08 **plus** Patch 07+08A (conversation priority memory fix). This patch contains **no frontend changes**.

## Scope

* **09 — controlled grounded research ingestion:** strict, JSON-only Gemini proposals for already-known **exact device+variant** prices. A proposed source URL must occur in Google's grounding metadata, be HTTPS and pass URL checks. Malformed data, impossible price ranges, unsupported variants, unsupported proposal types and unfounded source URLs are rejected. Staged `ResearchSource` entries default to **reuse rights unknown**. Staged `IngestionCandidate` rows are **pending**, deduplicated with SHA-256 fingerprints. No scraping, remote URL downloads, bulk Device creation or automatic catalog publication.
* **09 — editorial promotion:** admins separately review reuse permission, approve a candidate and invoke **Ingest approved price leads as PENDING observations** from Django admin. Promotion is transactional, idempotent, and rechecks rights, exact variant, approved status and fingerprint. It produces a **pending** `MarketPriceObservation`, never a verified price. Human research, price freshness and PTA review are still required in the existing `MarketPriceObservation` admin.
* **10 — background orchestration:** restricted staff API creates a bounded `ResearchJob` (Postgres). A Celery worker executes one opt-in grounded Gemini request and stages candidates. Results are limited to counts and a generic status; no API keys, untrusted provider text, raw chat transcripts or client session UUIDs are stored in jobs. Duplicate dispatch does not run the same job twice. A cleanup management command expires old metadata and marks stale jobs failed.

## Safety and limitations

* Staff-only enqueue: **POST** `/api/recommendations/research-jobs/` with `{"message":"used PTA phone under 80000 in Lahore"}`. Public conversation and catalog APIs are unchanged; no automatic paid research on public traffic.
* Staff-only **GET** `/api/recommendations/research-jobs/` or `/api/recommendations/research-jobs/<uuid>/` to check job status. Only the requester or superuser sees a job. POST retains the research throttle (default 3/hour), polling has a separate default 120/hour scope.
* Queue disabled by default and Gemini research separately disabled by default. Operators explicitly enable both.
* Only **price** proposals for existing variants are supported in this patch; novel models/specifications are intentionally **not automatically inserted**. Gemini-generated snippets are not proof of permission, current price, PT(A) approval, or source truth. Even administrator approval does not independently verify a price.
* Source URL matching is strict and fail-closed; some grounded answers will yield zero staged records because Gemini did not return machine-parseable JSON or its proposed URL was not present in grounding metadata. This is expected; **never weaken source checks merely to increase ingestion**.
* A running worker with a timed-out process can leave a job in `running`; the maintenance command marks stale unfinished jobs `failed` after two hours. Avoid retrying paid jobs automatically without operator approval.
* The existing `GEMINI_CHAT_MODEL` must support Google Search grounding through the Gemini REST endpoint; verify the configured model with your provider. Credentials must live only in private `backend/.env.local`.

## Configure locally on Windows

1. Before applying this patch, verify that the 07+08A correction is applied and all **124** backend tests pass; commit Patch 07+08 first. Never reset database volumes.
2. `git apply --check -- "$HOME\Downloads\phone-discover-patch-09-10-controlled-research-jobs.patch"` from project root, then `git apply -- "$HOME\Downloads\phone-discover-patch-09-10-controlled-research-jobs.patch"`.
3. `cd backend`; run `.\.venv\Scripts\python.exe manage.py check`, `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`, and `.\.venv\Scripts\python.exe manage.py test config catalog recommendations`; **expected 145 tests** (124+21). Verify actual `OK` before continuing.
4. Run `.\.venv\Scripts\python.exe manage.py migrate` after tests pass. This adds `recommendations.0004_research_jobs`.
5. Configure these values in private `backend/.env.local` (do **not** commit it):

   ```dotenv
   GEMINI_WEB_RESEARCH_ENABLED=1
   RESEARCH_JOB_QUEUE_ENABLED=1
   CELERY_BROKER_URL=redis://127.0.0.1:6379/1
   # Existing private GEMINI_API_KEY=... must be set
   ```

   These settings are read at Django and Celery process start. Use `docker compose up -d --wait db redis` from the repository root, keeping your established **127.0.0.1:15432** Postgres host mapping.
6. In one PowerShell terminal in `backend`, start Django `.\.venv\Scripts\python.exe manage.py runserver`; in another terminal in `backend`, start the **explicitly opted-in** Windows development worker: `.\.venv\Scripts\celery.exe -A config worker --loglevel=info --pool=solo --concurrency=1`. `--pool=solo` avoids Windows-prefork incompatibilities. This development worker is NOT a production deployment recommendation.
7. Sign into Django admin with a staff account. Staff-authenticated POST to `/api/recommendations/research-jobs/` queues paid research. Monitor the job status through GET, or Django admin > Research jobs. Inspect **Catalog > Research sources**, **Catalog > Ingestion candidates**, and review rights independently. Only then approve and run the admin ingestion action. Inspect the resulting pending PKR price observation, verify it separately, and only then approve its market evidence under existing rules.
8. Periodically run `.\.venv\Scripts\python.exe manage.py purge_research_jobs --days 30` from `backend` to limit job-metadata retention. Run your previous query/context cleanup commands separately.

## Example API call (staff-authenticated session or token)

```http
POST /api/recommendations/research-jobs/
Content-Type: application/json

{"message":"used PTA phone under 80000 in Lahore","max_results":3}
```

```json
{"id":"<uuid>","status":"queued","poll_url":"/api/recommendations/research-jobs/<uuid>/"}
```

If disabled: HTTP 503; if not staff: HTTP 403 (or 401 without credentials); if queued, HTTP 202. No production paid work is performed by the unit tests; provider and queue interactions are mocked.

## Changed files

`backend/catalog/research_ingestion.py`, `backend/catalog/admin.py`, `backend/recommendations/gemini_research.py`, `backend/recommendations/tasks.py`, `backend/recommendations/views.py`, `backend/recommendations/urls.py`, `backend/recommendations/models.py`, `backend/recommendations/admin.py`, `backend/recommendations/test_research_pipeline.py`, `backend/recommendations/migrations/0004_research_jobs.py`, `backend/recommendations/management/commands/purge_research_jobs.py`, `backend/config/celery.py`, `backend/config/__init__.py`, `backend/config/settings.py`, and this document.
