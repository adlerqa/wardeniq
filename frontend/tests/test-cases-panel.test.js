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

const entry = fileURLToPath(new URL("../src/features/test-cases/pages/TestCasesPage.jsx", import.meta.url));
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

const PROJECTS = [
  { id: "p1", name: "Tour QA", repo_count: 0, feature_count: 1 },
  { id: "p2", name: "Other", repo_count: 2, feature_count: 0 },
];
const FEATURES = [{ id: "f1", name: "Password reset" }];
const CASES = [
  {
    id: "c1",
    display_id: "TC-1",
    title: "According to the PRD, user requests a reset link",
    type: "api",
    step_count: 3,
    priority: "High",
    execution_status: "passed",
    inherited: true,
    source_feature_name: "Login",
  },
  { id: "c2", title: "Expired link is rejected", type: "e2e", step_count: 1, priority: "Low", deprecated: true },
];
const HOOKS = ["initCases", "loadCases", "fillFeatFilter", "openTestCasesFor"];

function harness(t, routes = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  for (const k of HOOKS) delete window[k];
  const calls = { viewCase: [], setCaseResult: [], requestDeleteCase: [], updateCaseSelection: 0, loadProjects: 0 };
  window.loadProjects = async () => {
    calls.loadProjects++;
    window.allProjects = PROJECTS;
  };
  window.viewCase = (...a) => calls.viewCase.push(a);
  window.setCaseResult = (...a) => calls.setCaseResult.push(a);
  window.requestDeleteCase = (...a) => calls.requestDeleteCase.push(a);
  window.updateCaseSelection = () => calls.updateCaseSelection++;
  const requests = [];
  const respond = {
    "/api/tags": () => [200, { tags: ["smoke", "api-test"] }],
    "/api/features": () => [200, { features: FEATURES }],
    "/api/test-cases": () => [200, { items: CASES, total: 2 }],
    ...routes,
  };
  async function fakeFetch(path) {
    requests.push(path);
    const key = Object.keys(respond)
      .sort((a, b) => b.length - a.length)
      .find((k) => path.split("?")[0] === k);
    const [status, body] = respond[key](path);
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, URLSearchParams });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  const $ = (sel) => container.querySelector(sel);
  // Some handlers start a load without awaiting it (as the old screen did).
  const settle = () => new Promise((r) => setTimeout(r, 0));
  return {
    container, requests, root, calls, $, respond,
    caseRequests: () => requests.filter((r) => r.startsWith("/api/test-cases")),
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async run(fn) {
      await act(async () => {
        await fn();
        await settle();
      });
    },
    async select(id, value) {
      const el = $(`#${id}`);
      await act(async () => {
        el.value = value;
        el.dispatchEvent(new window.Event("change", { bubbles: true }));
        await settle();
      });
    },
    async type(id, value) {
      const el = $(`#${id}`);
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      await act(async () => {
        setter.call(el, value);
        el.dispatchEvent(new window.Event("input", { bubbles: true }));
      });
    },
    async click(el) {
      await act(async () => {
        el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        await settle();
      });
    },
  };
}

test("registers the window hooks without fetching; removes them on unmount", async (t) => {
  const h = harness(t);
  await h.mount();
  for (const k of HOOKS) assert.equal(typeof window[k], "function", k);
  assert.deepEqual(h.requests, []);
  assert.equal(h.$("#tc-list").textContent, "");
  await act(async () => h.root.unmount());
  for (const k of HOOKS) assert.equal(window[k], undefined, k);
});

test("initCases loads projects, tags, features and the first page", async (t) => {
  const h = harness(t);
  await h.mount();
  await h.run(() => window.initCases());
  assert.equal(h.calls.loadProjects, 1);
  assert.deepEqual(h.requests, ["/api/tags", "/api/features", "/api/test-cases?status=active&limit=25&skip=0"]);
  const opts = (id) => [...h.$(`#${id}`).options].map((o) => `${o.value}|${o.textContent}`);
  assert.deepEqual(opts("tc-proj"), ["|All projects", "p1|Tour QA — 0 repos · 1 features", "p2|Other — 2 repos · 0 features"]);
  assert.deepEqual(opts("tc-feat"), ["|All features", "f1|Password reset"]);
  assert.deepEqual(opts("tc-tag"), ["|Any tag", "smoke|smoke", "api-test|api-test"]);

  const rows = h.container.querySelectorAll(".testcase-item");
  assert.equal(rows.length, 2);
  assert.equal(rows[0].dataset.caseItem, "c1");
  assert.equal(rows[0].querySelector(".testcase-title").textContent, "TC-1User requests a reset linkInherited from Login");
  assert.equal(rows[0].querySelector(".testcase-sub").textContent, "API · 3 steps");
  assert.equal(rows[0].querySelector(".result-select").className, "result-select needs-editor passed");
  assert.equal(rows[0].querySelector(".result-select").value, "passed");
  assert.equal(rows[0].querySelector(".testcase-priority").textContent, "High");
  assert.equal(rows[1].style.opacity, "0.6");
  assert.equal(rows[1].querySelector(".testcase-sub").textContent, "End-to-end · 1 step · deprecated");
  assert.ok(rows[1].querySelector("[data-case-detail='c2']"));
  assert.equal(h.container.querySelector(".case-list-head .case-select-all").dataset.bulkScope, "cases");
  assert.equal(h.$("#tc-summary").textContent, "2 matching test cases");
  assert.equal(h.$("#tc-pager").textContent, "‹ Prev2 cases · page 1 of 1Next ›");
  assert.ok(h.$("#tcp").disabled && h.$("#tcn").disabled);
});

