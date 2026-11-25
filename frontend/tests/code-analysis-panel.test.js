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

const entry = fileURLToPath(new URL("../src/features/code-analysis/pages/CodeAnalysisPage.jsx", import.meta.url));
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

const PROJECTS = [
  { id: "p1", name: "Tour QA", repo_count: 2, feature_count: 2 },
  { id: "p2", name: "Other", repo_count: 0, feature_count: 0 },
];
const REPOS = {
  repos: [
    { id: "r1", full_name: "o/backend", kind: "BE", default_branch: "main" },
    { id: "r2", full_name: "o/infra", kind: "infra", default_branch: "dev" },
  ],
};
const item = (i, extra = {}) => ({
  case_id: `c${i}`,
  display_id: `TQ-${i}`,
  title: `Case ${i} <b>x</b>`,
  type: "api",
  status: "matched",
  risk: "high",
  signal_type: "endpoint",
  signal: "/api/v1/reset",
  steps: [{ action: "Open", expected: "Shown" }],
  evidence: [{ file: "a.py", line: 4, sha: "abcdef123", repo: "o/backend", url: "https://gh/x" }, { file: "b.ts" }],
  ...extra,
});
const LATEST = {
  results: [item(0), item(1, { signal_type: "ai", signal: null, reason: "Related", evidence: [], steps: [] }), item(2)],
  commits: [{ repo: "o/backend", sha: "abc1234", url: "https://gh/c/1", message: "Fix <b>x</b>" }, { sha: "def5678", url: "u", message: "m" }],
};

function harness(t, routes = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { toast: [], project: [], job: null, cycles: 0 };
  Object.assign(window, {
    loadProjects: async () => {
      window.allProjects = PROJECTS;
    },
    getCurrentProject: () => "p1",
    setCurrentProject: (p) => calls.project.push(p),
    toast: (m, e) => calls.toast.push([m, !!e]),
    watchJob: (id, cb) => (calls.job = cb),
    loadCycles: () => calls.cycles++,
  });
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    const method = opts.method || "GET";
    requests.push([method, path, opts.body ? JSON.parse(opts.body) : undefined]);
    const key = Object.keys(routes).find((k) => k === `${method} ${path}`);
    const [status, body] = key
      ? routes[key](opts)
      : /\/repos\?repo_type=app$/.test(path)
        ? [200, REPOS]
        : /\/branches$/.test(path)
          ? path.includes("r1")
            ? [200, { default: "main", branches: ["main", "feature/x"] }]
            : [500, { detail: "no" }]
          : /commit-analysis\/latest$/.test(path)
            ? [200, LATEST]
            : path === "/api/analyze"
              ? [200, { job_id: "j1" }]
              : [200, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, clearTimeout,
  });
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
  return {
    $, calls, requests, flush, container,
    async open() {
      await act(async () => root.render(React.createElement(module.exports.default)));
      await flush(() => window.initCycles());
    },
    click: (el) => flush(() => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))),
    type: (el, value) =>
      flush(() => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        setter.call(el, value);
        el.dispatchEvent(new window.Event("input", { bubbles: true }));
      }),
  };
}

test("registers window hooks without fetching; loads projects, repos and the saved review", async (t) => {
  const h = harness(t);
  await act(async () => {});
  assert.equal(h.requests.length, 0);
  await h.open();
  assert.equal(typeof window.openCodeAnalysisFor, "function");
  assert.equal(h.$("#cyc-proj").value, "p1");
  assert.deepEqual(
    [...h.container.querySelectorAll(".cyc-repo-chk")].map((c) => [c.value, c.checked]),
    [["r1", true], ["r2", false]],
  );
  assert.deepEqual([...h.container.querySelectorAll(".cyc-repo-branch")[0].options].map((o) => o.textContent), ["main (default)", "feature/x"]);
  assert.equal(h.$("#cyc-status").innerHTML, '<span class="muted">↻ Restored the latest saved impact review · 3 impacted case(s)</span>');
  assert.equal(h.container.querySelectorAll("details.cycle-impact-item").length, 3);
  assert.match(h.$("#cyc-impacted").textContent, /2 direct evidence1 needs review3 impacted cases/);
  assert.match(h.$(".cycle-impact-title").innerHTML, /Case 0 &lt;b&gt;x&lt;\/b&gt;/);
  assert.equal(h.$(".cycles-commit-list summary").textContent, "2 commits reviewed as evidence");
  assert.equal(h.$("#cyc-create").style.display, "");
  assert.equal(h.$("#cyc-make").textContent, "Create cycle");
  assert.equal(h.$("#cyc-make").disabled, true);
});

test("lookback validation drives the analyze button", async (t) => {
  const h = harness(t);
  await h.open();
  for (const [v, disabled] of [["0", true], ["181", true], ["", true], ["1", false], ["180", false]]) {
    await h.type(h.$("#cyc-days"), v);
    assert.equal(h.$("#cyc-analyze").disabled, disabled, v);
    assert.equal(h.$("#cyc-analyze").title, disabled ? "Lookback must be between 1 and 180 days" : "");
  }
});

