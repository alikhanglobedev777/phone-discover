import { test } from "node:test";
import assert from "node:assert/strict";
import { selectLatestPhones } from "../src/lib/latestPhones.ts";

function model(slug, release_date, status = "available", brand = "Samsung") {
  return { slug, name: slug, release_date, status, brand: { name: brand } };
}

test("latest selection mixes brands in strict release-date order", () => {
  const choices = [
    model("apple-old", "2025-03-01", "available", "Apple"),
    model("samsung-new", "2026-09-18", "available", "Samsung"),
    model("xiaomi-newer", "2026-10-14", "available", "Xiaomi"),
    model("google-future", "2026-12-01", "available", "Google"),
    model("motorola-no-date", null, "available", "Motorola"),
    model("vivo-unreleased", "2026-10-19", "announced", "Vivo"),
  ];
  assert.deepEqual(
    selectLatestPhones(choices, 4, new Date(2026, 9, 22)).map((x) => x.slug),
    ["xiaomi-newer", "samsung-new", "apple-old"],
  );
});

test("duplicate models, future dates and missing dates are not featured", () => {
  const entries = [
    model("samsung-s", "2026-10-20"),
    model("samsung-s", "2026-10-20"),
    model("apple-a", null),
    model("google-x", "2027-01-01"),
    model("itel-i", "2026-10-16"),
  ];
  assert.deepEqual(
    selectLatestPhones(entries, 4, new Date(2026, 9, 22)).map((x) => x.slug),
    ["samsung-s", "itel-i"],
  );
});

test("limit is honored and announced phones are never mistaken for releases", () => {
  const entries = [
    model("first", "2026-10-18"),
    model("second", "2026-10-16"),
    model("third", "2026-10-14"),
    model("announcement", "2026-10-20", "announced"),
  ];
  assert.deepEqual(
    selectLatestPhones(entries, 2, new Date(2026, 9, 22)).map((x) => x.slug),
    ["first", "second"],
  );
});
