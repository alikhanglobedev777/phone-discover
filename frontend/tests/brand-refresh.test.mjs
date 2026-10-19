import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const assistant = readFileSync(new URL("../src/components/AssistantDrawer.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/brand-refresh.css", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8");

test("catalog appears on homepage before the Pakistan market and there is no inline assistant", () => {
  assert.ok(app.indexOf('<section className="catalog-section"') < app.indexOf('<PakistanMarket'));
  assert.ok(app.includes('<AssistantDrawer'));
  assert.equal(app.includes('<RecommendationAssistant'), false);
});
test("all catalog pages remain reachable through explicit load more", () => {
  assert.ok(app.includes("useInfiniteQuery("));
  assert.match(app, /hasNextPage/);
  assert.ok(app.includes("fetchNextPage("));
  assert.ok(api.includes('query.set("page", String(page))'));
});
test("assistant remains a right-side dialog with a persistent state and keyboard escape", () => {
  assert.match(assistant, /right-side|className="chat-drawer"|chat-drawer/);
  assert.match(assistant, /aria-modal="true"/);
  assert.ok(assistant.includes("inert={!open}"));
  assert.ok(assistant.includes('event.key === "Escape"'));
  assert.match(assistant, /hasOpened/);
  assert.ok(css.includes(".chat-drawer {"));
  assert.ok(css.includes("position: fixed;"));
  assert.ok(css.includes("right: max(20px"));
});
test("animations respect reduced motion", () => {
  assert.ok(css.includes("@media (prefers-reduced-motion: reduce)"));
  assert.ok(css.includes("animation: none !important"));
});
