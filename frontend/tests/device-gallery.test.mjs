import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { galleryPhotos, photosForColor } from "../src/lib/deviceGallery.ts";

const base = { brand: { name: "Test" }, name: "Phone", primary_image_url: "https://example.org/front.jpg" };
const image = (id, view, color, image_url) => ({ id, image_url, alt_text: "", sort_order: id, is_primary: id === 1, view, color });

test("front, back, side images are deduplicated without inventing angles", () => {
  const photos = galleryPhotos({ ...base, images: [
    image(1, "front", 2, base.primary_image_url),
    image(2, "back", 2, "https://example.org/back.jpg"),
    image(3, "side", 2, "https://example.org/side.jpg"),
  ] });
  assert.deepEqual(photos.map(photo => photo.view), ["front", "back", "side"]);
  assert.equal(photos.length, 3);
});

test("chosen color filters photos; no cross-color photos substituted", () => {
  const photos = galleryPhotos({ ...base, images: [
    image(1, "front", 1, base.primary_image_url),
    image(2, "back", 1, "https://example.org/one-back.jpg"),
    image(3, "front", 2, "https://example.org/two-front.jpg"),
    image(4, "unspecified", null, "https://example.org/generic.jpg"),
  ] });
  assert.deepEqual(photosForColor(photos, 2).photos.map(p => p.url), ["https://example.org/two-front.jpg"]);
  const unavailable = photosForColor(photos, 3);
  assert.equal(unavailable.isRepresentative, true);
  assert.deepEqual(unavailable.photos.map(p => p.url), ["https://example.org/generic.jpg"]);
});

test("primary-only products stay single-image with unknown angle", () => {
  const photos = galleryPhotos({ ...base, images: [] });
  assert.equal(photos.length, 1);
  assert.equal(photos[0].view, "unspecified");
  assert.equal(photosForColor(photos, 2).isRepresentative, true);
});

test("gallery CSS loads after responsive modal sizing", () => {
  const entry = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
  assert.ok(entry.indexOf('import "./device-gallery.css";') > entry.indexOf('import "./detail-modal.css";'));
});
