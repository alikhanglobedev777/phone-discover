# Patch 06: Pakistani AI-ready intent and local ranking

This patch adds a separate, **database-only** recommendation API for Phone Discover's Pakistani market. It uses the published / verified / licensed and fresh-price retrieval from Patch 05, not the old cross-currency `MarketOffer` flow.

## Endpoint

`POST /api/recommendations/local/`

Example request (English or Roman Urdu):

```json
{
  "message": "Mujhe Lahore mein 80 hazar tak used PTA approved gaming phone batao",
  "max_results": 3
}
```

Optional explicit filters override message parsing: `budget_pkr`, `condition`, `grade`, `pta_status`, `pta_verification`, `city`, `brand`, `priorities`, `ram_min`, `storage_min`, `strict_budget` and `max_results` (1–5). The API is **PK/PKR-only**; it rejects explicit foreign-currency prompts rather than silently comparing unconverted prices. A mixed new/used prompt must be disambiguated or given an explicit `condition`.

Example response (shortened; real phones and prices come only from the catalog):

```json
{
  "criteria": {
    "country_code": "PK", "currency": "PKR", "budget_pkr": "80000",
    "condition": "used", "pta_status": "approved", "city": "Lahore"
  },
  "results": [{
    "device": {"slug": "example", "detail_url": "/?device=example", "detail_api_url": "/api/catalog/devices/example/"},
    "variant": {"id": 1, "ram_gb": 8, "storage_gb": 256},
    "market_price": {"currency": "PKR", "condition": "used", "pta_verification": "reported", "availability": "not_confirmed"},
    "fit_score": 80.5,
    "fit_score_is_probability": false,
    "scoring_basis": "editorial_catalog_estimates_not_independent_benchmarks"
  }],
  "needs_research": true,
  "research_reason": "limited_local_evidence",
  "research_executed": false,
  "response_source": "deterministic"
}
```

The `fit_score` is a heuristic ranking based on editor-entered catalog scores and price. It is **not** an independently benchmarked phone-performance score, a verified match probability, a seller guarantee, a PTA certificate or an LLM judgement. Missing scores are labelled explicitly and cannot outrank otherwise comparable evidenced models by pretending to be zero-verified scores.

## Safety and scope

- Only `MarketPriceObservation` evidence permitted by Patch 04/05 is eligible; no fallback to currencies in `MarketOffer`.
- A strict PKR budget compares the **upper** observed price bound; a relaxed budget may use the lower bound but warns the user.
- PTA seller claims are always identified as **reported** unless marked independently checked; no handset IMEI is stored or inferred.
- The new view neither invokes Gemini/OpenAI nor searches the web or writes to `Device`, `DeviceVariant`, `MarketPriceObservation` or `IngestionCandidate`.
- It logs the request via the existing `RecommendationQuery` table for debugging/analytics under the existing retention policy. In this patch, `session_id` is *not* conversation memory.
- `needs_research` is a **signal**, not a promise that research ran. Agentic source discovery comes in Patch 08–10; conversation memory in Patch 07; frontend chat cards in Patch 11.
- For compatibility, the old `/api/recommendations/` endpoint remains unchanged. The new endpoint is intended for the Pakistan-focused frontend integration in a later patch.
- The local candidate scan is bounded to 250 cards and returns `coverage_incomplete=true` if the scan was truncated; it never claims to have searched more of the catalog than it did.

## Files

- `backend/recommendations/local_intent.py` — conservative English / Roman Urdu constraint parsing.
- `backend/recommendations/local_rank.py` — Pakistan evidence-backed shortlist, ranking, grounded reasons and research signal.
- `backend/recommendations/serializers.py`, `views.py`, `urls.py` — request validation and new endpoint.
- `backend/catalog/search.py` — expose refresh rate and battery capacity for local card scoring.
- `backend/recommendations/test_pakistan_local.py` — 20 new deterministic tests.

## Windows verification (existing `.venv` and Docker setup)

```powershell
cd "C:\Users\ak821\Desktop\phone-discover"
docker compose up -d db redis
cd backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test config catalog recommendations
```

Expected test discovery is **104** if all 84 earlier tests are present and discoverable plus the 20 new ones. Check for `OK`, not just the count. **No migrations are required** for Patch 06.

For repeatable testing, use a fresh local DB with reviewed price observations; demo catalog legacy offers by themselves are insufficient for this endpoint. A `needs_research` response when no fresh Pakistan prices have been entered is expected and honest.
