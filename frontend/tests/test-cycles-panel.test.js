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

const entry = fileURLToPath(new URL("../src/features/test-cycles/pages/TestCyclesPage.jsx", import.meta.url));
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

const item = (id, o = {}) => ({
  id,
  case_id: `case-${id}`,
  display_order: 1,
  title: `Case ${id}`,
  category: "api",
  priority: "High",
  execution_status: "pending",
  steps: [{ action: "Open", expected: "Shown" }],
  display_id: `TC-${id}`,
  ...o,
});
const DETAIL = {
  id: "cy1",
  project_id: "p1",
  name: "Sprint <b>12</b>",
  status: "active",
  description: "Retest",
  environment: "staging",
  build_version: "1.2",
  scheduled_start_at: "2026-11-20T00:00:00",
  scheduled_end_at: "2099-12-01T00:00:00",
  total: 3,
  counts: { passed: 1, failed: 1 },
  items: [
    item("i1", { execution_status: "passed" }),
    item("i2", { execution_status: "failed", actual_result: "Got 500", notes: "Flaky", defect_link: "https://bug/1" }),
    item("i3", { case_id: null, priority: null, steps: [] }),
  ],
};
const CYCLES = { cycles: [{ id: "cy1", name: "Sprint <b>12</b>", status: "active", total: 3, counts: { passed: 1, failed: 1 }, environment: "staging" }, { id: "cy2", name: "Empty", status: null, total: 0, counts: {} }] };
const TEMPLATES = { templates: [{ id: "t1", name: "Smoke", case_count: 12, description: "Core" }, { id: "t2", name: "Auth", case_count: 3 }] };

function harness(t, routes = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { toast: [], prompt: [], confirm: [], cc: [], info: [], newCase: [], editCase: [], project: [] };
  const answers = { prompt: [], confirm: true };
  Object.assign(window, {
    loadProjects: async () => {
      window.allProjects = [{ id: "p1", name: "Tour QA", repo_count: 0, feature_count: 1 }];
    },
    getCurrentProject: () => "p1",
    setCurrentProject: (p) => calls.project.push(p),
    toast: (m, e) => calls.toast.push([m, e === true]),
    uiPrompt: async (...a) => {
      calls.prompt.push(a);
      return answers.prompt.length ? answers.prompt.shift() : null;
    },
    uiConfirm: async (...a) => {
      calls.confirm.push(a);
      return answers.confirm;
    },
    openCaseConfirmation: (o) => calls.cc.push(o),
    openInfoDialog: (o) => calls.info.push(o),
    openNewCaseInCycle: (f, c) => calls.newCase.push([f, c]),
    editCase: (id) => calls.editCase.push(id),
  });
  delete window._cycle;
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    const method = opts.method || "GET";
    requests.push([method, path, opts.body ? JSON.parse(opts.body) : undefined]);
    const key = `${method} ${path}`;
    const [status, body] = routes[key]
      ? routes[key](opts)
      : key === "GET /api/projects/p1/test-cycles"
        ? [200, CYCLES]
        : key === "GET /api/projects/p1/cycle-templates"
          ? [200, TEMPLATES]
          : /^GET \/api\/test-cycles\/cy\d$/.test(key)
            ? [200, DETAIL]
            : [200, { ok: true }];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, { module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout });
  const root = createRoot(container);
  t.after(async () => {
    try {
      await act(async () => root.unmount());
    } catch {
      /* already unmounted */
    }
    container.remove();
  });
  const $ = (s) => container.querySelector(s);
  const flush = (fn) =>
    act(async () => {
      await fn?.();
      for (let i = 0; i < 8; i++) await settle();
    });
  const setter = (el) => Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set;
  return {
    $, calls, answers, requests, root, container, flush,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await this.mount();
      await flush(() => window.initTestCycles());
    },
    click: (el) => flush(() => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))),
    type: (el, v) =>
      flush(() => {
        setter(el).call(el, v);
        el.dispatchEvent(new window.Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
      }),
    select: (el, v) =>
      flush(() => {
        el.value = v;
        el.dispatchEvent(new window.Event("change", { bubbles: true }));
      }),
    btn: (txt, root = container) => [...root.querySelectorAll("button")].find((b) => b.textContent.trim() === txt),
    puts: (m, p) => requests.filter(([mm, pp]) => mm === m && pp === p).map(([, , b]) => b),
  };
}

