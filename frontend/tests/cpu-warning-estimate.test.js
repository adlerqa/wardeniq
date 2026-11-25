import assert from "node:assert/strict";
import test from "node:test";

import { harness, makeFile, window } from "./features-harness.js";

// The pre-run cost estimate on the "New feature" page: asked even before a
// document is added (the server may warn that a local model runs on CPU), and
// both the cost note and the warning are shown as text, never as HTML.

test.after(() => window.close());

const WARNING = "This model runs on CPU only, so a full generation can take from about 20 minutes to over an hour.";
const local = (extra = {}) => ({ low: null, high: null, note: "Local Ollama model — no per-token cost.", accelerator: "cpu", warning: WARNING, ...extra });

async function openCreate(t, reply, routes) {
  const h = harness(t, routes);
  h.state.estimate = reply;
  await h.open();
  await h.flush(() => window.showFeatureCreate());
  return h;
}
const estimates = (h) => h.requests.filter((r) => r[1] === "/api/usage/estimate");
const el = (h) => h.$("#f-cost-estimate");

test("opening the create page asks for an estimate with nothing entered, and the warning shows", async (t) => {
  const h = await openCreate(t, local());
  assert.equal(estimates(h).at(-1)[2].text_length, 0);
  assert.match(el(h).innerHTML, /⚠ This model runs on CPU only/);
  assert.match(el(h).innerHTML, /color: var\(--amber\)/);
  assert.doesNotMatch(el(h).innerHTML, /Local Ollama model/); // the cost note needs a document
});

test("with a document the cost note and the warning both show", async (t) => {
  const h = await openCreate(t, local());
  await h.setValue(h.$("#f-text"), "x".repeat(4000));
  assert.equal(estimates(h).at(-1)[2].text_length, 4000);
  assert.match(el(h).innerHTML, /Local Ollama model/);
  assert.match(el(h).innerHTML, /⚠ This model runs on CPU only/);
});

test("file sizes count toward the estimate as before", async (t) => {
  const h = await openCreate(t, local());
  await h.setValue(h.$("#f-text"), "abc");
  await h.setFiles(h.$("#f-file"), [makeFile("a.pdf", 1500), makeFile("b.md", 500)]);
  assert.equal(estimates(h).at(-1)[2].text_length, 2003);
});

test("a model with no warning leaves nothing on the page until a document is added", async (t) => {
  const h = await openCreate(t, { low: null, high: null, note: "n", accelerator: "gpu" });
  assert.equal(el(h).innerHTML, "");
});

test("a hosted provider still shows its price range exactly as before", async (t) => {
  const h = await openCreate(t, { low: 0.5, high: 1.5, note: "Rough estimate" });
  await h.setValue(h.$("#f-text"), "x".repeat(4000));
  assert.equal(el(h).innerHTML, "Estimated cost: $0.5000–$1.50 (Rough estimate)");
});

test("the warning is escaped, not injected as HTML", async (t) => {
  const h = await openCreate(t, local({ warning: '<img src=x onerror="alert(1)">' }));
  assert.doesNotMatch(el(h).innerHTML, /<img src=x/);
  assert.match(el(h).innerHTML, /&lt;img src=x onerror="alert\(1\)"&gt;/);
});

test("the cost note is escaped too", async (t) => {
  const h = await openCreate(t, local({ warning: undefined, note: "<b>bold</b>" }));
  await h.setValue(h.$("#f-text"), "abc");
  assert.match(el(h).innerHTML, /&lt;b&gt;bold&lt;\/b&gt;/);
});

test("a failed estimate request leaves the page empty and does not throw", async (t) => {
  const h = await openCreate(t, local(), { "POST /api/usage/estimate": () => [503, { detail: "down" }] });
  await h.setValue(h.$("#f-text"), "abc");
  assert.equal(el(h).textContent, "");
});

test("reopening the create page clears an old estimate first", async (t) => {
  const h = await openCreate(t, { low: 0.5, high: 1.5, note: "Rough" });
  await h.setValue(h.$("#f-text"), "abc");
  assert.match(el(h).textContent, /Estimated cost/);
  h.state.estimate = { low: null, high: null, note: "n" };
  await h.flush(() => window.showFeatureCreate());
  assert.equal(el(h).textContent, "");
});
