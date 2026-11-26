import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

import { ANALYZE_MESSAGES, brandLoader, brandTick } from "../src/lib/brandLoader.js";

test("analyze loader: size class, escaped steps / messages, first step active", () => {
  assert.match(brandLoader("analyze"), /^<div class="aql-root inline"/);
  assert.match(brandLoader("analyze", { compact: true }), /^<div class="aql-root compact"/);
  assert.match(brandLoader("analyze", { inline: false }), /^<div class="aql-root"/);
  const html = brandLoader(undefined, { steps: ["A <1>", "B"], messages: ["m <x>", "n"] });
  assert.match(html, /<span class="aql-stp active"><span class="aql-stp-dot"><\/span><span class="aql-stp-label">A &lt;1&gt;<\/span>/);
  assert.match(html, /<div class="aql-msg-pill">m &lt;x&gt;<\/div>/);
  assert.equal((html.match(/class="aql-card"/g) || []).length, 4);
  assert.match(brandLoader("analyze"), new RegExp(ANALYZE_MESSAGES[0]));
});

test("quiz loader: labels and steps", () => {
  const html = brandLoader("quiz", { compact: true, steps: ["x", "y", "z <w>"], questionLabel: "Q <2>", optionLabel: "O:" });
  assert.match(html, /^<div class="wql-root compact"/);
  assert.match(html, /z &lt;w&gt;<\/span>/);
  assert.match(html, /<div class="wql-qtitle">Q &lt;2&gt;<\/div>/);
  assert.match(brandLoader("quiz"), /Question 01/);
});

test("the ticker moves each loader's message and stepper", () => {
  const { window } = new JSDOM(`<body>${brandLoader("analyze", { messages: ["a", "b", "c", "d", "e", "f"] })}</body>`);
  const doc = window.document;
  const state = () => [doc.querySelector(".aql-msg").dataset.i, doc.querySelector(".aql-msg-pill").textContent,
    [...doc.querySelectorAll(".aql-stp")].map((s) => s.className).join("|")];
  brandTick(2, doc);
  assert.deepEqual(state(), ["2", "c", "aql-stp passed|aql-stp active|aql-stp"]);
  brandTick(5, doc);
  assert.deepEqual(state(), ["5", "f", "aql-stp passed|aql-stp passed|aql-stp active"]);
  brandTick(6, doc);
  assert.deepEqual(state(), ["0", "a", "aql-stp active|aql-stp|aql-stp"]);
  window.close();
});