test("registers window hooks without fetching; loads list and templates", async (t) => {
  const h = harness(t);
  await h.mount();
  for (const k of ["initTestCycles", "loadCycles", "openCycle"]) assert.equal(typeof window[k], "function", k);
  assert.equal(h.requests.length, 0);
  await h.flush(() => window.initTestCycles());
  assert.equal(h.$("#tcy-proj").value, "p1");
  const rows = h.container.querySelectorAll("#cyc-list .feat");
  assert.equal(rows[0].querySelector(".n").innerHTML, 'Sprint &lt;b&gt;12&lt;/b&gt; <span class="badge">active</span>');
  assert.equal(rows[0].querySelector(".pbar").style.width, "67%");
  assert.equal(rows[0].querySelector(".m").textContent, "2/3 executed · 1 passed · 1 failed · 0 skipped · 0 blocked · staging");
  assert.equal(rows[1].querySelector(".badge").textContent, "draft");
  const tpls = h.container.querySelectorAll("#cyc-templates .feat");
  assert.deepEqual([...tpls].map((x) => x.querySelector(".m").textContent), ["12 case(s) · Core", "3 case(s)"]);
  assert.equal(h.$("#cyc-detail-card").style.display, "none");
  await act(async () => h.root.unmount());
  for (const k of ["initTestCycles", "loadCycles", "openCycle"]) assert.equal(window[k], undefined, k);
});

test("empty and error list states", async (t) => {
  let mode = "empty";
  const h = harness(t, {
    "GET /api/projects/p1/test-cycles": () => (mode === "empty" ? [200, { cycles: [] }] : [500, { detail: "boom" }]),
    "GET /api/projects/p1/cycle-templates": () => [200, { templates: [] }],
  });
  await h.open();
  assert.equal(h.$("#cyc-list").textContent, "no cycles yet");
  assert.equal(h.$("#cyc-templates").textContent, "no templates yet — open a cycle and click “Save as template”");
  mode = "fail";
  await h.click(h.$("#tcy-refresh"));
  assert.equal(h.$("#cyc-list").innerHTML, '<div class="err">Couldn\'t load test cycles. boom</div>');
});

test("create a cycle: name required, trimmed, opens it", async (t) => {
  const h = harness(t, { "POST /api/test-cycles": () => [200, { id: "cy2" }] });
  await h.open();
  await h.click(h.$("#tcy-new"));
  assert.deepEqual(h.calls.toast.at(-1), ["Enter a cycle name", true]);
  await h.type(h.$("#tcy-name"), "  Sprint 13 ");
  await h.click(h.$("#tcy-new"));
  assert.deepEqual(h.puts("POST", "/api/test-cycles"), [{ project_id: "p1", name: "Sprint 13", case_ids: [] }]);
  assert.equal(h.$("#tcy-name").value, "");
  assert.equal(h.$("#cyc-detail-card").style.display, "block");
  assert.equal(window._cycle, "cy2");
});

test("cycle detail: header, summary, schedule, items and editors", async (t) => {
  const h = harness(t);
  await h.open();
  await h.click(h.container.querySelector("#cyc-list .feat"));
  assert.equal(h.$("#cyc-d-name").innerHTML, 'Sprint &lt;b&gt;12&lt;/b&gt; <span class="badge">active</span>');
  const d = h.$("#cyc-d-items");
  assert.equal(d.querySelector(".muted").textContent, "Retest · env staging · build 1.2");
  assert.deepEqual([...d.querySelectorAll(".cycle-detail-kpi")].map((k) => k.textContent), ["3Total cases", "1Passed", "1Failed", "0Blocked", "67%Progress"]);
  assert.equal(d.querySelector("a.export-btn").getAttribute("href"), "/api/test-cycles/cy1/export/csv");
  assert.equal(h.$("#cyc-start").value, "2026-11-20");
  assert.equal(h.$("#cyc-end").min, "2026-11-20");
  assert.equal(d.querySelector(".cycle-detail-actions + .cycle-detail-actions .badge").textContent, "Active");
  const items = d.querySelectorAll(".cycle-exec-item");
  assert.deepEqual([...items].map((i) => i.className), ["cycle-exec-item status-passed", "cycle-exec-item status-failed", "cycle-exec-item status-pending"]);
  assert.equal(items[0].querySelector(".cycle-exec-title").textContent, "TC-i1Case i1");
  assert.equal(items[0].querySelector(".case-steps-table").textContent, "#StepExpected result1.OpenShown");
  assert.ok(items[1].querySelector(".cycle-exec-editor"), "failed with saved details shows its editor");
  assert.equal(items[1].querySelector("textarea").value, "Got 500");
  assert.equal(items[2].querySelector(".case-steps-table"), null);
  assert.equal(h.btn("Edit case", items[2]), undefined);
  await h.click(h.btn("Edit case", items[0]));
  assert.deepEqual(h.calls.editCase, ["case-i1"]);
});

