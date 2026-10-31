import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE = process.env.BROWSER_TEST_BASE_URL || "http://127.0.0.1:4173";
const PHONE_SLUG = "google-pixel-7a";
const evidence = {
  tier: "catalog_unverified", label: "Catalog specs not independently verified",
  last_verified_at: null, recent_reviewed_claims: 0, reviewed_claims: 0,
  source_links: [], caution: "Saved specs are not performance tests.",
};
const phone = {
  id: 1, slug: PHONE_SLUG, name: "Pixel 7a",
  brand: { id: 1, name: "Google", slug: "google", logo_url: "" },
  summary: "Catalog phone", status: "available", release_date: null,
  operating_system: "Android", primary_image_url: "", official_url: "",
  specifications: {}, specification_sections: [
    { id: 1, name: "Camera", slug: "camera", sort_order: 0,
      items: [{ id: 1, label: "Main camera", value: "Saved local camera specification", sort_order: 0 }] },
  ],
  images: [], colors: [], variants_count: 1, lowest_price: null, pakistan_prices: [],
  variants: [{
    id: 1, name: "8/128", ram_gb: 8, storage_gb: 128, chipset: "Catalog chipset",
    battery_mah: 4385, display_refresh_hz: 90,
    camera_score: "0", battery_score: "0", gaming_score: "0", offers: [],
  }],
};
const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
async function mockApi(page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/catalog/status/") return route.fulfill(json({
      catalog_status: "missing_prices", research_available: false,
      automatic_research: false, guidance_available: false,
      data_quality: {
        published_devices: 2220, published_variants: 4695,
        devices_recently_verified: 0, devices_with_official_link: 0,
        reviewed_source_claims: 0, variants_with_camera_editorial_score: 0,
        variants_with_gaming_editorial_score: 0,
        variants_with_battery_editorial_score: 0, caution: "Do not invent scores",
      },
    }));
    if (url.pathname === "/api/recommendations/converse/") {
      const request = JSON.parse(route.request().postData() || "{}");
      return route.fulfill(json({
        session_id: request.session_id, query_id: crypto.randomUUID(),
        memory_used: false, criteria: { brand: "google", device_query: "Pixel 7a", priorities: [] },
        explanation: "Google Pixel 7a is in the local catalog. Verified prices are unavailable.",
        results: [], count: 0, needs_research: false, specs_results: [], comparison: null,
        catalog_details: [{
          slug: PHONE_SLUG, name: "Pixel 7a", brand: "Google",
          summary: "Saved local phone facts", operating_system: "Android",
          primary_image_url: "", detail_api_url: "/api/catalog/devices/google-pixel-7a/",
          variants: [{ram_gb: 8, storage_gb: 128, chipset: "Catalog chipset",
                      battery_mah: 4385, display_refresh_hz: 90}],
          specification_sections: [{name:"Camera",items:[{label:"Main camera",value:"Saved local camera specification"}]}],
          evidence,
        }],
        research: {status:"not_requested",sources:[],notice:"",summary:""},
        guidance: {status:"not_requested",text:"",notice:""},
        price_references: {results:[],notice:"",unconfirmed_filters:[]},
      }));
    }
    if (url.pathname === "/api/catalog/devices/" + PHONE_SLUG + "/") return route.fulfill(json(phone));
    if (route.request().method() === "DELETE") return route.fulfill({status:204,body:""});
    if (url.pathname === "/api/catalog/brands/" || url.pathname === "/api/catalog/devices/")
      return route.fulfill(json({count:0,next:null,previous:null,results:[]}));
    return route.fulfill(json({count:0,next:null,previous:null,results:[]}));
  });
}

const browser = await chromium.launch({headless:true});
try {
  for (const size of [{width:1280,height:900},{width:375,height:812}]) {
    const context = await browser.newContext({viewport:size});
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await mockApi(page);
    await page.goto(BASE,{waitUntil:"domcontentloaded"});
    // Initial catalog queries may replace React's first launcher node during
    // hydration. Wait for it to stabilize before issuing a real click.
    await page.locator(".chat-launcher").waitFor({state:"visible"});
    await page.waitForTimeout(1200);
    await page.locator(".chat-launcher").click({force:true,timeout:10000});
    const dialog = page.getByRole("dialog",{name:/Phone Discover assistant/});
    await dialog.waitFor();
    await dialog.locator(".assistant-composer textarea").fill("Google Pixel 7a information");
    await dialog.getByRole("button",{name:/Send/i}).click();
    await dialog.getByRole("link",{name:"Pixel 7a",exact:true}).waitFor({timeout:15000});
    assert.ok(await dialog.getByText("Catalog specs not independently verified").count() > 0);
    assert.ok(await dialog.getByText("No independently reviewed source link is available.").count() > 0);
    const card = dialog.locator(".pk-result-card").filter({hasText:"Pixel 7a"});
    await card.getByRole("button",{name:"+ Compare"}).click();
    assert.match(page.url(),/compare=google-pixel-7a/);
    const bounds = await dialog.boundingBox();
    assert.ok(bounds,"Assistant dialog visible");
    assert.ok(bounds.x >= -2 && bounds.x + bounds.width <= size.width + 2,
      "Dialog exceeds viewport " + size.width);
    await card.getByRole("link",{name:"Pixel 7a",exact:true}).click();
    await page.getByRole("dialog",{name:/Pixel 7a/}).waitFor({timeout:15000});
    assert.match(page.url(),/device=google-pixel-7a/);
    assert.deepEqual(errors,[],"Browser errors at " + size.width);
    console.log("PASS: " + size.width + "px chat, source badge, compare and detail modal");
    await context.close();
  }
} finally {
  await browser.close();
}
