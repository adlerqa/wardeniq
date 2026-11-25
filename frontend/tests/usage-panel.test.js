import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(new URL("../src/features/usage/pages/UsagePage.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "neutral",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"],
  loader: { ".css": "empty" },
  logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

const USAGE = {
  totals: { total_tokens: 1234567, prompt_tokens: 1000000, completion_tokens: 234567, cost_usd: 0.4321 },
  by_model: {
    "qwen2.5:7b": { kind: "llm", calls: 12, prompt_tokens: 900000, completion_tokens: 200000, total_tokens: 1100000, cost_usd: 0, estimated: true },
    "gpt-4o <b>": { kind: "llm", calls: 3, total_tokens: 134567, cost_usd: 12.5 },
    nomic: { kind: "embed", calls: 1, total_tokens: 0, cost_usd: null },
  },
  by_project: [{ name: "Tour QA", total_tokens: 1000000, cost_usd: 0.4 }, { project_id: "p9", total_tokens: 200000 }],
  recent: [
    { label: "Generate tests", project_name: "Tour QA", feature_name: "Login <i>", status: "done", by_model: { "qwen2.5:7b": {}, nomic: {} }, total_tokens: 5000, cost_usd: 0.01 },
    { type: "analysis", project_id: "p9", status: "failed", by_model: {} },
  ],
};

function harness(t) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const state = { reply: () => [200, USAGE] };
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    requests.push(path);
    const [status, body] =
      path === "/api/usage" ? state.reply() : path === "/api/projects" ? [200, { projects: [{ name: "Zeta" }, { name: "Tour QA" }] }] : [200, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  window.toast = () => {};
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, clearTimeout,
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  const $ = (s) => container.querySelector(s);
  const flush = (fn) =>
    act(async () => {
      await fn?.();
      for (let i = 0; i < 6; i++) await settle();
    });
  const setValue = (el, v, ev) =>
    flush(() => {
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v);
      el.dispatchEvent(new window.Event(ev, { bubbles: true }));
    });
  const shown = (id) => [...container.querySelectorAll(`#${id} tr`)].slice(1).map((tr) => tr.style.display !== "none");
  return {
    $, state, requests, flush, setValue, shown,
    async open() {
      await act(async () => root.render(React.createElement(module.exports.default)));
      await flush(() => window.loadUsage());
    },
  };
}

test("registers window.loadUsage without fetching; renders cards, tables and filter options", async (t) => {
  const h = harness(t);
  await act(async () => {});
  assert.equal(h.requests.length, 0);
  await h.open();
  assert.deepEqual(h.requests, ["/api/usage", "/api/projects"]);
  assert.deepEqual([...h.$("#usage-totals").querySelectorAll(".usage-stat-value")].map((e) => e.textContent), ["1,234,567", "1,000,000", "234,567", "$0.4321"]);
  assert.equal(h.$("#usage-by-model tr:nth-child(2) td").textContent, "qwen2.5:7b ~est");
  assert.equal(h.$("#usage-by-model tr:nth-child(3) code").innerHTML, "gpt-4o &lt;b&gt;");
  assert.deepEqual([...h.$("#usage-model-filter").options].map((o) => o.value), ["", "qwen2.5:7b", "gpt-4o <b>", "nomic"]);
  assert.deepEqual([...h.$("#usage-project-filter").options].map((o) => o.value), ["", "Tour QA", "p9", "Zeta"]);
  assert.equal(h.$("#usage-recent tr:nth-child(3) td:nth-child(4)").innerHTML, '<span class="err">failed</span>');
});

test("filters hide rows and survive a refresh", async (t) => {
  const h = harness(t);
  await h.open();
  await h.setValue(h.$("#usage-recent-search"), "TOUR", "input");
  assert.deepEqual(h.shown("usage-recent"), [true, false]);
  await h.setValue(h.$("#usage-model-filter"), "nomic", "change");
  assert.deepEqual(h.shown("usage-by-model"), [false, false, true]);
  await h.setValue(h.$("#usage-project-filter"), "p9", "change");
  assert.deepEqual(h.shown("usage-by-project"), [false, true]);
  await h.flush(() => h.$("#usage-refresh").dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  assert.equal(h.$("#usage-model-filter").value, "nomic");
  assert.deepEqual(h.shown("usage-by-project"), [false, true]);
});

test("empty usage, then an error keeps the tables", async (t) => {
  const h = harness(t);
  h.state.reply = () => [200, { totals: {}, by_model: {}, by_project: [], recent: [] }];
  await h.open();
  assert.equal(h.$("#usage-recent").textContent, "No processes yet.");
  assert.equal(h.$("#usage-by-model").textContent, "No usage recorded yet — run a generation or analysis.");
  assert.equal(h.$("#usage-by-project").textContent, "—");
  h.state.reply = () => [500, { detail: "Usage down" }];
  await h.flush(() => window.loadUsage());
  assert.equal(h.$("#usage-totals").innerHTML, '<div class="err">Usage down</div>');
  assert.equal(h.$("#usage-recent").textContent, "No processes yet.");
});