test("item status: direct save, failed opens the editor, cancel, save with details, error", async (t) => {
  let fail = false;
  const h = harness(t, { "PATCH /api/test-cycles/cy1/items": () => (fail ? [400, { detail: "nope" }] : [200, {}]) });
  await h.open();
  await h.click(h.container.querySelector("#cyc-list .feat"));
  const sel = (i) => h.container.querySelectorAll("#cyc-d-items .cycle-exec-status select")[i];
  await h.select(sel(0), "skipped");
  assert.deepEqual(h.puts("PATCH", "/api/test-cycles/cy1/items").at(-1), { item_id: "i1", status: "skipped", actual_result: "", notes: "", defect_link: "" });
  assert.deepEqual(h.calls.toast.at(-1), ["status updated", false]);
  await h.select(sel(2), "failed");
  const it2 = () => h.container.querySelectorAll("#cyc-d-items .cycle-exec-item")[2];
  assert.ok(it2().querySelector(".cycle-exec-editor"));
  assert.equal(it2().className, "cycle-exec-item status-failed");
  assert.equal(h.puts("PATCH", "/api/test-cycles/cy1/items").length, 1, "no save yet");
  await h.click(h.btn("Cancel", it2()));
  assert.equal(it2().querySelector(".cycle-exec-editor"), null);
  await h.select(sel(2), "blocked");
  await h.type(it2().querySelector("textarea"), "Env down");
  await h.click(h.btn("Save status", it2()));
  assert.deepEqual(h.puts("PATCH", "/api/test-cycles/cy1/items").at(-1), { item_id: "i3", status: "blocked", actual_result: "Env down", notes: "", defect_link: "" });
  // the editor open because of saved details saves them unchanged
  const it1 = h.container.querySelectorAll("#cyc-d-items .cycle-exec-item")[1];
  await h.click(h.btn("Save status", it1));
  assert.deepEqual(h.puts("PATCH", "/api/test-cycles/cy1/items").at(-1), {
    item_id: "i2", status: "failed", actual_result: "Got 500", notes: "Flaky", defect_link: "https://bug/1",
  });
  fail = true;
  await h.select(sel(0), "passed");
  assert.deepEqual(h.calls.toast.at(-1), ["nope", true]);
});

test("schedule, description, rename, report, delete, close", async (t) => {
  const h = harness(t, {
    "PATCH /api/test-cycles/cy1": (o) => [200, { ...DETAIL, ...JSON.parse(o.body) }],
    "GET /api/test-cycles/cy1/report": () => [200, { summary: { completion_rate: 60, pass_rate: 33, passed: 1, failed: 1, blocked: 0 } }],
  });
  await h.open();
  await h.click(h.container.querySelector("#cyc-list .feat"));
  await h.type(h.$("#cyc-end"), "2026-11-01");
  assert.deepEqual(h.calls.toast.at(-1), ["End date can't be before the start date", true]);
  assert.equal(h.puts("PATCH", "/api/test-cycles/cy1").length, 0);
  assert.equal(h.$("#cyc-end").value, "2099-12-01");
  await h.type(h.$("#cyc-start"), "");
  assert.deepEqual(h.puts("PATCH", "/api/test-cycles/cy1").at(-1), { scheduled_start_at: "" });
  assert.deepEqual(h.calls.toast.at(-1), ["Schedule cleared", false]);
  h.answers.prompt.push("New desc");
  await h.click(h.btn("Edit description"));
  assert.deepEqual(h.calls.prompt.at(-1), ["Edit cycle description", "Description", "Retest"]);
  assert.deepEqual(h.puts("PATCH", "/api/test-cycles/cy1").at(-1), { description: "New desc" });
  h.answers.prompt.push("  Renamed ");
  await h.click(h.$("#cyc-d-rename"));
  assert.deepEqual(h.puts("PATCH", "/api/test-cycles/cy1").at(-1), { name: "Renamed" });
  assert.deepEqual(h.calls.toast.at(-1), ["Cycle renamed", false]);
  await h.click(h.btn("View summary"));
  assert.equal(h.calls.info[0].title, "Cycle summary");
  assert.match(h.calls.info[0].summary, /<div class="cycle-detail-kpi"><b>60%<\/b><span>Completion<\/span><\/div>/);
  await h.click(h.$("#cyc-d-del"));
  const cc = h.calls.cc[0];
  assert.equal(cc.confirmLabel, "Delete cycle");
  assert.match(cc.summary, /^<b>Renamed<\/b><div class="muted" style="margin-top:6px">3 cases · 1 passed · 1 failed · 0 blocked<\/div>$/);
  await h.flush(() => cc.onConfirm());
  assert.equal(h.$("#cyc-detail-card").style.display, "none");
  assert.deepEqual(h.calls.toast.at(-1), ["Cycle deleted", false]);
  await h.click(h.container.querySelector("#cyc-list .feat"));
  await h.click(h.$("#cyc-d-close"));
  assert.equal(h.$("#cyc-detail-card").style.display, "none");
});

