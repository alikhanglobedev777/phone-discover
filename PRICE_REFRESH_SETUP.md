# Pakistan price refresh — administrator and Windows setup

This patch adds **Catalog → Price refresh runs** in Django admin (`http://127.0.0.1:8000/admin/catalog/pricerefreshrun/`). A **Refresh prices now** button launches a background one-batch refresh. Existing `Devices`, `Variants`, `Market price observations`, `Research sources`, review controls and gallery management remain in place.

## Required configuration

1. **Rotate any previously exposed API keys or passwords** and use only your private `backend/.env.local` for replacements.
2. Ensure Django and PostgreSQL are running (`py dev.py` from project root; Python launcher from earlier patch).
3. Add these lines to `backend/.env.local` (preserve your current valid Gemini key privately):

```dotenv
GEMINI_WEB_RESEARCH_ENABLED=1
WEB_SEARCH_PROVIDER=gemini
PRICE_REFRESH_ENABLED=1
PRICE_REFRESH_MAX_VARIANTS=40
PRICE_REFRESH_PRICE_CHANGE_LIMIT=0.35
PRICE_REFRESH_DELAY_SECONDS=1.0
```

`PRICE_REFRESH_MAX_VARIANTS` is a **per-run safety cap**, allowed 1–250. If your catalog contains more than 40 eligible RAM/storage variants, the scheduler will move through remaining (oldest-attempted-first, including failed checks) variants in subsequent runs; it does **not** guarantee that every variant will be checked in a single 48-hour cycle. Gemini searches may incur provider charges. Both source domains must be present in `GEMINI_RESEARCH_SOURCE_DOMAINS` if that variable is customized.

4. Apply database migration by starting `py dev.py`, or explicitly:

```powershell
cd "C:\Users\ak821\Desktop\phone-discover\backend"
.\.venv\Scripts\python.exe manage.py migrate
```

The patch includes migration `0007_price_refresh_runs.py`, **depending on `0006_device_gallery_colors.py` from the earlier photo/color patch**. If `0006` is missing, apply the gallery migration first.

## Authorize sources before publishing observations

In Django admin, open **Catalog → Research sources**. New source links discovered by research are created as **Not assessed**. An administrator must assess whether limited price-fact reuse is allowed, mark the relevant product source as **Permitted**, and record the basis in `reuse_notes`. Until then, a refresh records a **Blocked** count, not an observation. Source authorization is not implied by a public URL or by Gemini citation. Do not mark an unassessed site as permitted merely to force updates.

Prices recorded after authorization are **`web_reported`**, *not verified*. PTA approval and stock are not independently checked. Source URLs, observation timestamps and prior observations are retained. Prices over 35% away from the prior same-source observation are rejected for investigation. The process never edits manual verified observations, specifications, phones or variants. Availability of PriceOye/WhatMobile prices and exact variant matches depends on accessible, attributable pages; searches may yield no result, and the code does not guarantee a fresh quote from both sites.

## Run once / install every-two-days task

From project root:

```powershell
# One-off bounded run (when the backend environment is already set up):
cd "C:\Users\ak821\Desktop\phone-discover\backend"
.\.venv\Scripts\python.exe manage.py refresh_phone_prices --limit 20 --force
```

From project root, install the task explicitly:

```powershell
cd "C:\Users\ak821\Desktop\phone-discover"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install-price-refresh-task.ps1"
```

Windows Task Scheduler will then call `scripts/run-price-refresh.cmd` **every two days at 9 AM**, under your logged-in Windows account, without opening the website or starting the Django dev server. It **does require** the computer to be awake, the user logged in, PostgreSQL/network access, and available Gemini quota. Installing the task does *not* automatically install or start PostgreSQL; ensure your database service/Docker Desktop is running.

View/edit the task in **Task Scheduler → Task Scheduler Library → PhoneDiscoverPriceRefresh**. For a more reliable always-on deployment, use an actual server scheduler rather than a local PC. To remove it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\remove-price-refresh-task.ps1"
```

## Admin button

Log in as a **Django superuser**, then open **Catalog → Price refresh runs → Refresh prices now**. The CSRF-protected POST launches a bounded asynchronous Python command, and the run's status/counters appear in the table. This button uses a local subprocess and is designed for your Windows development setup, not as a production job queue. It is blocked if a current refresh is already running. Check Django terminal and the refresh run table after clicking.

## Backend checks

```powershell
cd backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test catalog.test_price_refresh
```

The scheduler is opt-in. Nothing starts paid web research merely from applying this patch.
