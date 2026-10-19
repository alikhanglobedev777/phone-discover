import { test } from "node:test";
import { strict as assert } from "node:assert";
import { canCompareStartingPrices } from "../src/lib/comparison.ts";

const offer = (price, currency) => ({ lowest_price: { price, currency, country_code: "PK" } });

test("highlighting prices is safe within one currency", () => {
  assert.equal(canCompareStartingPrices([offer("85000", "PKR"), offer("94000", "PKR")]), true);
  assert.equal(canCompareStartingPrices([offer("999.99", "USD"), offer("1200", "USD")]), true);
});

test("prices in different currencies are never ranked numerically", () => {
  assert.equal(canCompareStartingPrices([offer("90000", "PKR"), offer("499", "USD")]), false);
});

test("missing, invalid and non-finite offers do not receive best-price highlights", () => {
  assert.equal(canCompareStartingPrices([offer("90000", "PKR"), { lowest_price: null }]), false);
  assert.equal(canCompareStartingPrices([offer("-1", "PKR"), offer("1000", "PKR")]), false);
  assert.equal(canCompareStartingPrices([offer("unknown", "USD"), offer("100", "USD")]), false);
  assert.equal(canCompareStartingPrices([offer("", "USD"), offer("100", "USD")]), false);
  assert.equal(canCompareStartingPrices([offer("Infinity", "USD"), offer("100", "USD")]), false);
  assert.equal(canCompareStartingPrices([offer("100", "USD")]), false);
});
