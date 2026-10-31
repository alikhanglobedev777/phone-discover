import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const chat = readFileSync(new URL("../src/components/RecommendationAssistant.tsx", import.meta.url), "utf8");
const types = readFileSync(new URL("../src/lib/pakistan.ts", import.meta.url), "utf8");
const drawer = readFileSync(new URL("../src/components/AssistantDrawer.tsx", import.meta.url), "utf8");

test("chat stores specs-only recommendations and comparison instead of dropping API fields", () => {
  assert.ok(chat.includes("specsResults: response.specs_results"));
  assert.ok(chat.includes("comparison: response.comparison"));
  assert.ok(chat.includes("entry.specsResults.map((phone) => <SpecsCard"));
  assert.ok(chat.includes("entry.comparison.dimensions.map"));
  assert.ok(types.includes("specs_results?: SpecsRecommendation[]"));
  assert.ok(types.includes("comparison?: PhoneComparison | null"));
});

test("unpriced recommendations never render a fabricated price or PTA assurance", () => {
  assert.ok(chat.includes("Price and PTA unverified."));
  assert.ok(chat.includes("No budget, city or condition match is claimed."));
  assert.ok(chat.includes("phone.missing_scores.length > 0"));
});

test("specs results and comparison use the existing details modal", () => {
  assert.ok(chat.includes("onClick={() => onOpenDevice(phone.slug)}"));
  assert.ok(chat.includes("onClick={() => onCompareDevice(phone.slug)}"));
  assert.ok(drawer.includes("closeDrawer(); onOpenDevice(slug);"));
});