test("filters reload page 0; project reloads features and clears the feature", async (t) => {
  const h = harness(t);
  await h.mount();
  await h.run(() => window.initCases());
  await h.select("tc-feat", "f1");
  await h.select("tc-type", "api");
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?feature_id=f1&type=api&status=active&limit=25&skip=0");
  assert.equal(h.$("#tc-summary").textContent, "2 matching test cases · Password reset · API");
  await h.select("tc-proj", "p1");
  assert.equal(h.requests.at(-2), "/api/features?project_id=p1");
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?project_id=p1&type=api&status=active&limit=25&skip=0");
  assert.equal(h.$("#tc-feat").value, "");
  assert.equal(h.$("#tc-summary").textContent, "2 matching test cases · Tour QA — 0 repos · 1 features · API");

  await h.type("tc-q", " link ");
  assert.equal(h.caseRequests().length, 4, "typing alone does not search");
  await h.run(async () =>
    h.$("#tc-q").dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
  );
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?project_id=p1&type=api&q=link&status=active&limit=25&skip=0");
  await h.select("tc-status", "all");
  await h.select("tc-lineage", "inherited");
  await h.click(h.$("#tc-apply"));
  assert.match(h.$("#tc-summary").textContent, /lifecycle: all · lineage: Inherited \/ reused only · search contains “link”$/);

  await h.click(h.$("#tc-reset"));
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?status=active&limit=25&skip=0");
  assert.equal(h.requests.at(-2), "/api/features");
  for (const id of ["tc-proj", "tc-feat", "tc-type", "tc-tag", "tc-result", "tc-lineage", "tc-q"])
    assert.equal(h.$(`#${id}`).value, "", id);
  assert.equal(h.$("#tc-status").value, "active");
});

test("pager moves between pages", async (t) => {
  const h = harness(t, { "/api/test-cases": () => [200, { items: CASES, total: 60 }] });
  await h.mount();
  await h.run(() => window.initCases());
  assert.ok(h.$("#tcp").disabled);
  await h.click(h.$("#tcn"));
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?status=active&limit=25&skip=25");
  assert.equal(h.container.querySelector("#tc-pager .muted").textContent, "60 cases · page 2 of 3");
  await h.click(h.$("#tcn"));
  assert.ok(h.$("#tcn").disabled);
  await h.click(h.$("#tcp"));
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?status=active&limit=25&skip=25");
  await h.select("tc-type", "e2e");
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?type=e2e&status=active&limit=25&skip=0");
});

