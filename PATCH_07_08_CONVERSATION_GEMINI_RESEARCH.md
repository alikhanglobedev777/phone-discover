# Combined Patch 07 + 08: conversation preferences and Gemini grounded research

This patch builds on **Patch 06 + Patch 06A** (rate-limit test correction) and the Patch 05 one-line price-fixture fix. It does **not** replace the production `/api/recommendations/` or `/api/recommendations/local/` endpoints.

## New API

`POST /api/recommendations/converse/`

First turn:

```json
{"message":"Mujhe Lahore mein 80 hazar tak used PTA gaming phone batao", "max_results": 1}
```

The response includes a randomly generated `session_id`, evidence-backed local results, `needs_research`, and the `research` object. For follow-ups, send that exact `session_id`:

```json
{"session_id":"<UUID FROM FIRST RESPONSE>", "message":"Samsung mein batao"}
```

The next request retains earlier local search preferences (budget, city, condition, PTA status, priorities, variant requirements) unless the user supplies a new value. Explicit API fields override natural language; `reset_context: true` or "start over" clears the previous preference context before searching. `use_memory: false` skips loading and writing conversation preferences for a single call. Phone cards are still produced **only** from Patch 05's eligible published catalog data.

A session UUID acts as a **bearer handle**, so keep it private and use HTTPS outside local development. No authentication is added in this patch. There is no cross-session fallback, and the server stores only structured preferences in `ConversationContext`, not a complete chat transcript. The older `RecommendationQuery` analytics table still logs submitted messages and their recommendation results (90-day policy by default); use the delete endpoint to remove both for a session.

`DELETE /api/recommendations/conversation/<session-uuid>/` removes stored preferences **and** analytics for that session; returns HTTP 204 even if nothing exists. Memory expires for retrieval after `CONVERSATION_RETENTION_DAYS` (default 7, capped to 1–90). Schedule `python manage.py purge_conversation_contexts` to physically remove expired context; analytics retention remains managed by existing `purge_recommendation_queries` command.

## Opt-in Gemini research

Add `"research": true` to an individual conversation request to consider web research. Gemini is invoked only when:

1. The user explicitly requested research in that request;
2. The local shortlist has `needs_research=true`;
3. `GEMINI_WEB_RESEARCH_ENABLED=1` **and** `GEMINI_API_KEY` are set in the private `backend/.env.local` environment;
4. The separate `gemini_research` IP rate limit has not been exceeded.

This uses Google's Gemini REST `generateContent` endpoint with the `google_search` tool (not an LLM pretending to browse). It sends **only structured criteria**, not conversation history or session UUIDs. It returns a short **unverified preview** and up to five HTTPS Google Search grounding URLs, or `not_configured`, `not_needed`, `rate_limited`, `unavailable`, `not_requested` statuses. No source URL is independently fetched or confirmed to contain any particular claim in this patch. The preview can be inaccurate; users/admins must inspect original sources.

**No automated ingestion or promotion**: No ResearchSource, IngestionCandidate, Device, DeviceVariant, PTA status or price observation is created or verified from Gemini output. Structured source-by-source verification and reviewable ingestion remain Patch 09+. The endpoint never turns a Gemini-reported asking price into a verified Pakistani market price.

Gemini Google Search may incur usage-based **charges**, and may be unavailable at your account tier. Research is off by default and bounded to 3 requests/hour per IP by default. The provider may execute more than one search query per call. Configure `GEMINI_RESEARCH_RATE_LIMIT` and `CONVERSATION_RATE_LIMIT` in environment if needed, and monitor provider billing. The API key never belongs in the frontend or Git.

## Setup and verification on Windows

1. Finish committing Patch 06/06A after its existing **104 tests** pass.
2. Apply the combined Patch 07+08 from the repository root (`git apply --check` then `git apply`).
3. `cd backend; .\.venv\Scripts\python.exe manage.py check`
4. `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`
5. `.\.venv\Scripts\python.exe manage.py test config catalog recommendations` — expected **124 tests** with the new 20.
6. When tests pass, `.\.venv\Scripts\python.exe manage.py migrate` (creates the single `recommendations.0003_conversation_context` table).
7. Stage only the changed files and commit. No production schema reset is required.

If the 429 failure from the earlier suite reappears, ensure Patch 06A is applied first. Backend tests use mocks for Gemini; no API key or provider network access is required to run them. The full 124-test suite must be verified on your Windows/Docker environment.

### Example opt-in test call after running Django

```powershell
$first = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/recommendations/converse/" -Method Post -ContentType "application/json" -Body '{"message":"used PTA gaming phone under 80000 in Lahore", "max_results":1}'
$first.session_id
$follow = @{session_id=$first.session_id; message="Samsung mein batao"; research=$false} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/recommendations/converse/" -Method Post -ContentType "application/json" -Body $follow
```

The research-enabled version needs explicit opt-in and a configured Gemini key; a missing key returns a clear status without affecting local recommendations.
