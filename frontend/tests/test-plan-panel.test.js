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

const entry = fileURLToPath(
  new URL("../src/features/test-plan/pages/TestPlanPage.jsx", import.meta.url),
);
const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "neutral",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"],
  logLevel: "silent",
});
const code = bundled.outputFiles[0].text;
const require = createRequire(import.meta.url);

const PLAN = {
  meta: { featureName: "Login", projectName: "Shop", featureVersionNumber: 2 },
  sections: [{ title: "Objective", type: "paragraph", content: "Verify sign-in." }],
};

function harness(t, routes, { feature = "f1" } = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const name = document.createElement("h2");
  name.id = "d-name";
  name.textContent = "Login";
  document.body.appendChild(name);
  for (const k of ["toast", "getCurrentFeatureId", "initTestPlan"]) delete window[k];
  window.getCurrentFeatureId = () => feature;
  window.toast = () => {};

  const requests = [];
  const streams = [];
  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.closed = false;
      this.listeners = {};
      streams.push(this);
    }
    addEventListener(type, fn) {
      (this.listeners[type] ||= []).push(fn);
    }
    close() {
      this.closed = true;
    }
    emit(type, data) {
      for (const fn of this.listeners[type] || [])
        fn({ data: data === undefined ? undefined : JSON.stringify(data) });
    }
  }
  async function fakeFetch(path, init = {}) {
    const method = init.method || "GET";
    requests.push(`${method} ${path}`);
    const handler = routes[`${method} ${path}`];
    const [status, body] = handler ? handler() : [404, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports, require, window, document, console,
    fetch: fakeFetch, EventSource: FakeEventSource, setTimeout, clearTimeout,
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
    name.remove();
  });
  const card = () => container.querySelectorAll(".card");
  return {
    container, requests, streams, root,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await act(async () => window.initTestPlan());
    },
    async emit(stream, type, data) {
      await act(async () => stream.emit(type, data));
    },
    text: () => container.textContent,
    workspace: () => [...card()].find((c) => c.querySelector("h2")?.textContent.endsWith("— Test Plan")),
    generate: () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Generate Test Plan"),
    links: () => [...container.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")]),
    async click(el) {
      await act(async () => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    },
  };
}

test("registers window.initTestPlan without fetching, and removes it on unmount", async (t) => {
  const h = harness(t, {});
  await h.mount();
  assert.equal(typeof window.initTestPlan, "function");
  assert.deepEqual(h.requests, []);
  assert.match(h.text(), /Please select a feature first to generate a test plan\./);
  await act(async () => h.root.unmount());
  assert.equal(window.initTestPlan, undefined);
});

test("no feature open keeps the empty state", async (t) => {
  const h = harness(t, {}, { feature: null });
  await h.mount();
  await h.open();
  assert.deepEqual(h.requests, []);
  assert.match(h.text(), /Please select a feature first/);
});

test("completed plan renders with export links and no Generate button", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/test-plan/latest": () => [200, { run: { id: "r1", status: "COMPLETED", content: PLAN } }],
  });
  await h.mount();
  await h.open();
  assert.ok(!/Please select a feature first/.test(h.text()));
  assert.equal(h.workspace().querySelector("h2").textContent, "Login — Test Plan");
  assert.match(h.text(), /Project: Shop · Version: 2/);
  assert.match(h.text(), /Verify sign-in\./);
  assert.equal(h.generate().hidden, true);
  assert.deepEqual(h.links(), [
    ["Export CSV", "/api/test-plan/runs/r1/export/csv"],
    ["Export PDF", "/api/test-plan/runs/r1/export/pdf"],
  ]);
});

test("no run yet: message and Generate; generate streams to completion", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/test-plan/latest": () => [200, { run: null }],
    "POST /api/features/f1/test-plan": () => [200, { runId: "r2", status: "PROCESSING" }],
  });
  await h.mount();
  await h.open();
  assert.match(h.text(), /No test plan generated yet\./);
  assert.equal(h.generate().hidden, false);
  assert.deepEqual(h.links(), []);

  await h.click(h.generate());
  assert.equal(h.streams.length, 1);
  assert.equal(h.streams[0].url, "/api/test-plan/runs/r2/stream");
  assert.match(h.text(), /Synthesizing test plan via LLM\.\.\./);
  assert.ok(h.container.querySelector('[role="status"][aria-label="Generating test plan"]'));

  await h.emit(h.streams[0], "status", { status: "PROCESSING" });
  assert.match(h.text(), /Synthesizing sections via LLM\.\.\./);

  await h.emit(h.streams[0], "status", { status: "COMPLETED", testPlan: PLAN });
  assert.equal(h.streams[0].closed, true);
  assert.match(h.text(), /Completed/);
  assert.match(h.text(), /Verify sign-in\./);
  assert.equal(h.links().length, 2);
});

test("failed generation and previous failure show errors with Generate", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/test-plan/latest": () => [200, { run: { id: "r3", status: "PROCESSING" } }],
  });
  await h.mount();
  await h.open();
  await h.emit(h.streams[0], "status", { status: "FAILED" });
  assert.match(h.text(), /Failed to generate test plan\./);
  assert.equal(h.generate().hidden, false);
  assert.equal(h.generate().disabled, false);

  const h2 = harness(t, {
    "GET /api/features/f1/test-plan/latest": () => [200, { run: { id: "r4", status: "FAILED" } }],
  });
  await h2.mount();
  await h2.open();
  assert.match(h2.text(), /Previous generation failed\./);
});

test("a lost stream re-checks after 2 seconds", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let calls = 0;
  const h = harness(t, {
    "GET /api/features/f1/test-plan/latest": () => {
      calls += 1;
      return [200, { run: { id: "r5", status: "PROCESSING" } }];
    },
  });
  await h.mount();
  await h.open();
  await h.emit(h.streams[0], "error");
  assert.equal(h.streams[0].closed, true);
  assert.match(h.text(), /Connection lost\. Re-checking\.\.\./);
  await act(async () => t.mock.timers.tick(2000));
  await act(async () => {});
  assert.equal(calls, 2);
  assert.equal(h.streams.length, 2);
});

test("load error is shown", async (t) => {
  const h = harness(t, {
    "GET /api/features/f1/test-plan/latest": () => [500, { detail: "db down" }],
  });
  await h.mount();
  await h.open();
  assert.match(h.text(), /db down/);
});