test("row actions: detail, result, selection, bulk bars and delete", async (t) => {
  const h = harness(t, {
    "/api/test-cases/c1": () => [200, { id: "c1", title: "Reset <b>", type: "api", priority: "High", tags: ["t"], steps: [{ action: "Go", expected: "" }], metadata: { expected_result: { status_code: 200 } } }],
    "/api/test-cases/c1/execution": () => [200, {}],
  });
  window.toast = () => {};
  await h.mount();
  await h.run(() => window.initCases());
  const item = h.container.querySelector("[data-case-item='c1']");
  const row = item.querySelector(".testcase-row");
  await h.click(row);
  assert.ok(item.classList.contains("open"));
  assert.match(item.querySelector("[data-case-detail='c1']").textContent, /Reset <b>.*Status code200.*1\.GoNo separate expected result/);
  await h.click(row.querySelector(".case-select"));
  await h.click(row.querySelector(".result-select"));
  assert.ok(item.classList.contains("open"), "checkbox and select do not toggle the case");
  assert.equal(h.$(".case-bulk-toolbar").className, "case-bulk-toolbar show");
  assert.equal(h.container.querySelector("[data-bulk-count='cases']").textContent, "1 selected");
  assert.equal(h.container.querySelector(".case-select-all").indeterminate, true);
  const sel = row.querySelector(".result-select");
  await act(async () => {
    sel.value = "failed";
    sel.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
  await h.run(async () => {});
  assert.ok(h.requests.includes("/api/test-cases/c1/execution"));
  assert.equal(sel.className, "result-select failed");
  await h.click(row.querySelector(".testcase-delete"));
  assert.deepEqual(h.calls.requestDeleteCase.map((a) => a[0]), ["c1"]);
  await h.click(item.querySelector("[data-case-detail='c1'] button.ghost:not(.needs-editor)"));
  assert.ok(!item.classList.contains("open"));
});

test("a reload remounts the rows (detail closed, boxes cleared)", async (t) => {
  const h = harness(t);
  await h.mount();
  await h.run(() => window.initCases());
  const item = h.container.querySelector("[data-case-item='c1']");
  item.classList.add("open");
  item.querySelector(".case-select").checked = true;
  await h.run(() => window.loadCases());
  const fresh = h.container.querySelector("[data-case-item='c1']");
  assert.notEqual(fresh, item);
  assert.ok(!fresh.classList.contains("open"));
  assert.equal(fresh.querySelector(".case-select").checked, false);
});

test("empty and error states; summary and pager keep their last values on error", async (t) => {
  let mode = "ok";
  const h = harness(t, {
    "/api/test-cases": () =>
      mode === "ok" ? [200, { items: CASES, total: 2 }] : mode === "empty" ? [200, { items: [], total: 0 }] : [500, { detail: "boom" }],
  });
  await h.mount();
  await h.run(() => window.initCases());
  mode = "fail";
  await h.run(() => window.loadCases());
  assert.equal(h.container.querySelector("#tc-list .empty-state h3").textContent, "Couldn't load test cases");
  assert.equal(h.container.querySelector("#tc-list .empty-state p").textContent, "boom");
  assert.equal(h.$("#tc-summary").textContent, "2 matching test cases");
  assert.match(h.$("#tc-pager").textContent, /2 cases · page 1 of 1/);
  mode = "empty";
  await h.click(h.container.querySelector("#tc-list .empty-state button"));
  assert.equal(h.$("#tc-list").textContent, "No test cases match the selected filters.");
  assert.equal(h.$("#tc-summary").textContent, "0 matching test cases");
});

test("openTestCasesFor scopes the list to a feature and keeps tc-feat readable", async (t) => {
  const h = harness(t);
  await h.mount();
  await h.run(() => window.initCases());
  await h.select("tc-type", "api");
  await h.select("tc-result", "failed");
  await h.run(() => window.openTestCasesFor("f1", "p1"));
  assert.equal(h.$("#tc-proj").value, "p1");
  assert.equal(h.$("#tc-feat").value, "f1");
  assert.equal(h.$("#tc-type").value, "");
  assert.equal(h.$("#tc-result").value, "");
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?project_id=p1&feature_id=f1&status=active&limit=25&skip=0");
  assert.equal(h.$("#tc-summary").textContent, "2 matching test cases · Tour QA — 0 repos · 1 features · Password reset");
});

test("opening the screen again resets project, feature and tag but keeps other filters", async (t) => {
  const h = harness(t);
  await h.mount();
  await h.run(() => window.initCases());
  await h.select("tc-proj", "p1");
  await h.select("tc-feat", "f1");
  await h.select("tc-tag", "smoke");
  await h.select("tc-type", "e2e");
  await h.select("tc-status", "deprecated");
  await h.run(() => window.initCases());
  assert.deepEqual(
    ["tc-proj", "tc-feat", "tc-tag", "tc-type", "tc-status"].map((id) => h.$(`#${id}`).value),
    ["", "", "", "e2e", "deprecated"],
  );
  assert.equal(h.caseRequests().at(-1), "/api/test-cases?type=e2e&status=deprecated&limit=25&skip=0");
});

test("bulk actions: results, export (needs a feature) and delete", async (t) => {
  const h = harness(t, {
    "/api/test-cases/c1/execution": () => [200, {}],
    "/api/test-cases/c2/execution": () => [200, {}],
    "/api/features/f1/test-cases/c1": () => [200, {}],
    "/api/features/f1/test-cases/c2": () => [200, {}],
  });
  const toasts = [];
  window.toast = (m, e) => toasts.push([m, !!e]);
  window.uiConfirm = async (...a) => {
    toasts.push(["confirm", a[0]]);
    return true;
  };
  await h.mount();
  await h.run(() => window.initCases());
  const bulk = (label) => [...h.container.querySelectorAll(".case-bulk-toolbar[data-bulk-scope='cases'] button")].find((b) => b.textContent.includes(label));
  await h.click(bulk("Pass"));
  assert.deepEqual(toasts.at(-1), ["Select test cases first", true]);
  await h.click(h.container.querySelector(".case-select-all"));
  assert.equal(h.container.querySelector("[data-bulk-count='cases-floating']").textContent, "2");
  await h.click(bulk("Pass"));
  assert.deepEqual(toasts.at(-1), ["2 test cases marked passed", false]);
  assert.deepEqual([...h.container.querySelectorAll(".result-select")].map((s) => s.className), [
    "result-select needs-editor passed",
    "result-select needs-editor passed",
  ]);
  await h.click(bulk("Export"));
  assert.deepEqual(toasts.at(-1), ["Choose one feature before exporting selected test cases", true]);
  await h.select("tc-feat", "f1");
  await h.click(h.container.querySelector(".case-select-all"));
  await h.click(bulk("Delete"));
  assert.match(toasts.at(-2)[1], /^Delete 2 selected test cases\?/);
  assert.deepEqual(toasts.at(-1), ["2 selected test cases removed", false]);
  assert.ok(h.requests.includes("/api/features/f1/test-cases/c2"));
});
