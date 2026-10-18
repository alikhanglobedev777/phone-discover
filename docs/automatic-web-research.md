# Automatic phone discovery

See [provider configuration](provider-configuration.md) to switch between Gemini,
OpenAI, Tavily, and source-page research using environment settings only.

The conversation endpoint checks the catalog first. If no exact local result
exists and automatic research is configured, it searches the web without requiring
the browser checkbox. Successful discoveries create published devices, exact
RAM/storage variants, image links where available, and attributed PKR price
observations. The assistant returns cards and refreshes the catalog/brand/market
queries so new phones appear in the phone list immediately.

Local configuration has been enabled for this installation. For another setup:

```text
GEMINI_WEB_RESEARCH_ENABLED=1
GEMINI_AUTO_RESEARCH_ENABLED=1
GEMINI_RESEARCH_SOURCE_DOMAINS=whatmobile.com.pk,priceoye.pk
GEMINI_RESEARCH_TIMEOUT_SECONDS=60
```

Use an existing `GEMINI_API_KEY` in the private environment file. Restart Django
after changing configuration and run `python manage.py migrate --noinput`.
There are no new Python dependencies or Celery requirements for conversational
research; the older admin research queue remains separate.

The primary provider uses Gemini Google Search grounding and accepts product
URLs only when supported by citation metadata and the configured source list.
When Google is unavailable or out of quota, a bounded WhatMobile product-page
lookup can extract real prices and exact physical memory specifications directly.
It supports exact models and limited brand-list discovery. Used-phone requests
need sources that actually supply used listings; new-phone reference pages do
not establish used prices, city availability or PTA approval.

Web imports have `data_source=web_research` and prices have
`verification_status=web_reported`, with no independent review timestamp. They
are labeled on the assistant, market and catalog cards. They do not manufacture
camera scores or independent PTA verification. Unknown city/PTA details stay
unknown; helpful web references remain separate from exact matches. Restricted
sources, unpublished phones, rejected observations, pending admin proposals,
ended listings, stale evidence and invalid/uncited data are excluded as appropriate.

Each result is validated before a per-phone transaction. Repeated discoveries
reuse identities/variants and update the same web price observation; they do not
overwrite curated specifications, images or existing reviewed price records.
Equivalent searches use a ten-minute cache, with short negative caching and a
lock against duplicate requests. Cache hits do not refresh evidence timestamps
and recheck public visibility. New research is limited to 12 requests per hour
by default (`GEMINI_RESEARCH_RATE_LIMIT`); cached searches do not consume that
provider-request allowance.

Run one live diagnostic without exposing credentials:

```powershell
cd backend
& .\.venv\Scripts\python.exe manage.py check_web_research 'Samsung Galaxy A57 under PKR 200000' --save
```

The live test on 18 October 2026 encountered exhausted Google research quota.
The source-page fallback successfully imported Galaxy A57, saved its cited price,
returned a card, and made the model available to subsequent local searches.
Google-backed research requires available quota on the configured API project.

Provider references: [Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search)
and [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).
