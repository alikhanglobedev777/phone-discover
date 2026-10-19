import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const component = readFileSync(new URL("../src/components/PhoneDetail.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/detail-modal.css", import.meta.url), "utf8");
const entry = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

test("device detail overrides load after the burgundy design stylesheet", () => {
  assert.ok(entry.indexOf('import "./detail-modal.css";') > entry.indexOf('import "./brand-refresh.css";'));
});

test("detail dialog has a sticky close action and stays inside the viewport", () => {
  assert.match(component, /className="detail-modal-toolbar"/);
  assert.match(component, /aria-label="Close details"/);
  assert.match(css, /\.detail-modal-toolbar\s*\{[^}]*position:\s*sticky/s);
  assert.match(css, /\.detail-panel\s*\{[^}]*max-height:\s*calc\(100dvh - 32px\)[^}]*overflow-y:\s*auto/s);
});

test("device photos are contained and cannot cover the performance section", () => {
  assert.match(css, /\.detail-image-stage\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)[^}]*overflow:\s*hidden/s);
  assert.match(css, /\.detail-image-stage img\s*\{[^}]*min-height:\s*0[^}]*max-height:\s*100%[^}]*object-fit:\s*contain/s);
});

test("mobile detail dialog is full-screen and scrollable, above floating assistant", () => {
  assert.match(css, /\.detail-backdrop\s*\{[^}]*z-index:\s*120/s);
  assert.match(css, /@media \(max-width: 600px\)/);
  assert.match(css, /height:\s*100dvh/);
  assert.match(css, /overflow-wrap:\s*anywhere/);
});
