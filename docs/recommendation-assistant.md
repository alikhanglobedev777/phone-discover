# Recommendation assistant

The recommendation engine always ranks phones from local catalog facts. It
works without an AI key and returns up to three candidates with match scores,
strengths, tradeoffs, active offers, and one primary recommendation.

## Optional OpenAI explanation

Add a key to `backend/.env.local`:

```text
OPENAI_API_KEY=your-key
OPENAI_CHAT_MODEL=gpt-5.6-luna
```

The backend uses the OpenAI Responses API with `store: false`. The model only
explains candidates already selected by the deterministic ranking engine; it
does not choose prices, sellers, availability, or specifications. If the key is
missing or the model call fails, the API automatically returns a deterministic
explanation.

Official API documentation:
`https://developers.openai.com/api/docs/guides/migrate-to-responses`

## Recommendation API

`POST /api/recommendations/`

```json
{
  "message": "Best camera and battery phone under $600",
  "budget": 600,
  "currency": "USD",
  "country_code": "US",
  "priorities": ["camera", "battery"],
  "ram_min": 8,
  "storage_min": 128,
  "strict_budget": true
}
```

Supported priorities are `camera`, `gaming`, `battery`, `display`, and `value`.
Requests can also include `preferred_brands` and `excluded_brands` arrays.

## Analytics and privacy

Anonymous query analytics are visible under **Recommendation queries** in
Django admin. They contain a random browser session identifier, a query excerpt,
parsed criteria, result snapshots, and whether the explanation came from the
catalog engine or OpenAI. No account, email, or IP address is stored by this
feature.

The default retention period is 90 days. Delete older records with:

```powershell
cd backend
& .\.venv\Scripts\python.exe manage.py purge_recommendation_queries
```

Use `--days 30` to choose another retention window. The endpoint is throttled
to 30 anonymous recommendation requests per hour by default. Override this in
`backend/.env.local` with `RECOMMENDATION_RATE_LIMIT`.
