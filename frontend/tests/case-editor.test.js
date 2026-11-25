import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

import { deletePlan, editorBody, moveStep, reviewLine } from "../src/features/test-cases/lib/caseEditor.js";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(new URL("../src/components/overlays/modals/TestCaseEditorModal.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry], bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

const CASE = {
  id: "c1", title: "Login <b>", type: "api", priority: "P1", preconditions: "User", tags: ["smoke", "Auth"],
  shared_with_features: 2, display_id: "TQ-1",
  features: [{ id: "f1", name: "Login", origin: "reused" }, { id: "f2", name: "Other" }],
  steps: [
    { id: "s1", action: "Open", expected: "Shown", usage_count: 3 },
    { id: "s2", action: "Click", expected: "", usage_count: 1 },
  ],
};

async function mount(t, routes = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { toast: [], cc: [], win: [] };
  let feature = null;
  Object.assign(window, {
    getCurrentFeatureId: () => feature,
    toast: (m, e) => calls.toast.push([m, !!e]),
    openCaseConfirmation: (o) => calls.cc.push(o),
    openFeature: (f) => calls.win.push(["openFeature", f]),
    refreshStatus: () => calls.win.push(["refreshStatus"]),
    loadCases: () => calls.win.push(["loadCases"]),
    loadSteps: () => calls.win.push(["loadSteps"]),
  });
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    const method = opts.method || "GET";
    requests.push([method, path, opts.body ? JSON.parse(opts.body) : undefined]);
    const key = Object.keys(routes).find((k) => k === `${method} ${path}`);
    const [status, body] = key
      ? routes[key]()
      : method === "GET" && path === "/api/test-cases/c1"
        ? [200, CASE]
        : method === "PUT"
          ? [200, { steps: 2, other_cases_affected_by_step_edits: 1 }]
          : method === "POST" && path === "/api/test-cases"
            ? [200, { id: "cN", display_id: "TQ-9" }]
            : [200, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, { module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, clearTimeout });
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(module.exports.default)));
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
  const click = (el) => flush(() => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  const setValue = (el, v, ev = "input") =>
    flush(() => {
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v);
      el.dispatchEvent(new window.Event(ev, { bubbles: true }));
    });
  const steps = () => [...container.querySelectorAll("#m-steps .steprow")].map((r) => [...r.querySelectorAll("textarea")].map((x) => x.value));
  return { $, flush, click, setValue, steps, calls, requests, setFeature: (f) => (feature = f) };
}

test("helpers: body, review line, step move, delete plan", () => {
  const body = editorBody({ title: " T ", type: "e2e", prio: "Low", pre: " p ", tags: "A, b ,, C" }, [
    { id: "s1", action: "a", expected: "" },
    { action: "", expected: "" },
    { action: "n", expected: "x" },
  ]);
  assert.deepEqual(body, {
    title: "T", type: "e2e", priority: "Low", preconditions: "p", tags: ["a", "b", "c"],
    steps: [{ id: "s1", action: "a", expected: "" }, { action: "n", expected: "x" }],
  });
  assert.equal(reviewLine(body, 2), "End-to-end · Low · 2 steps · linked to 2 features");
  assert.deepEqual(moveStep(["a", "b", "c"], 2, 0), ["c", "a", "b"]);
  assert.equal(deletePlan(CASE, "f1").copy, "This removes “Login <b>” only from Login. Its 1 other feature link will stay intact.");
  assert.equal(deletePlan(CASE, "f1").secondaryLabel, "Delete everywhere");
  assert.equal(deletePlan(CASE, "zz").confirmLabel, "Delete from all features");
  assert.equal(deletePlan({ title: "S", shared_with_features: 1, features: [{ id: "f", name: "F" }] }, "f").secondaryLabel, null);
});