test("selection, select all and create cycle from selection", async (t) => {
  const h = harness(t);
  await h.open();
  const chks = () => [...h.container.querySelectorAll(".imp-chk")];
  await h.click(h.$("#imp-create-top"));
  assert.deepEqual(h.calls.toast.at(-1), ["Select at least one case", true]);
  await h.flush(() => chks()[2].click());
  await h.flush(() => chks()[0].click());
  assert.equal(h.$("#imp-selected-count").textContent, "2 selected");
  assert.equal(h.$("#cyc-make").textContent, "Create cycle (2)");
  await h.click(h.$("#cyc-make"));
  assert.deepEqual(h.calls.toast.at(-1), ["Enter a cycle name", true]);
  await h.type(h.$("#cyc-name"), "  Sprint 12 ");
  h.requests.length = 0;
  await h.click(h.$("#cyc-make"));
  assert.deepEqual(h.requests, [
    ["POST", "/api/test-cycles", { project_id: "p1", name: "Sprint 12", case_ids: ["c0", "c2"], source: { repo_ids: ["r1"], days: 14 } }],
  ]);
  assert.deepEqual(h.calls.toast.at(-1), ["Cycle created with 2 case(s) — see it under Test Cycles", false]);
  assert.equal(h.$("#cyc-name").value, "");
  assert.equal(h.calls.cycles, 1);
  await h.flush(() => h.$("#imp-select-all").click());
  assert.equal(h.$("#imp-selected-count").textContent, "3 selected");
  await h.flush(() => h.$("#imp-select-all").click());
  assert.equal(h.$("#imp-selected-count").textContent, "0 selected");
});

test("analyze: request body, statuses and results", async (t) => {
  const h = harness(t, { "POST /api/test-cycles": () => [409, { detail: "exists" }] });
  await h.open();
  await h.flush(() => h.container.querySelectorAll(".cyc-repo-chk").forEach((c) => c.checked || c.click()));
  const sel = h.container.querySelectorAll(".cyc-repo-branch")[0];
  await h.flush(() => {
    sel.value = "feature/x";
    sel.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
  await h.type(h.$("#cyc-days"), "30");
  h.requests.length = 0;
  await h.click(h.$("#cyc-analyze"));
  assert.deepEqual(h.requests, [
    ["POST", "/api/analyze", { project_id: "p1", repo_ids: ["r1", "r2"], branches: { r1: "feature/x" }, days: 30 }],
  ]);
  assert.equal(h.$("#cyc-status").textContent, "Starting change impact review for 2 repos…");
  assert.equal(h.$("#cyc-analyze").title, "Analysis in progress…");
  assert.equal(h.$("#cyc-impacted").innerHTML, "");
  assert.equal(h.$("#cyc-create").style.display, "none");
  await h.flush(() => h.calls.job({ status: "running", stage: "grounded matching", result: { commit_count: 3, changed_files: ["a"] } }));
  assert.equal(h.$("#cyc-status").textContent, "⏳ Matching changed code to impacted test cases… (3 commits, 1 files)");
  await h.flush(() => h.calls.job({ status: "done", result: { commit_count: 3, note: "n", impacted: [item(5)], grounded: 1 } }));
  assert.equal(h.$("#cyc-status").textContent, "Review complete · 3 commits · 0 files changed · n");
  assert.equal(h.$("#cyc-analyze").disabled, false);
  assert.equal(h.container.querySelectorAll(".imp-chk").length, 1);
  await h.flush(() => h.$(".imp-chk").click());
  await h.type(h.$("#cyc-name"), "X");
  await h.click(h.$("#cyc-make"));
  assert.deepEqual(h.calls.toast.at(-1), ["exists", true]);
  assert.equal(h.$("#cyc-name").value, "X");
  await h.click(h.$("#cyc-analyze"));
  await h.flush(() => h.calls.job({ status: "failed", error: "boom" }));
  assert.equal(h.$("#cyc-status").innerHTML, '<span class="err">Analysis failed: boom</span>');
  assert.match(h.$("#cyc-impacted").textContent, /No impacted test cases/);
  assert.equal(h.$("#cyc-create").style.display, "none");
});

test("no repo selected, POST error, no saved review, and opening from a Projects repo card", async (t) => {
  const h = harness(t, {
    "POST /api/analyze": () => [400, { detail: "No PAT" }],
    "GET /api/projects/p2/commit-analysis/latest": () => [200, { results: [] }],
  });
  await h.open();
  await h.flush(() => h.$(".cyc-repo-chk").click());
  await h.click(h.$("#cyc-analyze"));
  assert.deepEqual(h.calls.toast.at(-1), ["Select at least one repo", true]);
  await h.flush(() => h.$(".cyc-repo-chk").click());
  await h.click(h.$("#cyc-analyze"));
  assert.equal(h.$("#cyc-status").innerHTML, '<span class="err">No PAT</span>');
  assert.equal(h.$("#cyc-analyze").disabled, false);
  await h.flush(() => {
    const s = h.$("#cyc-proj");
    s.value = "p2";
    s.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
  assert.deepEqual(h.calls.project, ["p2"]);
  assert.equal(h.$("#cyc-status").textContent, "No saved impact analysis for this project yet — click Analyze changes.");
  assert.equal(h.$("#cyc-impacted").innerHTML, "");
  await h.flush(() => window.openCodeAnalysisFor("p1", "r2"));
  assert.equal(h.$("#cyc-proj").value, "p1");
  assert.deepEqual(
    [...h.container.querySelectorAll(".cyc-repo-chk")].map((c) => [c.value, c.checked]),
    [["r1", false], ["r2", true]],
  );
});
