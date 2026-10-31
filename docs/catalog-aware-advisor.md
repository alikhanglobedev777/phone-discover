# Catalog-aware Phone Discover advisor

The conversation endpoint `POST /api/recommendations/converse/` retrieves
published catalog phones before any optional external research.

## Model lookup

- Exact-model lookup resolves common brand/name shorthands from published
  database devices, not a fixed enumeration of phone models. Longer matching
  aliases win: `Samsung S26 Ultra` does not mean `Galaxy S26`.
- An exact result returns `catalog_details` with a published slug and local
  stored specification sections; the existing frontend phone modal opens by slug.
- No same-brand sibling is substituted if the requested model does not exist.
- Unpublished devices, arbitrary research output and imported unreviewed prices
  are never exposed by the catalog resolver.

## Recommendations without verified prices

- If a phone recommendation has no eligible Pakistani price results, and the
  user asks about camera, gaming or battery, `specs_results` offers up to the
  requested `max_results` published specs-based candidates.
- `editorial_fit` is computed only from positive catalog editorial scores;
  zero or absent scores mean *not rated*, not zero capability.
- Results have `price_status: not_verified_for_filters`, and **never** claim
  eligibility for a requested budget, PTA status, condition or city.
- Battery mAh is labeled *capacity*, not battery endurance. Screen refresh rate
  and chipset are shown as facts, not independently measured gaming performance.
- Candidate exploration is bounded by `MAX_DISCOVERY_VARIANTS`; this is not a
  guaranteed worldwide ranking or benchmark leaderboard.

## Two-phone comparisons and follow-ups

Examples:

1. `Compare Samsung Galaxy S26 Ultra vs Pixel 7a`
2. `Samsung S26 Ultra` followed by `Compare it with Pixel 7a`
3. After (1) or (2), `Which one has better battery?`

The response's `comparison` lists the *exact two published phones*. Camera,
gaming and battery editorial scores are displayed side by side. When a score is
missing for either side, the API explicitly returns no winner. Neither PTA
eligibility nor a current asking price is inferred.

When chat memory is enabled, the server stores at most five recent device slugs
in the existing short-lived structured preference context. It does not persist
a chat transcript or provider response. New-chat reset still clears the context.

## Tests

CI runs frontend lint, UI tests and build, plus Django catalog, pricing,
conversation and `recommendations.test_catalog_advisor` tests with PostgreSQL.

Try `Google Pixel 7a info`, `s26 ultra`, `best camera phone`,
`best gaming phone`, `best battery phone` and the comparison examples above.

No new database migration, API key or background research job is required.