test("edit: loads the case, edits fields and steps, reviews and saves", async (t) => {
  const h = await mount(t);
  for (const k of ["editCase", "openNewCase", "openNewCaseInCycle", "requestDeleteCase"]) assert.equal(typeof window[k], "function", k);
  await h.flush(() => window.editCase("c1"));
  assert.equal(h.$("#modal").classList.contains("show"), true);
  assert.deepEqual([h.$("#m-heading").textContent, h.$("#m-title").value, h.$("#m-type").value, h.$("#m-prio").value, h.$("#m-tags").value], [
    "Edit test case", "Login <b>", "api", "High", "smoke, Auth",
  ]);
  assert.match(h.$("#m-warn").textContent, /^Linked to 2 features/);
  assert.equal(h.$("#m-del").style.display, "");
  assert.match(h.$("#m-steps .editor-shared-note").textContent, /shared by 3 testcases/);
  await h.setValue(h.$('#m-steps textarea[data-i="1"][data-f="expected"]'), "Clicked");
  await h.click(h.$("#m-addstep"));
  await h.setValue(h.$('#m-steps textarea[data-i="2"][data-f="action"]'), "New");
  await h.click(h.$('#m-steps .steprow[data-i="0"] .iconbtn'));
  assert.deepEqual(h.steps(), [["Click", "Clicked"], ["New", ""]]);
  await h.click(h.$("#m-save"));
  const cc = h.calls.cc[0];
  assert.equal(cc.title, "Confirm testcase update");
  assert.equal(cc.summary, '<div><b>Login &lt;b&gt;</b></div><div class="muted" style="margin-top:6px">API · High · 2 steps · linked to 2 features</div>');
  h.setFeature("f1");
  await h.flush(() => cc.onConfirm());
  assert.deepEqual(h.requests.at(-1), ["PUT", "/api/test-cases/c1", {
    title: "Login <b>", type: "api", priority: "High", preconditions: "User", tags: ["smoke", "auth"],
    steps: [{ id: "s2", action: "Click", expected: "Clicked" }, { action: "New", expected: "" }],
  }]);
  assert.equal(h.$("#m-msg").innerHTML, '<span class="ok">Saved 2 steps · 1 other case(s) updated via shared steps</span>');
  assert.deepEqual(h.calls.win, [["loadCases"], ["loadSteps"], ["openFeature", "f1"], ["refreshStatus"]]);
  await h.flush(() => new Promise((r) => setTimeout(r, 550)));
  assert.equal(h.$("#modal").classList.contains("show"), false);
});

test("new case in a cycle: create, then the cycle link fails", async (t) => {
  const h = await mount(t, { "POST /api/test-cycles/cy1/items": () => [409, { detail: "Duplicate" }] });
  await h.flush(() => window.openNewCaseInCycle("f9", "cy1"));
  assert.deepEqual([h.$("#m-heading").textContent, h.$("#m-tags").value, h.$("#m-del").style.display], ["Create test case (adds to this cycle)", "from-test-cycle", "none"]);
  await h.click(h.$("#m-save"));
  assert.equal(h.$("#m-msg").innerHTML, '<span class="err">Title is required.</span>');
  await h.setValue(h.$("#m-title"), "Cycle case");
  await h.click(h.$("#m-save"));
  assert.equal(h.calls.cc[0].confirmLabel, "Create testcase");
  await h.flush(() => h.calls.cc[0].onConfirm());
  assert.equal(h.requests[0][2].feature_id, "f9");
  assert.equal(h.$("#m-msg").innerHTML, '<span class="err">Created — TQ-9, but not added to this cycle: Duplicate</span>');
});

test("a failed save shows the error and rethrows for the dialog", async (t) => {
  const h = await mount(t, { "POST /api/test-cases": () => [400, { detail: "Post fail" }] });
  await h.flush(() => window.openNewCase("f1"));
  assert.equal(h.$("#m-warn").textContent, "The testcase will be linked to the selected feature.");
  await h.setValue(h.$("#m-title"), "P");
  await h.click(h.$("#m-save"));
  let thrown = null;
  await h.flush(async () => {
    try {
      await h.calls.cc[0].onConfirm();
    } catch (e) {
      thrown = e;
    }
  });
  assert.equal(thrown && thrown.message, "Post fail");
  assert.equal(h.$("#m-msg").innerHTML, '<span class="err">Post fail</span>');
  assert.equal(h.$("#m-save").disabled, false);
});

test("delete: feature-scoped remove with delete-everywhere, and global delete", async (t) => {
  const h = await mount(t);
  h.setFeature("f1");
  await h.flush(() => window.requestDeleteCase("c1"));
  const cc = h.calls.cc[0];
  assert.equal(cc.summary, '<b>TQ-1 Login &lt;b&gt;</b><div class="muted" style="margin-top:6px">Inherited / reused here · linked to 2 features</div>');
  assert.equal(cc.secondaryLabel, "Delete everywhere");
  await h.flush(() => cc.onSecondary());
  assert.deepEqual(h.requests.at(-1).slice(0, 2), ["DELETE", "/api/test-cases/c1?force=true"]);
  assert.deepEqual(h.calls.toast.at(-1), ["Testcase deleted from every feature", false]);
  h.setFeature(null);
  await h.flush(() => window.requestDeleteCase("c1"));
  const g = h.calls.cc[1];
  assert.equal(g.title, "Delete testcase");
  assert.equal(g.danger, true);
  await h.flush(() => g.onConfirm());
  assert.deepEqual(h.requests.at(-1).slice(0, 2), ["DELETE", "/api/test-cases/c1?force=true"]);
});
