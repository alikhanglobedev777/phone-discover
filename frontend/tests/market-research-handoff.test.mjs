import test from "node:test";
import assert from "node:assert/strict";
import { marketResearchHandoff, conversationPayload } from "../src/lib/pakistan.ts";

const filters = {
  q: "Snapdragon", city: "Lahore", budget_pkr: "80000", condition: "used",
  pta_status: "approved", pta_verification: "reported", ram_min: "8", sort: "price",
};

test("market to AI handoff preserves the visitor's filters and opts into research", () => {
  const handoff = marketResearchHandoff(filters);
  assert.match(handoff.message, /Snapdragon/);
  assert.match(handoff.message, /Lahore/);
  assert.match(handoff.message, /PKR 80000/);
  assert.match(handoff.message, /source/i);
  assert.equal(handoff.pending.reset_context, true);
  assert.equal(handoff.pending.ram_min, 8);
  assert.equal(handoff.pending.pta_verification, "reported");
  const request = conversationPayload("unique-session", handoff.message, true, handoff.pending);
  assert.equal(request.research, true);
  assert.equal(request.condition, "used");
  assert.equal(request.budget_pkr, "80000");
  assert.equal(request.pta_status, "approved");
  assert.equal(request.city, "Lahore");
});

test("clearing market filters cannot carry over stale chat preferences", () => {
  const handoff = marketResearchHandoff({
    q: "", city: "", budget_pkr: "", condition: "", pta_status: "",
    pta_verification: "", ram_min: "", sort: "relevance",
  });
  assert.equal(handoff.pending.reset_context, true);
  assert.equal(handoff.pending.city, null);
  assert.equal(handoff.pending.pta_status, null);
  assert.equal(handoff.pending.ram_min, null);
  assert.ok(handoff.message.length <= 1000);
});
