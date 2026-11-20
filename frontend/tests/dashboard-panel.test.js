import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

// Create the DOM globals before react-dom loads (see api-tokens-panel.test.js).
const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(new URL("../src/features/dashboard/pages/DashboardPage.jsx", import.meta.url));
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
const code = bundled.outputFiles[0].text;
const require = createRequire(import.meta.url);

const DATA = {
  counts: { projects: 1, features: 2, test_cases: 10, test_steps: 18, documents: 1, repos: 2, pull_requests: 45 },
  coverage: { code_pct: 40, automation_pct: 120, covered_cases: 4, automated_cases: 0 },
  by_type: { functional: 2, api: 4 },
  projects: [{ id: "p1", name: "Tour QA", features: 1, test_cases: 10, code_pct: 40, automation_pct: 0, repos: 0, prs: 3 }],
};

function harness(t, respond) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  delete window.loadDashboard;
  const requests = [];
  async function fakeFetch(path) {
    requests.push(path);
    const [status, body] = respond();
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  return {
    container, requests, root,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await act(async () => window.loadDashboard());
    },
  };
}

test("registers window.loadDashboard without fetching; removes it on unmount", async (t) => {
  const h = harness(t, () => [200, DATA]);
  await h.mount();
  assert.equal(typeof window.loadDashboard, "function");
  assert.deepEqual(h.requests, []);
  await act(async () => h.root.unmount());
  assert.equal(window.loadDashboard, undefined);
});

test("renders tiles, coverage (clamped), types and projects", async (t) => {
  const h = harness(t, () => [200, DATA]);
  await h.mount();
  await h.open();
  const text = h.container.textContent;
  const values = [...h.container.querySelectorAll(".dashboard-metric-value")].map((e) => e.textContent);
  assert.deepEqual(values, ["1", "2", "10", "18", "1", "2", "45"]);
  assert.deepEqual(
    [...h.container.querySelectorAll(".dashboard-coverage-value")].map((e) => e.textContent),
    ["40%", "100%"],
  );
  assert.match(text, /4 covered/);
  assert.match(text, /10 total cases/);
  assert.match(text, /10 total/);
  assert.equal(h.container.querySelectorAll(".dashboard-type-row").length, 2);
  assert.equal(h.container.querySelector(".dashboard-type-fill").style.width, "50%");
  assert.match(text, /1 project(?!s)/);
  assert.match(h.container.querySelector(".dashboard-table tbody").textContent, /Tour QA.*40%.*0%/);
});

test("empty states", async (t) => {
  const h = harness(t, () => [200, { counts: {}, coverage: {}, by_type: {}, projects: [] }]);
  await h.mount();
  await h.open();
  assert.match(h.container.textContent, /No test case data yet/);
  assert.match(h.container.textContent, /Create your first project to see project metrics/);
  assert.match(h.container.textContent, /0 projects/);
});

test("error state with Retry", async (t) => {
  let fail = true;
  const h = harness(t, () => (fail ? [500, { detail: "db down" }] : [200, DATA]));
  await h.mount();
  await h.open();
  assert.match(h.container.textContent, /Could not load dashboard/);
  assert.match(h.container.textContent, /db down/);
  fail = false;
  await act(async () => h.container.querySelector(".dashboard-retry").dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  assert.equal(h.container.querySelectorAll(".dashboard-metric").length, 7);
});
