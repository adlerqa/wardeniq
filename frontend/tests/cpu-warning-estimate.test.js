import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// A local model on a CPU can take from about 20 minutes to over an hour (#249). The
// pre-run estimate endpoint now returns a `warning` for that case, and the Generate page
// must show it before any document is added and keep it out of the way otherwise. This runs
// the real 03-features-and-usage.js controller (same sandbox style as
// feature-upload-file-remove.test.js) with a stubbed `api`, and checks the rendered HTML.

const read = (name) =>
  readFileSync(new URL(`../src/compat/runtime/controllers/${name}`, import.meta.url), "utf8");

// The app's real escaper, not an approximation.
const core = read("00-core.js");
const escSource = core.slice(
  core.indexOf("const esc = (s) =>"),
  core.indexOf("const escAttr = esc;") + "const escAttr = esc;".length,
);
const source = read("03-features-and-usage.js").split("const FOCUS_TYPES")[0];

function harness(reply) {
  const nodes = new Map();
  const $ = (selector) => {
    if (!nodes.has(selector)) {
      nodes.set(selector, {
        hidden: false, textContent: "", innerHTML: "", value: "", files: [], style: {},
        addEventListener() {}, onclick: null, onchange: null,
      });
    }
    return nodes.get(selector);
  };
  const timers = [];
  const calls = [];
  const context = vm.createContext({
    $, window: {}, DataTransfer: class {}, console,
    setTimeout: (fn) => { timers.push(fn); return timers.length; }, clearTimeout() {},
    api: async (path, opts) => {
      calls.push({ path, body: opts && opts.body ? JSON.parse(opts.body) : null });
      if (reply instanceof Error) throw reply;
      return reply;
    },
    fmtUsd: (n) => `$${n}`, currentProject: "p1",
    loadFeatureTicketOptions: async () => {}, updateBackbar() {},
  });
  vm.runInContext(escSource, context);
  vm.runInContext(source, context);
  return { $, context, calls, timers, el: $("#f-cost-estimate") };
}

const WARNING = "This model runs on CPU only, so a full generation can take from about 20 minutes to over an hour.";
const local = (extra = {}) => ({
  low: null, high: null, note: "Local Ollama model — no per-token cost.",
  accelerator: "cpu", warning: WARNING, ...extra,
});

test("with no document yet the warning still shows, and no cost line does", async () => {
  const h = harness(local());
  await h.context.updateCostEstimate();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].body.text_length, 0);                 // asked even with nothing entered
  assert.match(h.el.innerHTML, /⚠ This model runs on CPU only/);
  assert.match(h.el.innerHTML, /color:var\(--amber\)/);
  assert.doesNotMatch(h.el.innerHTML, /Local Ollama model/);    // the cost note needs a document
});

test("with a document the cost note and the warning both show", async () => {
  const h = harness(local());
  h.$("#f-text").value = "x".repeat(4000);
  await h.context.updateCostEstimate();
  assert.equal(h.calls[0].body.text_length, 4000);
  assert.match(h.el.innerHTML, /Local Ollama model/);
  assert.match(h.el.innerHTML, /⚠ This model runs on CPU only/);
});

test("file sizes count toward the estimate as before", async () => {
  const h = harness(local());
  h.$("#f-file").files = [{ size: 1500 }, { size: 500 }];
  h.$("#f-text").value = "abc";
  await h.context.updateCostEstimate();
  assert.equal(h.calls[0].body.text_length, 2003);
});

test("a model with no warning leaves nothing on the page until a document is added", async () => {
  const h = harness({ low: null, high: null, note: "n", accelerator: "gpu" });
  await h.context.updateCostEstimate();
  assert.equal(h.el.innerHTML, "");
});

test("a hosted provider still shows its price range exactly as before", async () => {
  const h = harness({ low: 0.5, high: 1.5, note: "Rough estimate" });
  h.$("#f-text").value = "x".repeat(4000);
  await h.context.updateCostEstimate();
  assert.equal(h.el.innerHTML, "Estimated cost: $0.5–$1.5 (Rough estimate)");
  assert.doesNotMatch(h.el.innerHTML, /⚠/);
});

test("the warning is escaped, not injected as HTML", async () => {
  const h = harness(local({ warning: '<img src=x onerror="alert(1)">' }));
  await h.context.updateCostEstimate();
  assert.doesNotMatch(h.el.innerHTML, /<img src=x/);
  assert.match(h.el.innerHTML, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
});

test("the cost note is escaped too", async () => {
  const h = harness(local({ warning: undefined, note: "<b>bold</b>" }));
  h.$("#f-text").value = "abc";
  await h.context.updateCostEstimate();
  assert.match(h.el.innerHTML, /&lt;b&gt;bold&lt;\/b&gt;/);
});

test("a failed estimate request leaves the page empty and does not throw", async () => {
  const h = harness(new Error("503"));
  h.el.textContent = "stale";
  await h.context.updateCostEstimate();
  assert.equal(h.el.textContent, "");
});

test("opening the create page queues an estimate so the warning is there before Generate", async () => {
  const h = harness(local());
  await h.context.showFeatureCreate();
  assert.ok(h.timers.length >= 1, "an estimate must be scheduled when the page opens");
  h.timers.forEach((fn) => fn());                                // run what was scheduled
  await new Promise((r) => setImmediate(r));
  assert.equal(h.calls.at(-1).path, "/api/usage/estimate");
  assert.equal(h.calls.at(-1).body.text_length, 0);
  assert.match(h.el.innerHTML, /⚠ This model runs on CPU only/);
});

test("reopening the create page clears an old estimate first", async () => {
  const h = harness(local());
  h.el.innerHTML = "stale cost line";
  await h.context.showFeatureCreate();
  assert.equal(h.el.textContent, "");
});
