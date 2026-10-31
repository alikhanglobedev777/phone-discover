# Evidence-aware recommendations and comparison (Stages 5–7)

## Truth contract

Phone Discover separates four independent classes of information:

1. **Catalog record** — saved product specifications; useful to describe a phone but **not independently verified** by default.
2. **Reviewed claim and source** — a `DeviceClaim` explicitly reviewed by a human with a permitted `ResearchSource`. Only approved HTTPS links are returned. Claims older than 365 days are labeled potentially outdated.
3. **Editorial performance scores** — existing optional camera/gaming/battery 0–100 values. Absent/zero means *not rated*, never 0 performance. Scores are **not independent benchmarks**, especially if no linked review exists.
4. **Pakistan market price evidence** — source-permitted, reviewed, current observations, kept separate by storage, city, condition, grade, PTA classification and evidence strength. Larger mAh, pixels, or RAM must not be treated as a performance winner.

No formula pretends that memory, processor name, battery mAh, megapixels, or display refresh prove real photo quality, gaming frame rate, or battery endurance.

## How advice now works

- Exact-phone chat cards expose provenance tier, verification date (when present), approved source links and warnings.
- Specs-only recommendations identify the number of documented hardware features; when performance scores are absent the results are **examples ordered by documented spec coverage**, not a best-to-worst performance ranking.
- Two-phone comparisons show editorial scores (with missing-score checks), hardware facts side-by-side, and observed PKR price ranges only where both phones have comparable published, reviewed observations. Better value is not claimed from price alone.
- The public `/api/catalog/status/` response includes cached counts for published devices/variants, reviewed claims, freshness and editorial rating coverage.
- Operators can inspect the read-only report with `python manage.py audit_catalog_quality --json`.

## Human verification workflow

- Review an authoritative manufacturer document or independent benchmark and check reuse permissions.
- Save its URL as `ResearchSource` with `reuse_status=permitted`, permissions notes and `last_checked_at`.
- Create a `DeviceClaim` for the relevant exact device + field path; review it with `status=verified` and `reviewed_at` to surface it publicly.
- Check `Device.last_verified_at` after a real catalog verification. Do not stamp records without verifying them.
- Use reviewed, comparable independent tests (e.g., the same protocol for two phones) before publishing camera, gaming or battery performance scores; distinguish editorial judgments from measured results.
- Reassess claims older than 365 days. Refresh market price evidence within existing condition-specific freshness windows.

**Existing data is not retroactively labeled verified.** In the connected production catalog as inspected October 31, 2026, there were zero independently verified claims, manufacturer URLs, device verification dates or editorial quality scores. That is an editorial content backlog, not a bug to repair by filling arbitrary numbers.

## Tests

The existing `finder-checks.yml` runs backend source/price comparison tests, API/chat regressions, and frontend lint/UI/build.

The `browser-quality.yml` workflow uses actual headless Chromium on a production frontend build, with stubbed API responses (never contacting the live catalog), and tests phone name/image, provenance, comparison action, modal open and responsive dialog geometry at 1280px and 375px. It can be dispatched manually from GitHub Actions.

`live-chat-smoke.yml` separately verifies the deployed HTTP API against the real catalog using disposable session IDs. This does not replace visual/browser testing.

No database migrations, unreviewed source ingestion, or blind production data updates are part of this change.
