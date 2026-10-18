# Pakistani catalog data

An HTTP 200 with `count: 0` is a successful empty query. Migrations create the
schema, not phone records. The original `seed_demo` command only creates sample
USD offers; those cannot satisfy the Pakistani evidence search.

The two real snapshots contain twelve phones (seven brands) and sixteen source
price observations from WhatMobile and PriceOye. Pages were checked on
18 October 2026, Asia/Karachi. It is a small starting catalog, not a live feed or
complete copy of either website.

From `backend`:

```powershell
& .\.venv\Scripts\python.exe manage.py import_market_snapshot catalog/data/pakistan-2026-10-18.json
& .\.venv\Scripts\python.exe manage.py import_market_snapshot catalog/data/pakistan-more-2026-10-18.json
```

This transaction is repeatable. It preserves the original observation date and
later admin edits. It fails if an existing source is restricted or unassessed.
The JSON records URLs, exact RAM/storage, review notes and the intended-use
basis for these limited factual excerpts. No product photographs, descriptions,
reviews or personal contact details were copied. Source review means checking
the displayed facts, not an independent guarantee of prices or handset status.

All twelve phones include a source-hosted product image from their corresponding
WhatMobile page. Images remain hosted by the source and require internet access.
The importer fills missing primary images and adds a gallery entry without
replacing artwork selected in admin. Re-importing does not duplicate galleries.
The expansion adds Galaxy A17, Galaxy A56, Vivo V60 Lite (4G), Realme C75,
Tecno Spark 40, Oppo A5 Pro (4G), and Infinix Note 50. Spark 40 has separate
WhatMobile and PriceOye price observations for its 6GB/128GB variant.

WhatMobile entries are national new-phone reference prices, not retailer stock.
The PriceOye A26 listing is marked ended because the product page says
discontinued. The PriceOye Redmi Note 14 price was omitted because its page
exposed multiple memory variants without an unambiguous price-to-variant mapping.
PTA status, city and stock remain unknown; camera/gaming/battery scores were not
invented. Consequently used-phone, city-specific or PTA-approved filters may
still return no matches. Use a new conversation to clear earlier constraints.

Box-pack observations expire from public search after 30 days. Recheck the
original pages and import a new dated snapshot when updating evidence; rerunning
the old file must not make stale prices appear fresh. Additional reviewed data
can be entered through Django admin.

`GET /api/catalog/status/` reports `empty`, `missing_prices`, or `ready`, plus
whether Gemini web research is configured. It exposes no credentials or drafts.
The assistant disables research when the server setting is off. General Gemini
guidance does not populate the catalog and does not verify prices.
