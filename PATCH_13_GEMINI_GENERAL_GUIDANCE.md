# Patch 13 — Explicit, ungrounded Gemini general guidance

## Purpose

This patch connects working Gemini **text generation** to the Pakistani
conversation UI without requiring paid Google Search grounding. The app still
searches eligible *published* phone variants and *verified* PKR observations
first. If no priced local match exists, users can opt in to general buying
advice from Gemini. The Gemini text appears in a separate, explicitly labeled
**unverified** section; it never becomes a product recommendation, price quote,
PTA check, source citation, or database catalog record.

## Prerequisites

Patches 01–12 plus the **12A exact-device lookup correction** must already be
applied; commit or otherwise protect earlier changes before applying Patch 13.
No migration is introduced. Keep `.env.local` private and rotate any exposed
credentials. `AI_PROVIDER=gemini` and a valid server-side `GEMINI_API_KEY` are
required for the optional general-advice endpoint.

Example additions to **backend/.env.local** (Windows Python):

```dotenv
AI_PROVIDER=gemini
GEMINI_CHAT_MODEL=gemini-3.8-flash
GEMINI_WEB_RESEARCH_ENABLED=0
RESEARCH_JOB_QUEUE_ENABLED=0
GEMINI_GUIDANCE_RATE_LIMIT=6/hour
GEMINI_GUIDANCE_TIMEOUT_SECONDS=35
```

Do not paste keys in chats or commit environment files. Keep existing
Windows-specific Postgres settings (`127.0.0.1:15432`).

## User workflow

1. Restart Django and the Vite frontend.
2. On `/assistant`, check **Use Gemini general guidance** (off by default).
   This explicitly permits sending a redacted, bounded form of the current
   question and public criteria to the Google Gemini API.
3. Leave **Request Gemini web research** unchecked if your Google AI Studio
   project does not have Google Search grounding quota.
4. Ask about a phone model missing from your local verified Pakistani catalog.
   The backend returns the ordinary `needs_research` flag and may also include
   a separate `guidance` response with `status: "generated"`.

Unverified text has no live citation or confirmed specifications. Exact model
information still requires independently checked manufacturer sources. Market
prices, PTA approval/IMEI status, offers, and availability remain database
and human-review concerns. When Gemini is unavailable or exhausted, the local
response continues with a generic notice rather than an invented answer.

## API

`POST /api/recommendations/converse/` (JSON), for example:

```json
{
  "message": "What should I check before buying an iPhone 18 Pro Max?",
  "guidance": true,
  "research": false
}
```

The response retains all existing fields and adds:

```json
{
  "guidance_requested": true,
  "guidance": {
    "status": "generated",
    "text": "...",
    "notice": "AI general guidance only — not web-verified. No local price, availability or PTA status is confirmed."
  }
}
```

Other guidance statuses: `not_requested`, `not_needed` (eligible local results
or a grounded research preview already available), `disabled`, `rate_limited`,
`unavailable`. `response_source` remains `deterministic` because it describes
the trusted local shortlist, not the separately labeled advisory text.

The Gemini request: one HTTPS call with low thinking and 2,048 maximum output
tokens; bounded 35-second timeout (at most 45); no Google Search tool, no
redirect following, no automatic retries. The API key stays server-side. The
prompt omits sessions, prior messages, user IDs, URLs, emails, and obvious
phone numbers. The generated text is neither persisted to analytics nor
imported into the catalog. Incomplete answers, generated links, and numeric
money quotations are rejected. These controls **reduce** risk; they do not
make LLM-generated facts authoritative.

## Verification (Windows PowerShell)

From repository root, after applying the Git patch:

```powershell
cd backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test config catalog recommendations
cd ..\frontend
npm run lint
npm run test:ui
npm run build
```

The existing 149-test baseline plus **10 new Django tests** means **159** tests
should be discovered, if all previous patches and their regression tests are
present. If any verification step fails, do not commit.

## Deliberate limitations

* Gemini has no live external sources in this pathway, and cannot confirm
  current device launch dates, specs, local prices or PTA approvals.
* Opt-in ordinary text generation may still consume limited API quota.
* Paid grounded web research remains separately controlled by Patch 08.
* This does not seed your catalog. Add real phones and reviewed evidence through
  the existing Django admin ingestion workflows.
