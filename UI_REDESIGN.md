# Phone Discover — Monochrome UI Redesign

This revision focuses on the **frontend**. The Django backend, database migrations, endpoints, evidence requirements, and research configuration are intentionally left unchanged.

## What changed

- White/black monochrome visual language, removing the former blue/purple/navy palette throughout the frontend.
- All chatbot text is black; chatbot headers, controls, sidebars, messages, result cards, tooltips, action buttons, and composer have white backgrounds. Borders and typographic hierarchy distinguish interaction states.
- New responsive editorial homepage with a clear value proposition, navigation, primary assistant CTA, PKR-market CTA, and three accurate feature explanations. The assistant appears before the market and secondary catalog.
- Marketing copy distinguishes observed asking prices and source-reported research from guaranteed live offers. New page title, search description, Open Graph metadata, and transparent footer disclaimer.
- Rebuilt spacing, typographic scale, inputs, buttons, cards, comparison tray, dialogs, and responsive behavior around shared design tokens in `frontend/src/design-system.css`.
- Chat usability: keyboard shortcut Ctrl/Cmd+Enter, scrolling to new messages, recognizable two-part layout, improved legibility, clear service status, retry-preserving input, and request cancellation on new chat/unmount.
- Dialog hardening: keyboard focus trapping, Escape handling, page scroll locking, and focus restoration in a shared hook.
- Comparison UX: limit to three phones with clear feedback; shortlist remains visible while shopping; clipboard failure feedback; starting-price highlighting is disabled when any price is missing/invalid or currencies differ.
- Recoverable catalog, brand, price-search, and phone-detail loading errors with retry/close controls, rather than silent or misleading empty states.
- Removed the ambiguous mixed-currency numeric price filter from the reference catalog; buyers seeking a PKR price ceiling are directed to the evidence-backed Pakistan market search.
- Accessible focus outlines, descriptive action labels, reduced-motion support, 320px responsive layout checks, and minimum usable control sizes.

## Key files

| File | Purpose |
| --- | --- |
| `frontend/src/design-system.css` | New, documented monochrome design system and responsive rules |
| `frontend/src/styles.css` | Existing structural CSS, palette normalized to achromatic values |
| `frontend/src/App.tsx` | Marketing layout, navigation, error and shortlist states |
| `frontend/src/components/RecommendationAssistant.tsx` | White-on-white chatbot redesign and interaction improvements |
| `frontend/src/components/PakistanMarket.tsx` | Honest evidence wording, consistent controls and retry states |
| `frontend/src/components/ComparisonModal.tsx` | Safe price highlighting and share feedback |
| `frontend/src/lib/comparison.ts` | Currency-safe comparison helper |
| `frontend/src/lib/useModalKeyboard.ts` | Accessible dialog focus and keyboard helper |
| `frontend/tests/comparison.test.mjs` | Price comparison safety tests |
| `frontend/tests/monochrome.test.mjs` | CSS palette and chatbot contrast regression tests |

## Validation performed

- `npm run test:ui`: **15 passed** (9 existing tests, 3 comparison tests, and 3 palette checks).
- TypeScript/TSX syntax parsing: **15 source files, no parse diagnostics**.
- CSS parsing: `styles.css` and `design-system.css` parsed without stylesheet errors.
- Palette audit: no chromatic hex/RGB values in either stylesheet.
- Headless Chromium *layout mock* at widths 1440, 768, 390 and 320px: no document horizontal overflow; computed chatbot backgrounds were white. This uses representative UI markup and does not imply full live-application testing.

**Not verified:** a complete `npm run build` and integration with live backend data. Installing the required frontend dependencies did not complete in the sandbox. Run the build locally or in CI as below.

## Run and verify locally

```bash
cd frontend
npm ci
npm run lint
npm run test:ui
npm run build
npm run dev
```

The backend still needs to be running at the API origin configured by `vite.config.ts` for catalog, market and assistant content.

## Limitations / follow-on work

The frontend changes do not alter the trustworthiness of third-party price evidence or AI research. The existing backend review and search correctness issues still need separate treatment. This pass also does not implement login, analytics, or commercial conversion tracking.
