import test from "node:test";
import assert from "node:assert/strict";
import {
  activeFilterSummary, conversationPayload, formatPkr, formatPriceRange, marketQuery, safeSourceUrl, searchProviderLabel,
} from "../src/lib/pakistan.ts";

test("legacy status responses cannot crash provider rendering after loading", async () => {
  const { catalogStatus } = await import("../src/lib/pakistan.ts");
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({
    catalog_status: "ready", research_available: true, automatic_research: true,
  }) });
  try {
    const status = await catalogStatus();
    assert.equal(status.automatic_research, true);
    assert.equal(searchProviderLabel(status.search_provider), "configured web sources");
    for (const missing of [undefined, null, "", 42, {}]) {
      assert.equal(searchProviderLabel(missing), "configured web sources");
    }
    assert.equal(searchProviderLabel("source_pages"), "source pages");
    assert.equal(searchProviderLabel("tavily"), "tavily");
  } finally { globalThis.fetch = oldFetch; }
});

test("PKR only, without inventing a foreign exchange rate", () => {
  assert.equal(formatPkr("80000.00"), "PKR 80,000");
  assert.equal(formatPkr("NaN"), "PKR price unavailable");
  assert.equal(formatPriceRange({observed_min_pkr: "60000.00", observed_max_pkr: "70000.00"}), "PKR 60,000 – PKR 70,000");
});

test("only explicit updates are sent to a continuing conversation", () => {
  const payload = conversationPayload("opaque-uuid", "Samsung mein batao", false, {});
  assert.deepEqual(payload, { session_id: "opaque-uuid", message: "Samsung mein batao", research: false, guidance: false });
  assert.ok(!("priorities" in payload));
  assert.equal(conversationPayload("session", "camera?", false, {}, true).guidance, true);
  assert.deepEqual(conversationPayload("opaque-uuid", "used PTA", true, { condition: "used", pta_status: "approved", budget_pkr: "80000" }), {
    session_id: "opaque-uuid", message: "used PTA", research: true, guidance: false,
    condition: "used", pta_status: "approved", budget_pkr: "80000",
  });
});

test("market search keeps filters and pagination on strict evidence-backed endpoint", () => {
  const query = new URLSearchParams(marketQuery({
    q: "Samsung", city: " Lahore ", condition: "used", pta_status: "approved",
    pta_verification: "checked", budget_pkr: "80000", ram_min: "8", sort: "price",
  }, 2));
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("require_price"), "true");
  assert.equal(query.get("budget_pkr"), "80000");
  assert.equal(query.get("city"), "Lahore");
  assert.equal(query.get("pta_verification"), "checked");
});

test("cleared controls and complete-search reset reach the server explicitly", () => {
  const payload = conversationPayload("session", "show phones", false, {
    city: null, pta_status: null, budget_pkr: null, ram_min: null, priorities: [], reset_context: true,
  });
  const sent = JSON.parse(JSON.stringify(payload));
  assert.equal(sent.city, null);
  assert.equal(sent.pta_status, null);
  assert.equal(sent.reset_context, true);
  assert.deepEqual(sent.priorities, []);
});

test("active filters reveal remembered constraints and omit cleared values", () => {
  const summary = activeFilterSummary({budget_pkr: "120000", city: "Karachi", condition: "box_pack", pta_status: "approved", ram_min: null, priorities: ["camera"]});
  assert.match(summary, /City: Karachi/);
  assert.match(summary, /PTA: approved/);
  assert.match(summary, /Condition: box pack/);
  assert.ok(!summary.includes("Minimum RAM"));
});

test("external citations use https domain names, never localhost/credentials/script schemes", () => {
  assert.equal(safeSourceUrl("javascript:alert(1)"), null);
  assert.equal(safeSourceUrl("https://127.0.0.1/internal"), null);
  assert.equal(safeSourceUrl("https://localhost/internal"), null);
  assert.equal(safeSourceUrl("https://intranet.local/private"), null);
  assert.equal(safeSourceUrl("https://user:password@example.com"), null);
  assert.equal(safeSourceUrl("http://example.com"), null);
  assert.equal(safeSourceUrl("https://example.com/source"), "https://example.com/source");
});

test("public conversation POST sends no research without explicit opt-in", async () => {
  const { converse } = await import("../src/lib/pakistan.ts");
  const oldFetch = globalThis.fetch;
  let received;
  globalThis.fetch = async (url, opts) => {
    received = { url, opts };
    return { ok: true, json: async () => ({ results: [], needs_research: true, research_executed: false }) };
  };
  try {
    await converse(conversationPayload("session", "80k Lahore", false, {}));
    assert.equal(received.url, "/api/recommendations/converse/");
    assert.equal(JSON.parse(received.opts.body).research, false);
    assert.equal(JSON.parse(received.opts.body).guidance, false);
    assert.equal(received.opts.credentials, "same-origin");
  } finally { globalThis.fetch = oldFetch; }
});

test("rate limit 429 is shown as an error rather than a fabricated recommendation", async () => {
  const { converse } = await import("../src/lib/pakistan.ts");
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 429 });
  try {
    await assert.rejects(converse(conversationPayload("session", "Gaming phone", false, {})), /Too many requests/);
  } finally { globalThis.fetch = oldFetch; }
});

test("new chat deletes only the old opaque session", async () => {
  const { forgetConversation } = await import("../src/lib/pakistan.ts");
  const oldFetch = globalThis.fetch;
  let received;
  globalThis.fetch = async (url, opts) => { received = { url, opts }; return { ok: true, status: 204 }; };
  try {
    await forgetConversation("abc-123");
    assert.equal(received.url, "/api/recommendations/conversation/abc-123/");
    assert.equal(received.opts.method, "DELETE");
  } finally { globalThis.fetch = oldFetch; }
});
