# Groq AI and missing-phone web research

Phone Discover can use **Groq GPT-OSS with its built-in browser_search** to discover product pages when the conversation has no eligible local PostgreSQL result. The backend then retrieves supported WhatMobile / PriceOye product pages and extracts their explicit phone variant and PKR asking price; only passing records enter PostgreSQL as **web_reported**, not independently verified. Groq text output itself is never trusted as a price source. This process is not a guarantee that every phone will be discovered.

Groq's built-in browser_search is currently supported for `openai/gpt-oss-20b` and `openai/gpt-oss-120b`. The old `groq/compound` model names were retired in September 2026. Browser search does not require a second Tavily/Exa key, but it is subject to your account's usage limits and availability. See https://console.groq.com/docs/tool-use/built-in-tools/browser-search .

## Private configuration (`backend/.env.local`)

```dotenv
API_KEY=
API_PROVIDER=auto
AI_PROVIDER=groq
GROQ_API_KEY=YOUR_PRIVATE_NEW_GROQ_KEY
GROQ_MODEL=openai/gpt-oss-20b
GROQ_WEB_MODEL=openai/gpt-oss-20b
WEB_SEARCH_PROVIDER=groq
GEMINI_WEB_RESEARCH_ENABLED=1
GEMINI_AUTO_RESEARCH_ENABLED=1
```

The two last `GEMINI_...` flags are **legacy generic web-research feature switches** in the existing Django code. They enable web research and its automatic missing-phone fallback even when the search provider is Groq; they do **not** send requests to Gemini. Don't commit real API keys. Leave `API_KEY` empty to use provider-specific keys. Restart the backend after changes.

## Verify on Windows

From your repository root, run `py dev.py`. From a second PowerShell terminal:

```powershell
cd "C:\Users\ak821\Desktop\phone-discover\backend"
.\.venv\Scripts\python.exe manage.py check_ai_provider
.\.venv\Scripts\python.exe manage.py check_web_research "Samsung Galaxy A57 8GB 256GB Pakistan"
```

The second command makes a **real Groq browser-search request**, consumes free-tier quota, but **does not save**. Check `provider: groq` and `status: grounded_preview`. To explicitly test database import:

```powershell
.\.venv\Scripts\python.exe manage.py check_web_research "Samsung Galaxy A57 8GB 256GB Pakistan" --save
```

For the chatbot, automatic web research only runs when there are no suitable local results and the search switches are enabled. Successful imported records are reused by subsequent local searches. Existing 48-hour refresh jobs continue to use the selected search provider's research pipeline subject to exact-variant matching and source permissions. Imported price claims remain unreviewed. Your admin can review them.

## Limitations and safeguards

- Only HTTPS allowlisted PriceOye and WhatMobile product pages are fetched; off-domain search results are ignored. No arbitrary Groq-generated URL is fetched.
- The server parses the retailer's actual page: **no source page, exact variant or explicit PKR price = no database write**. Some retailer pages cannot be parsed, so the tool can return `no_sources` even when a phone exists online.
- Rate limits, disabled web tools, 401/403 credentials errors and 429 quota errors are handled; the old source-page discovery remains an optional fallback, not a Gemini call.
- Built-in browser search can have different free-tier limits than plain text generation. Monitor https://console.groq.com/settings/limits .
- The model can choose search pages, but it cannot directly set stored prices, PTA verification, city, or stock in the database.
- Configuration is all backend. No new Django migrations or frontend assets are required.
