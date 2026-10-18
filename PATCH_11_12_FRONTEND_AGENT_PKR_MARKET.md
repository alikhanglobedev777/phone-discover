# Phone Discover — Combined Patch 11 + 12

This is a frontend-only Git patch based on **Patch 09+10 plus the 09+10A/09+10B corrections**. No Django model changes, new Python dependencies, secrets, background jobs, or database migrations are included.

## Patch 11 — Conversation and research interface

- Changes the assistant from the old `/api/recommendations/` USD/global endpoint to `POST /api/recommendations/converse/` (English and Roman Urdu, PKR prices only).
- Sends structured filters **only when the user changes them**. Omitted fields let the server retain budget, PTA status, condition, city, priorities and specifications on a brand-only follow-up such as “Samsung mein batao.”
- Displays actual `market_price` observations for the **same matched variant**, not an unrelated merchant offer or probability-style percentage.
- Lets users explicitly opt into Gemini grounding when local evidence is insufficient. A research preview is labeled unverified and linked to vetted HTTPS sources; the frontend never queues a staff research job or publishes price evidence.
- Uses an in-memory random session UUID, aborts an in-flight request when a new chat starts, and sends `DELETE /api/recommendations/conversation/<session-id>/` to clear the previous server-side context. **Do not store or share session UUIDs.** If deletion fails, an error warns that the old server context may remain until expiry.
- Shows rate-limit/unavailable errors and offers a retry instead of inventing phones or prices. Supports opening details and adding shortlisted devices to the existing comparison UI.

## Patch 12 — Pakistani market browser

- Adds a separate, responsive `#market` section powered by `GET /api/catalog/search/`, with city, PKR budget, condition, PTA status/verification, RAM, query and sort filters.
- Paginates exact-variant, reviewed price observations. Results show observed PKR ranges, source date, PTA claim vs independent checking, and unconfirmed availability.
- Keeps the old specification/global-offer catalog as a **clearly labeled reference catalog**; those offer currencies are not compared with Pakistani prices.
- Adds safe external-link rendering, accessible labels/status/error messages, and pure frontend tests.

## Installation (PowerShell)

1. Verify and commit Patch 09+10 with corrections A/B first. The working tree should be clean; backend tests should pass (previous expected count: 145).
2. Download `phone-discover-patch-11-12-frontend-pkr-agent.patch` into Downloads.
3. From the repository root:

```powershell
$ErrorActionPreference = 'Stop'
cd 'C:\Users\ak821\Desktop\phone-discover'
$patch = "$HOME\Downloads\phone-discover-patch-11-12-frontend-pkr-agent.patch"
if (!(Test-Path -LiteralPath $patch)) { throw 'Patch missing from Downloads.' }
if (git status --porcelain) { throw 'Working tree is not clean. Commit verified Patch 09+10 first.' }
git apply --check -- "$patch"
if ($LASTEXITCODE -ne 0) { throw 'Patch compatibility check failed.' }
git apply -- "$patch"
if ($LASTEXITCODE -ne 0) { throw 'Patch application failed.' }
git -c core.whitespace=cr-at-eol diff --check
if ($LASTEXITCODE -ne 0) { throw 'Git whitespace check failed.' }
```

4. Verify frontend from the `frontend` folder. Use Node.js **22 or newer** for the no-dependency `node --experimental-strip-types` UI helper tests. Install the project's locked frontend dependencies normally (from a vetted environment):

```powershell
cd 'C:\Users\ak821\Desktop\phone-discover\frontend'
npm ci
if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
npm run lint
if ($LASTEXITCODE -ne 0) { throw 'Frontend TypeScript check failed.' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
npm run test:ui
if ($LASTEXITCODE -ne 0) { throw 'Frontend helper tests failed.' }
```

5. When these checks pass, commit the frontend changes:

```powershell
cd 'C:\Users\ak821\Desktop\phone-discover'
git add -- PATCH_11_12_FRONTEND_AGENT_PKR_MARKET.md frontend/package.json frontend/src/App.tsx frontend/src/styles.css frontend/src/components/RecommendationAssistant.tsx frontend/src/components/PakistanMarket.tsx frontend/src/lib/pakistan.ts frontend/tests/pakistan.test.mjs
git -c core.whitespace=cr-at-eol diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged changes need review.' }
git diff --cached --stat
git commit -m 'feat: patches 11-12 PKR agent frontend and market browser'
git status --short
```

## Smoke check

- Start database/Redis: `docker compose up -d --wait db redis` from the repo root.
- Start Django in a separate terminal using `backend\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000` from `backend`.
- Start Vite using `npm run dev` from `frontend`. Visit `http://127.0.0.1:5173/`.
- Search Pakistani phones. A clean new database may show **zero evidence-backed results**; that is expected, not a frontend failure. Add real reviewed source-permitted price observations via Django admin before expecting recommendations.
- Ask `80 hazar tak Lahore mein used PTA approved gaming phone` and follow up `Samsung mein batao`; check that the conversation retains earlier preferences.
- Leave research unticked to verify DB-only behavior. Research requires both the checkbox and server-side Gemini configuration; no key belongs in frontend code.
- Test `New chat + forget`; verify the next request starts a different context.

## Verification limits

The patch was Git-applied to a fresh reconstructed Patch 09+10B baseline; the TypeScript sources were syntax-transpiled and the built-in Node helper tests passed. A complete Vite build and live browser test require the frontend npm dependencies and a running Django backend on your machine. No new backend test count is claimed, and the patch does not assert that Gemini research is configured or that Pakistani phone price records have been populated.
