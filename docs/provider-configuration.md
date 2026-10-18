# Switching AI and web-search providers

The integrations support Gemini, OpenAI, Tavily Search, and the keyless product
page fallback. Change environment settings and restart Django; application code
does not need changing when switching between these supported services. Each
service keeps its own quota, available models and account requirements.

## One key field

In `backend/.env.local` for native development (or root `.env` for Docker):

```dotenv
API_KEY=your-key-here
API_PROVIDER=auto
WEB_SEARCH_PROVIDER=auto
```

With auto selection, an `AIza...` key selects Gemini, an `sk-...` key selects
OpenAI, and a `tvly-...` key selects Tavily. If your key has another format, set
`API_PROVIDER=gemini`, `openai`, or `tavily` explicitly. Unknown keys are reported
as a configuration error and are never tried against several services.

When `API_KEY` is nonempty, only that key is used. Old provider-specific keys are
ignored, so replacing the global key cannot accidentally send it to another
service or run requests against an old account.

Gemini and OpenAI support AI guidance and their respective built-in web search.
Tavily is a search provider: Tavily alone can discover product pages, extract
supported facts, save new phones/prices, and return cards without an AI model.
AI general guidance stays disabled in Tavily-only mode.

Clear `AI_MODEL` to use the existing provider-specific model defaults. Set it to
an accessible compatible model when you want to override the selected AI model.
No key or model setting bypasses a provider's account limits.

## Separate AI and search keys

Leave `API_KEY` empty to combine services:

```dotenv
API_KEY=
AI_PROVIDER=auto
WEB_SEARCH_PROVIDER=auto
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=
TAVILY_API_KEY=your-tavily-key
```

AI auto selection prefers Gemini, then OpenAI, otherwise local explanations.
Search auto selection prefers Tavily, then Gemini, then OpenAI, otherwise the
source-page fallback. To choose explicitly:

```dotenv
AI_PROVIDER=openai
WEB_SEARCH_PROVIDER=tavily
OPENAI_API_KEY=your-openai-key
TAVILY_API_KEY=your-tavily-key
```

Model overrides per service remain `OPENAI_CHAT_MODEL` and `GEMINI_CHAT_MODEL`.
`WEB_SEARCH_PROVIDER=source_pages` uses the existing website parser without an
API key. Tavily requests use basic search with automatic upgrades disabled.
If the selected service fails or exhausts quota, research falls back to supported
product pages rather than silently using another API account.

## Research switches and shared settings

Automatic research is already enabled in this installation. For another setup:

```dotenv
WEB_RESEARCH_ENABLED=1
AUTO_WEB_RESEARCH_ENABLED=1
WEB_RESEARCH_SOURCE_DOMAINS=whatmobile.com.pk,priceoye.pk
WEB_RESEARCH_TIMEOUT_SECONDS=60
```

The older `GEMINI_WEB_RESEARCH_ENABLED`, `GEMINI_AUTO_RESEARCH_ENABLED`,
`GEMINI_RESEARCH_SOURCE_DOMAINS` and `GEMINI_RESEARCH_TIMEOUT_SECONDS` settings
remain supported when their neutral equivalents are absent. Existing source
checks, catalog provenance, cached research, deduplication, price freshness,
and the human-review admin queue apply to every search adapter. The built-in
website parsers cover WhatMobile and unambiguous PriceOye Product metadata;
adding a different site's parser or a new API service requires an adapter.

## Verify your configuration

From `backend`:

```powershell
& .\.venv\Scripts\python.exe manage.py check_ai_provider
```

This prints selected services and whether automatic research is enabled, without
printing credentials or making provider requests. `check_web_research MESSAGE`
performs a live search with the selected service; add `--save` to import results.
Provider/model/key changes get separate cache entries. A Django restart loads
edited environment files. Refreshing only the browser does not reload backend
environment settings.

The assistant shows the selected services. The phone catalog and cards use the
same normalized records regardless of which search service discovered them.

Implementation references: [OpenAI Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search),
[Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search),
[Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search).
