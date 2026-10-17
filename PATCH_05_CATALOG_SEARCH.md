# Patch 05: verified Pakistan catalog search (read-only)

New endpoint: `GET /api/catalog/search/`. This is the **DB-first tool** for a future conversational Gemini agent. It performs **no external search, inference, or writes**.

Examples:

- `/api/catalog/search/?condition=used&pta_status=approved&city=Lahore&budget_pkr=80000`
- `/api/catalog/search/?brand=samsung&ram_min=8&storage_min=256&gaming_min=75&sort=gaming`
- `/api/catalog/search/?q=Galaxy&require_price=false` (specifications-only, no verified price required)

Parameters: `q`, `brand` (slug), `os`, `status`, `ram_min`, `storage_min`, `camera_min`, `gaming_min`, `battery_min`, `condition`, `grade` (used/refurbished only), `pta_status`, `pta_verification` (`reported` vs `checked`), `city`, `budget_pkr`, `budget_mode` (`strict` default, or `possible`), `require_price` (true by default), `sort` (`relevance`, `price`, `camera`, `gaming`, `battery`, `newest`, `name`), `page` and `page_size` (1–50).

The output has one matching variant per published phone, with `slug`, `detail_api_url`, exact variant properties, and at most one properly labeled **verified observed price** from that same variant. It includes the price's condition, grade, city and PTA provenance, but does not pretend to prove a particular handset is PTA-approved. Price samples are **not live offers**. `needs_research=true` when no usable local match remains after filtering; this flag does not itself initiate a web request.

In strict budget mode, `price_max_pkr` must be within budget on a single observed price range. `possible` mode accepts an observation whose *minimum* is within budget. No cross-currency comparisons or legacy `MarketOffer` prices are used. Stale, rejected, future, ended, restricted and undocumented observations are excluded.

**Important:** The legacy `/api/catalog/devices/` endpoint still exists for compatibility with the current React app. It has its older filter and offer semantics; future AI search **must call `/api/catalog/search/` instead**. A later UI/API patch should migrate the legacy device filter to the new strict semantics rather than rely on legacy cross-variant joins.

The endpoint is anonymous and read-only with a separate `catalog_search` throttle (default 120 requests/hour). Its in-memory final selection and device deduplication are suitable for an early catalog; measure and optimize for large catalog sizes before public launch. No migrations or credentials are introduced by this patch.

## Verification (PowerShell)

```powershell
cd C:\Users\ak821\Desktop\phone-discover\backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run catalog
.\.venv\Scripts\python.exe manage.py test config catalog recommendations
```
