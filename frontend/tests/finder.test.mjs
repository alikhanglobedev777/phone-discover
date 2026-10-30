import test from "node:test";
import assert from "node:assert/strict";
import { buildFinderRequest } from "../src/lib/finder.ts";

const base = {
  budget_pkr: "100000", city: "Lahore", condition: "used", pta_status: "approved",
  pta_verification: "checked", brand: "samsung", priorities: ["camera", "battery"],
  ram_min: "8", storage_min: "256", strict_budget: true,
};

test("complete finder includes exact user selections and strict budget", () => {
  assert.deepEqual(buildFinderRequest(base), {
    message: "Recommend phones for my selected preferences",
    max_results: 5, budget_pkr: "100000", city: "Lahore",
    condition: "used", pta_status: "approved", pta_verification: "checked",
    brand: "samsung", priorities: ["camera", "battery"], ram_min: "8",
    storage_min: "256", strict_budget: true,
  });
});

test("unselected filters are not forced or guessed", () => {
  const value = buildFinderRequest({
    ...base, budget_pkr: "", city: "", condition: "", pta_status: "",
    pta_verification: "", brand: "", ram_min: "", storage_min: "", priorities: [],
    strict_budget: false,
  });
  assert.deepEqual(value, { message: "Recommend phones for my selected preferences", max_results: 5, strict_budget: false });
});

test("DB-only finder never silently turns on paid AI research", () => {
  const value = buildFinderRequest(base);
  assert.equal("research" in value, false);
  assert.equal("guidance" in value, false);
  assert.equal("session_id" in value, false);
});
