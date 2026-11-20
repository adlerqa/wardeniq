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

const entry = fileURLToPath(new URL("../src/features/step-library/pages/StepLibraryPage.jsx", import.meta.url));
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

const STEPS = [
  { id: "s1", action: "Then the response status is 200 OK", expected: "The API returns 200 OK.", used_in_cases: 4 },
  { id: "s2", action: "user opens the page", expected: "", used_in_cases: 0 },
];
const CASES = { items: [{ id: "c1", feature_id: "f1", display_id: "TQ-1", title: "Reset works" }] };

function harness(t, routes) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  for (const k of ["toast", "loadSteps", "openFeature", "navigateTo", "viewCase"]) delete window[k];
  const ui = [];
  window.toast = (...a) => ui.push(["toast", ...a]);
  const calls = [];
  window.openFeature = async (fid) => calls.push(["openFeature", fid]);
  window.navigateTo = (v) => calls.push(["navigateTo", v]);
  window.viewCase = (cid) => calls.push(["viewCase", cid]);
  const requests = [];
  async function fakeFetch(path, init = {}) {
    const method = init.method || "GET";
    requests.push({ method, path, body: init.body ? JSON.parse(init.body) : undefined });
    const handler = routes[`${method} ${path}`];
    const [status, body] = handler ? handler() : [404, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports, require, window, document, console,
    fetch: fakeFetch, setTimeout, clearTimeout,
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  return {
    container, requests, ui, calls, root,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await act(async () => window.loadSteps());
    },
    async click(el) {
      await act(async () => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    },
    async type(el, value) {
      const proto = el.tagName === "SELECT" ? window.HTMLSelectElement.prototype : el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
      await act(async () => el.dispatchEvent(new window.Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true })));
    },
    rows: () => [...container.querySelectorAll('[role="option"]')],
    button: (label) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === label || b.title === label),
    // The dialog is portalled to document.body.
    modal: () => document.querySelector(".step-modal-overlay"),
  };
}

const base = () => ({
  "GET /api/steps?limit=1000": () => [200, { steps: STEPS }],
  "GET /api/test-cases?step_id=s1&limit=200": () => [200, CASES],
});

test("registers window.loadSteps without fetching; removes it on unmount", async (t) => {
  const h = harness(t, base());
  await h.mount();
  assert.equal(typeof window.loadSteps, "function");
  assert.deepEqual(h.requests, []);
  await act(async () => h.root.unmount());
  assert.equal(window.loadSteps, undefined);
});

test("list rows, count, filters and empty state", async (t) => {
  const h = harness(t, base());
  await h.mount();
  await h.open();
  assert.match(h.container.textContent, /\(2\)/);
  const [r1, r2] = h.rows();
  assert.match(r1.textContent, /Thenthe response status is 200 OK/);
  assert.match(r1.textContent, /ExpectedThe API returns 200 OK\./);
  assert.match(r1.textContent, /4 cases/);
  assert.match(r2.textContent, /User opens the page/);
  assert.match(r2.textContent, /Unused/);

  await h.type(h.container.querySelector("#s-filter-usage"), "unused");
  assert.equal(h.rows().length, 1);
  await h.type(h.container.querySelector("#s-filter-usage"), "");
  await h.type(h.container.querySelector("#s-search"), "zzz");
  assert.equal(h.rows().length, 0);
  assert.match(h.container.textContent, /No matching steps/);
});

test("selecting a row opens the detail pane with the cases; Open goes to the case", async (t) => {
  const h = harness(t, base());
  await h.mount();
  await h.open();
  await h.click(h.rows()[0]);
  assert.equal(h.rows()[0].getAttribute("aria-selected"), "true");
  const pane = h.container.querySelector("aside");
  assert.match(pane.textContent, /THEN/);
  assert.match(pane.textContent, /the response status is 200 OK/);
  assert.match(pane.textContent, /Used in Cases \(1\)/);
  assert.match(pane.textContent, /TQ-1Reset works/);
  await h.click(h.button("Open ↗"));
  await act(async () => new Promise((r) => setTimeout(r, 350)));
  assert.deepEqual(h.calls, [["openFeature", "f1"], ["navigateTo", "features"], ["viewCase", "c1"]]);
  await h.click(h.button("Close details"));
  assert.equal(h.container.querySelector("aside"), null);
});

test("create: validation then POST; edit: warning, PATCH and update toast", async (t) => {
  const routes = base();
  routes["POST /api/steps"] = () => [200, { id: "s3" }];
  routes["PATCH /api/steps/s1"] = () => [200, { affected_cases: 4 }];
  const h = harness(t, routes);
  await h.mount();
  await h.open();

  await h.click(h.button("New step"));
  assert.match(h.modal().className, /\bshow\b/);
  assert.match(h.modal().textContent, /Create Step/);
  await h.click(h.button("Save step"));
  assert.deepEqual(h.ui.at(-1), ["toast", "Action / Description is required", true]);
  await h.type(document.querySelector("#step-modal-action"), " a user ");
  await h.click(h.button("Save step"));
  assert.deepEqual(h.requests.find((r) => r.method === "POST").body, { action: "Given a user", expected: "" });
  assert.deepEqual(h.ui.at(-1), ["toast", "Step created ✓", undefined]);
  assert.doesNotMatch(h.modal().className, /\bshow\b/);

  await h.click(h.button("Edit step"));
  assert.match(h.modal().textContent, /Edit Step/);
  assert.equal(document.querySelector("#step-modal-prefix").value, "Then");
  assert.match(h.modal().textContent, /referenced by 4 active testcase\(s\)/);
  await h.type(document.querySelector("#step-modal-expected"), "200 returned");
  await h.click(h.button("Save step"));
  assert.deepEqual(h.requests.find((r) => r.method === "PATCH").body, {
    action: "Then the response status is 200 OK",
    expected: "200 returned",
  });
  assert.deepEqual(h.ui.at(-1), ["toast", "Updated — affects 4 case(s) ✓", undefined]);
});

test("delete: blocked when used, deletes when unused", async (t) => {
  const routes = base();
  routes["DELETE /api/steps/s2"] = () => [200, { deleted: true }];
  const h = harness(t, routes);
  await h.mount();
  await h.open();
  const del = (row) => [...row.querySelectorAll("button")].find((b) => b.title === "Delete step");
  await h.click(del(h.rows()[0]));
  assert.deepEqual(h.ui.at(-1), ["toast", "Cannot delete: Step is referenced by 4 case(s).", true]);
  await h.click(del(h.rows()[1]));
  assert.equal(h.requests.at(-2).method, "DELETE");
  assert.deepEqual(h.ui.at(-1), ["toast", "Step deleted", undefined]);
});
