import { test } from "node:test";
import assert from "node:assert/strict";
import { searchCachedPhones } from "../src/lib/catalogSearch.ts";

const entries = [
  { slug: "apple-iphone-16", name: "iPhone 16", brand: "Apple", brand_slug: "apple", image_url: "https://example.com/iphone16.jpg" },
  { slug: "apple-iphone-16-pro", name: "iPhone 16 Pro", brand: "Apple", brand_slug: "apple", image_url: "https://example.com/iphone16pro.jpg" },
  { slug: "apple-iphone-16-pro-max", name: "iPhone 16 Pro Max", brand: "Apple", brand_slug: "apple", image_url: "https://example.com/iphone16promax.jpg" },
  { slug: "google-pixel-9", name: "Pixel 9", brand: "Google", brand_slug: "google", image_url: "" },
  { slug: "samsung-galaxy-s24", name: "Galaxy S24", brand: "Samsung", brand_slug: "samsung", image_url: "" },
];

test("return empty suggestions for blank input", () => {
  assert.deepEqual(searchCachedPhones(entries, "   "), []);
});

test("name suggestions are immediate and exact match appears first", () => {
  const result = searchCachedPhones(entries, "IPHONE 16 Pro");
  assert.equal(result[0].name, "iPhone 16 Pro");
  assert.ok(result.some((x) => x.name === "iPhone 16 Pro Max"));
  assert.ok(result.every((x) => x.brand === "Apple"));
});

test("brand and model combined searches work across the entire index", () => {
  assert.deepEqual(
    searchCachedPhones(entries, "google pixel").map((x) => x.slug),
    ["google-pixel-9"],
  );
});

test("brand filter is applied locally and distinct Pro models are preserved", () => {
  assert.deepEqual(
    searchCachedPhones(entries, "iphone", "samsung"), [],
  );
  assert.deepEqual(
    searchCachedPhones(entries, "iphone", "apple", 2).map((x) => x.slug),
    ["apple-iphone-16", "apple-iphone-16-pro"],
  );
});

test("no result is invented for a model that is not in the cached catalog", () => {
  assert.deepEqual(searchCachedPhones(entries, "Pixel 99"), []);
});
