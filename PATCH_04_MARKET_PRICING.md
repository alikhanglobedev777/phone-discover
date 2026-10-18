# Patch 04 — Evidence-gated Pakistani PKR pricing guide

This patch adds an **informational price guide** for Phone Discover, not store
prices, live stock, purchase links, price guarantees or verified individual
handset PTA clearance. It only uses the separate `MarketPriceObservation` model
introduced in Patch 02, with review handled by the Patch 03 admin.

## API

- `GET /api/catalog/devices/<slug>/pakistan-prices/` — verified, currently
  fresh, comparable, deduplicated price observation groups for a published phone.
- `GET /api/catalog/devices/<slug>/` — existing phone details plus a
  `pakistan_prices` array (without requested filters).
- Optional query parameters on the dedicated endpoint:
  `variant_id`, `condition`, `grade`, `pta_status`, `pta_verification`, `city`,
  `budget_pkr`.

Examples:

```text
GET /api/catalog/devices/example-phone/pakistan-prices/?condition=used&pta_status=approved&city=Lahore&budget_pkr=80000
GET /api/catalog/devices/example-phone/pakistan-prices/?condition=box_pack
```

Each group contains the exact variant, phone condition, grade, PTA status,
PTA verification strength, city, PKR min/max observed ranges, median of
observed midpoints, sample counts, source references, last observation date,
condition-specific freshness limit, and optional budget-fit category.

**Never treat “PTA approved (reported)” as an independently verified handset.**
CPID/patched states are distinct from official PTA approval. A product or
listing that was marked active when recorded is not guaranteed to be active
now. Contact information and raw research payloads are not exposed.

## Inclusion rules

Only observations with `verification_status=verified`, a review timestamp,
non-future observation dates, not ended, and within the condition's freshness
limit are included:

| Condition | Days |
| --- | ---: |
| Box pack | 30 |
| Open box | 21 |
| Used | 14 |
| Refurbished | 21 |

For observations linked to a research source, its reuse status must be
`permitted` with documented permission/basis in `reuse_notes`. Admin-only
verified observations without a research-source link require nonblank written
human evidence in `notes`. Pending, rejected, restricted or undocumented
research observations are excluded. Publication state on the phone is also
required. Multiple observations of the same listing URL within one group
count once, using the most recently observed one.

No web fetching, automated verification or Gemini calls happen here. These
are explicit later milestones. This module is also an internal service that
later agentic ranking can query without relying on untrusted LLM arithmetic.

## Known scope limits

- This is a small observation-based *asking-price guide*, **not** a robust
  statistical estimate of real transaction values. Median-of-midpoints is a
  descriptive sample statistic, not a forecast; some groups have only one
  observation. The endpoint explicitly states counts and evidence type.
- Existing legacy `MarketOffer` and catalog `lowest_price` fields are
  unchanged and can span incomparable countries/currencies. **Do not use them
  as Pakistan price recommendations.** Patch 05 will address catalog-wide
  accurate variant/market filters and listing presentation.
- No automatic outlier detection, market scraping, conversion, data feed,
  currency forecasting or seller reputation scoring is introduced here.
- Freshness thresholds are policy defaults to review against real Pakistan
  listing practices before production, not a promise of source accuracy.
- Non-linked admin evidence is distinguished as `admin_documented`, which
  is not equivalent to independently corroborated sources.

## Verify (PowerShell from repo root)

```powershell
cd 'C:\Users\ak821\Desktop\phone-discover'
$patch = "$HOME\Downloads\phone-discover-patch-04-market-pricing.patch"
if (git status --porcelain) { throw 'Commit previous work first' }
git apply --check -- "$patch"
if ($LASTEXITCODE -ne 0) { throw 'Patch incompatible' }
git apply -- "$patch"
if ($LASTEXITCODE -ne 0) { throw 'Patch application failed' }
git -c core.whitespace=cr-at-eol diff --check
if ($LASTEXITCODE -ne 0) { throw 'Invalid diff' }

cd backend
$python = '.\.venv\Scripts\python.exe'
& $python manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Django check failed' }
& $python manage.py makemigrations --check --dry-run catalog
if ($LASTEXITCODE -ne 0) { throw 'Unexpected schema difference' }
& $python manage.py test config catalog recommendations
if ($LASTEXITCODE -ne 0) { throw 'Test failure' }
```

Expected after Patch 03: **65 tests** (44 existing + 21 Patch 04 tests).
Patch 04 adds no model fields or migrations.
