import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const chat = readFileSync(new URL("../src/components/RecommendationAssistant.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/brand-refresh.css", import.meta.url), "utf8");

test("all catalog card kinds use the same clickable phone identity", () => {
  assert.ok(chat.includes("function PhoneCardHeader("));
  assert.ok(chat.includes("function openInModal("));
  assert.ok(chat.includes("onOpenDevice(slug);"));
  assert.ok(chat.includes("const href = `/?device=${encodeURIComponent(slug)}`"));
  assert.ok(chat.includes("<PhoneCardHeader slug={phone.slug} brand={phone.brand} name={phone.name}"));
  assert.ok(chat.includes("<PhoneCardHeader slug={device.slug} brand={device.brand} name={device.name}"));
  assert.ok(chat.includes("image={phone.primary_image_url} caption=\"Local catalog\""));
});

test("cards show key facts with clearly labeled evidence and no invented price", () => {
  assert.ok(chat.includes("className=\"chat-card-facts\""));
  assert.ok(chat.includes("className=\"chat-card-specs\""));
  assert.ok(chat.includes("phone.specification_sections.map"));
  assert.ok(chat.includes("Price and PTA unverified."));
  assert.ok(chat.includes("Saved catalog specifications. Prices and PTA status require separate evidence."));
  assert.ok(chat.includes("formatPriceRange(price)"));
});

test("photos, keyboard links and details/compare actions are usable in mini chat", () => {
  assert.ok(chat.includes("onError={() => setImageFailed(true)}"));
  assert.ok(chat.includes("loading=\"lazy\""));
  assert.ok(css.includes(".chat-drawer .chat-card-head"));
  assert.ok(css.includes(".chat-drawer .chat-card-photo-link"));
  assert.ok(css.includes(".chat-drawer .chat-card-title-link:focus-visible"));
  assert.ok(css.includes(".chat-drawer .pk-result-actions button"));
  assert.ok(chat.includes("Show only PTA-approved options"));
});
