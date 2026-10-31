import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const chat = readFileSync(new URL("../src/components/RecommendationAssistant.tsx", import.meta.url), "utf8");
const drawer = readFileSync(new URL("../src/components/AssistantDrawer.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/brand-refresh.css", import.meta.url), "utf8");

test("chat retains specs-only catalog details returned by the API", () => {
  // Regression: backend returned catalog_details but React silently dropped it.
  assert.ok(chat.includes("catalogDetails: response.catalog_details"));
  assert.ok(chat.includes("entry.catalogDetails?.map((phone) =>"));
});

test("catalog phone links open the existing modal without losing deep linking", () => {
  assert.ok(chat.includes("href={`/?device=${encodeURIComponent(phone.slug)}`}"));
  assert.ok(chat.includes("event.preventDefault();"));
  assert.ok(chat.includes("onOpenDevice(phone.slug);"));
  assert.ok(drawer.includes("closeDrawer(); onOpenDevice(slug);"));
  assert.ok(app.includes("<PhoneDetail device={activeQuery.data}"));
  assert.ok(css.includes(".chat-drawer .chat-phone-link-row a"));
});
