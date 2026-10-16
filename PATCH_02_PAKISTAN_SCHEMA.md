# Patch 02/14 — Pakistan phone-market and AI research storage

This patch builds the **database foundation**, not yet a web-research agent or a new UI.
It applies after Patch 01 and its Windows PostgreSQL port fix. It does not modify
`docker-compose.yml`, `.env`, or `backend/.env.local`, so your working port `15432`
is preserved.

## What is added

- `ResearchSource`: URLs, publishers, source type, reviewed reuse-rights status, and timestamps.
- `DeviceClaim`: field-level proposed facts with citations, observation timestamps, and review status.
- `MarketPriceObservation`: condition-specific **PKR** price ranges linked to exact RAM/storage variants,
  city, new/used/refurbished state, PTA classification, seller-claimed vs independently checked PTA,
  battery health when known, evidence, and when that price was observed.
- `IngestionCandidate`: an isolated queue of structured phone/specification/price research awaiting
  review. Candidate JSON is **not** copied into a `Device` automatically.
- Database checks for positive prices, ordered ranges, battery health <= 100, reasonable condition
  grade/PTA combinations, and reviewed timestamps/evidence on verified data.

### Why this does not change the existing catalog endpoint yet

The existing `MarketOffer` records are not reliable Pakistan used-phone price evidence: they have
no used/new condition or PTA context and may use other currencies. This migration intentionally
**does not backfill, convert or delete legacy offers** and never mixes them into the new tables.
The existing `/api/catalog/devices/` endpoint remains backward-compatible, but its existing
cross-currency `lowest_price` limitations are not fixed until the pricing/API patches.
In particular, pending AI research is not exposed to users as verified facts.

This patch does **not** yet add complete admin forms (Patch 03), PKR price aggregation (Patch 04),
Pakistan filters/API (Patch 05), Gemini agent/web research (Patches 08–10), or Three.js (Patch 13).

## Apply from PowerShell

From `C:\Users\ak821\Desktop\phone-discover`, finish/commit Patch 01 first (including the
port correction). Do not stage/commit `.env` or `backend/.env.local`.

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\ak821\Desktop\phone-discover'
$patch = Join-Path $HOME 'Downloads\phone-discover-patch-02-pakistan-schema.patch'
if (-not (Test-Path -LiteralPath $patch)) { throw "Not found: $patch" }
if (git status --porcelain) { git status --short; throw 'Commit or safely preserve existing changes first.' }

git apply --check -- $patch
if ($LASTEXITCODE -ne 0) { throw 'Patch does not apply. No files changed.' }
git apply -- $patch
if ($LASTEXITCODE -ne 0) { throw 'Patch application failed.' }
git -c core.whitespace=cr-at-eol diff --check
if ($LASTEXITCODE -ne 0) { throw 'Patch whitespace check failed.' }
```

## Migrate and test (uses your existing native Python environment)

```powershell
Set-Location 'C:\Users\ak821\Desktop\phone-discover\backend'
$python = '.\.venv\Scripts\python.exe'
& $python manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Django check failed' }
& $python manage.py makemigrations --check --dry-run catalog
if ($LASTEXITCODE -ne 0) { throw 'Migration/model drift detected' }
& $python manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
& $python manage.py test config catalog recommendations
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
```

The migration is **additive** but as always, back up valuable data before schema changes.
Do not use `docker compose down -v` or recreate your existing database volume.

## Future research pipeline safeguards

- Treat every third-party webpage as untrusted input; it must never provide tool instructions.
- Validate facts before writing canonical `Device` fields; store untrusted proposals in the staging tables.
- Check actual rights/terms for any source and the intended use before caching or republishing data.
- A PTA label on a listing is not verification of the exact handset's IMEI: keep provenance visible.
- AI research should not turn an old used listing into an asserted live market price.
- Do not store IMEIs or sensitive customer information in public catalog tables.
- Gemini API credentials are **not required** for this patch; later they go only in untracked env files.
