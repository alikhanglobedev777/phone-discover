import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

for (const stylesheet of ["styles.css", "design-system.css"]) {
  test(`${stylesheet} contains no chromatic CSS colors`, () => {
    const css = readFileSync(new URL(`../src/${stylesheet}`, import.meta.url), "utf8");
    const hex = [...css.matchAll(/#([a-f\d]{6})\b/gi)];
    for (const match of hex) {
      const [red, green, blue] = match[1].match(/../g);
      assert.equal(red.toLowerCase(), green.toLowerCase(), `${stylesheet}: ${match[0]}`);
      assert.equal(green.toLowerCase(), blue.toLowerCase(), `${stylesheet}: ${match[0]}`);
    }
    const rgba = [...css.matchAll(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/gi)];
    for (const match of rgba) {
      assert.equal(match[1], match[2], `${stylesheet}: ${match[0]}`);
      assert.equal(match[2], match[3], `${stylesheet}: ${match[0]}`);
    }
  });
}

test("assistant uses white conversation and black reading text with burgundy controls", () => {
  const css = readFileSync(new URL("../src/brand-refresh.css", import.meta.url), "utf8");
  assert.match(css, /--wine:\s*#76253f/);
  assert.match(css, /\.chat-drawer\s*\{[^}]+background:\s*#fff/s);
  assert.match(css, /\.chat-drawer \.chat-stream\s*\{[^}]+background:\s*#fff/s);
  assert.match(css, /\.chat-drawer \.chat-bubble > p\s*\{[^}]+color:\s*#111/s);
  assert.match(css, /\.chat-drawer \.assistant-composer > div > button\s*\{[^}]+background:\s*var\(--wine\)/s);
});