test("templates: save as, new cycle from, delete", async (t) => {
  const h = harness(t, { "POST /api/cycle-templates/t1/create-cycle": () => [200, { id: "cy2" }] });
  await h.open();
  await h.click(h.container.querySelector("#cyc-list .feat"));
  h.answers.prompt.push("   ");
  await h.click(h.btn("Save as template"));
  assert.deepEqual(h.calls.toast.at(-1), ["Name required", true]);
  h.answers.prompt.push("Reg pack");
  await h.click(h.btn("Save as template"));
  assert.deepEqual(h.puts("POST", "/api/test-cycles/cy1/save-template"), [{ name: "Reg pack" }]);
  await h.click(h.btn("New cycle", h.$("#cyc-templates")));
  assert.match(h.calls.prompt.at(-1)[2], /^Cycle /);
  assert.equal(h.puts("POST", "/api/cycle-templates/t1/create-cycle").length, 0, "cancelled");
  h.answers.prompt.push("From tpl");
  await h.click(h.btn("New cycle", h.$("#cyc-templates")));
  assert.deepEqual(h.puts("POST", "/api/cycle-templates/t1/create-cycle"), [{ name: "From tpl" }]);
  assert.equal(window._cycle, "cy2");
  await h.click(h.container.querySelectorAll("#cyc-templates .danger")[1]);
  assert.deepEqual(h.calls.confirm[0], ["Delete this template? Existing cycles are not affected.", "Delete template", "Delete", true]);
  assert.ok(h.requests.some(([m, p]) => m === "DELETE" && p === "/api/cycle-templates/t2"));
});

test("add cases: chooser, existing picker, new case feature picker", async (t) => {
  let feats = [{ id: "f1", name: "Reset" }, { id: "f2", name: "Login" }];
  const h = harness(t, {
    "GET /api/test-cases?project_id=p1&limit=500": () => [
      200,
      { items: [{ id: "case-i1", title: "In", type: "api" }, { id: "c10", title: "Expiry", type: "e2e", display_id: "TQ-10" }, { id: "c11", title: "Unknown", type: "api" }] },
    ],
    "GET /api/features?project_id=p1": () => [200, { features: feats }],
  });
  await h.open();
  await h.click(h.container.querySelector("#cyc-list .feat"));
  await h.click(h.btn("+ Add test cases"));
  assert.ok(document.querySelector("#acc-existing"));
  await h.click(document.querySelector("#acc-cancel"));
  assert.equal(document.querySelector("#acc-existing"), null);
  await h.click(h.btn("+ Add test cases"));
  await h.click(document.querySelector("#acc-existing"));
  const list = () => document.querySelector("#addcase-list");
  assert.deepEqual([...list().querySelectorAll(".addcase-chk")].map((c) => c.value), ["c10", "c11"]);
  await h.type(document.querySelector("#addcase-q"), "tq-");
  assert.deepEqual([...list().querySelectorAll(".addcase-chk")].map((c) => c.value), ["c10"]);
  await h.type(document.querySelector("#addcase-q"), "");
  await h.click(document.querySelector("#addcase-add"));
  assert.deepEqual(h.calls.toast.at(-1), ["Select at least one case", true]);
  list().querySelectorAll(".addcase-chk")[1].click();
  await h.click(document.querySelector("#addcase-add"));
  assert.deepEqual(h.puts("POST", "/api/test-cycles/cy1/items"), [{ case_ids: ["c11"] }]);
  assert.equal(document.querySelector("#addcase-list"), null);
  await h.click(h.btn("+ Add test cases"));
  await h.click(document.querySelector("#acc-new"));
  await h.select(document.querySelector("#ncf-feat"), "f2");
  await h.click(document.querySelector("#ncf-go"));
  assert.deepEqual(h.calls.newCase, [["f2", "cy1"]]);
  feats = [{ id: "f1", name: "Reset" }];
  await h.click(h.btn("+ Add test cases"));
  await h.click(document.querySelector("#acc-new"));
  assert.deepEqual(h.calls.newCase.at(-1), ["f1", "cy1"]);
  feats = [];
  await h.click(h.btn("+ Add test cases"));
  await h.click(document.querySelector("#acc-new"));
  assert.deepEqual(h.calls.toast.at(-1), ["Create a feature first — every test case must belong to a feature", true]);
});
