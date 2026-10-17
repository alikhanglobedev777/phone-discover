# Patch 03 — Django Admin for Pakistani smartphone data

This patch adds a **manual administration layer** to the Patch 02 schema. It is
not a public-facing dashboard or a research agent. **It does not scrape the
internet or ingest AI output into the catalog automatically.**

## Data entry workflow

1. Log in at `/admin/` with a trusted Django staff/superuser account.
2. Open **Brands**, then **Devices**. Create a phone with its real identity,
   source/official URL, publication status and a unique slug. Add image URLs,
   RAM/storage variants, and specification section headings in the same form.
3. To add section items, open the **Specification sections** editor for that
   phone. Add labels and values (for example, Display -> Panel -> OLED).
4. To add Pakistani prices, open **Device variants**, select the exact RAM and
   storage configuration, and expand **Pakistan PKR market observations**; or
   add a record directly in **Market price observations**.
5. Record **condition** (box pack, open box, used or refurbished) separately
   from **PTA status**, including whether any approval was merely reported by a
   source or checked independently. A CPID/patched classification is never
   equivalent to official PTA approval.
6. Record PKR price minimum and maximum, city, observation time, evidence,
   listing status and optional used-phone battery health. Historical observations
   remain available for review; a price is not proof of current availability.
7. Mark observations verified only with acceptable evidence. Django Admin
   records a review timestamp and validates price ranges and conditions.

**Phone publication is a separate manual admin decision.** A newly created
phone remains unpublished by default unless an admin explicitly publishes it.
Legacy `MarketOffer` fields and public API behavior remain unchanged by this
patch; the price engine and frontend consumption will be developed later.

## Research review workflow

- **Research sources**: classify origin and explicitly document the permission
  or other lawful basis for reusing source material before marking the source
  `permitted`. Unknown is not equivalent to permitted.
- **Device claims**: review proposed phone facts. Claims from sources lacking a
  documented `permitted` reuse status cannot be verified in Admin.
- **Ingestion candidates**: inspect the escaped, read-only untrusted JSON
  proposal; approve for a *future* ingestion service or reject it. Approval does
  **not** write the proposed device, variant or price into public tables.
  The `ingested` status cannot be selected manually.
- Bulk review actions validate each selected record, set the review timestamp,
  and report skipped records. They never execute the candidate payload.

## How to verify on Windows

Starting from a **clean committed Patch 02** checkout:

```powershell
cd "C:\Users\ak821\Desktop\phone-discover"
$patch = "$HOME\Downloads\phone-discover-patch-03-admin-workflows.patch"
git apply --check -- "$patch"
if ($LASTEXITCODE -ne 0) { throw "Patch 03 is incompatible" }
git apply -- "$patch"
if ($LASTEXITCODE -ne 0) { throw "Patch 03 could not be applied" }

git -c core.whitespace=cr-at-eol diff --check
if ($LASTEXITCODE -ne 0) { throw "Git diff failed validation" }

cd backend
.\.venv\Scripts\python.exe manage.py check
if ($LASTEXITCODE -ne 0) { throw "Django check failed" }
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run catalog
if ($LASTEXITCODE -ne 0) { throw "Unexpected migration changes" }
.\.venv\Scripts\python.exe manage.py test config catalog recommendations
if ($LASTEXITCODE -ne 0) { throw "Test suite failed" }
```

Expected: the original 30 tests plus 14 new Admin workflow tests, **44 tests
in total**, provided the same Patch 02 test baseline is present.

To create a first administrative account locally (only if one doesn't exist):

```powershell
cd "C:\Users\ak821\Desktop\phone-discover\backend"
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Access `/admin/` on your existing development server.

## File changes

- `backend/catalog/admin.py`: branded, searchable editors with structured
  inlines, source review, market prices and evidence-gated bulk review actions.
- `backend/catalog/admin_forms.py`: form-level validation and review timestamps.
- `backend/catalog/test_admin_workflows.py`: Admin access, data entry, review
  safety, rights, and HTML escaping regression tests.
- `PATCH_03_ADMIN.md`: operational guidance and explicit scope.

No schema migration is required by Patch 03.

## Limits and security

- Django Admin is for authorized staff. Do not expose it without HTTPS,
  strong credentials and an appropriate production access policy.
- Source URLs and AI-origin JSON are untrusted. The Admin UI does not fetch
  them, and the JSON preview escapes HTML.
- Admin permissions do not replace the later automatic ingestion validator.
- Specs and scores remain manually editable; they are not automatically
  benchmark-verified.
- No Gemini API key is needed in this patch.
