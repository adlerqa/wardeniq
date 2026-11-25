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

const entry = fileURLToPath(new URL("../src/features/mind-map/pages/MindMapPage.jsx", import.meta.url));
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
    { id: "r2", full_name: "o/infra", kind: "infra", default_branch: "" },
  ],
};
const MAP = {
  project_id: "p1",
  features: [
    {
      feature: "Password reset",
      feature_id: "f1",
      version: 2,
      case_count: 3,
      counts: { covered: 1, partial: 1, uncovered: 1 },
      cases: [
        { title: "Lockout", type: "api", status: "uncovered", display_id: "PR-3", files: [] },
        { title: "Send link <b>x</b>", type: "api", status: "covered", display_id: "PR-1", rationale: "Done.", files: ["a.py", "b.py"] },
        { title: "Strong pw", type: "functional", status: "partial", files: ["c.py"] },
      ],
      repos: ["o/backend", "o/web"],
      reviewed_files: ["a.py", "b.py", "c.py"],
      analyzed: true,
    },
    {
      feature: "Login",
      feature_id: "f2",
      version: 1,
      case_count: 2,
      counts: { covered: 0, partial: 0, uncovered: 2 },
      cases: [],
      repos: [],
      reviewed_files: ["x.py"],
      analyzed: true,
    },
    { feature: "Signup", feature_id: "f3", version: 1, case_count: 4, counts: { covered: 0, partial: 0, uncovered: 0 }, cases: [], repos: [], reviewed_files: [], analyzed: false },
  ],
  last_analysis: null,
};

function harness(t, routes = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { toast: [], graph: [], project: [], job: null };
  Object.assign(window, {
    loadProjects: async () => {
      window.allProjects = PROJECTS;
    },
    getCurrentProject: () => "p1",
    setCurrentProject: (p) => calls.project.push(p),
    setMindmapGraphData: (d) => calls.graph.push(d),
    toast: (m, e) => calls.toast.push([m, !!e]),
    watchJob: (id, cb) => (calls.job = cb),
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
            ? [200, { default: "main", branches: ["main", "dev"] }]
            : [500, { detail: "no" }]
          : /\/mindmap$/.test(path)
            ? [200, MAP]
            : [200, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout,
    clearTimeout, DOMPoint: class {},
  });
  const root = createRoot(container);
  t.after(async () => {
    try {
      await act(async () => root.unmount());
    } catch {
      /* already unmounted by the test */
    }
    container.remove();
    document.querySelectorAll("#gitrepo-list").forEach((n) => n.closest("div[style]")?.parentElement?.remove());
  });
  const $ = (s) => container.querySelector(s);
  const flush = (fn) =>
    act(async () => {
      await fn?.();
      for (let i = 0; i < 8; i++) await settle();
    });
  return {
    $, calls, requests, root, flush, container,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await this.mount();
      await flush(() => window.initMindmap());
    },
    click: (el) => flush(() => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))),
    change: (el, value) =>
      flush(() => {
        if (el.type === "checkbox") el.click();
        else {
          el.value = value;
          el.dispatchEvent(new window.Event("change", { bubbles: true }));
        }
      }),
  };
}

test("registers window.initMindmap without fetching; loads projects, repos and the map", async (t) => {
  const h = harness(t);
  await h.mount();
  assert.equal(typeof window.initMindmap, "function");
  assert.equal(h.requests.length, 0);
  await h.flush(() => window.initMindmap());
  assert.deepEqual(
    [...h.$("#mm-proj").options].map((o) => `${o.value}|${o.textContent}`),
    ["p1|Tour QA — 2 repos · 2 features", "p2|Other — 0 repos · 0 features"],
  );
  assert.equal(h.$("#mm-proj").value, "p1");
  const checks = [...h.container.querySelectorAll(".mm-repo-chk")].map((c) => `${c.value}:${c.checked}`);
  assert.deepEqual(checks, ["r1:true", "r2:false"]);
  assert.deepEqual(
    [...h.$(".mm-repo-branch[data-rid='r1']").options].map((o) => `${o.value}|${o.textContent}`),
    ["|main (default)", "dev|dev"],
  );
  assert.deepEqual([...h.$(".mm-repo-branch[data-rid='r2']").options].map((o) => o.textContent), ["default (default)"]);
  assert.equal(h.calls.graph.length, 1);
});

test("window.initMindmap is removed on unmount", async (t) => {
  const h = harness(t);
  await h.mount();
  await act(async () => h.root.unmount());
  assert.equal(window.initMindmap, undefined);
});

test("coverage list: summary, feature cards, cases sorted, warnings", async (t) => {
  const h = harness(t);
  await h.open();
  const map = h.$("#mm-map");
  assert.equal(map.querySelector(".mindmap-summary-head .mindmap-chip-row").textContent, "1 covered 1 partial 3 uncovered");
  assert.equal(map.querySelector(".mindmap-summary-card .mm-bar").title, "1 covered · 1 partial · 3 uncovered");
  const cards = map.querySelectorAll(".mindmap-feature-card");
  assert.deepEqual([...cards].map((c) => c.open), [true, true, false]);
  assert.equal(cards[0].querySelector(".mindmap-feature-title").textContent, "Password reset v2 ");
  assert.equal(cards[0].querySelector(".mindmap-feature-meta").textContent, "Reviewed against o/backend o/web");
  assert.deepEqual(
    [...cards[0].querySelectorAll(".mindmap-case-item .mm-dot")].map((d) => d.className),
    ["mm-dot covered", "mm-dot partial", "mm-dot uncovered"],
  );
  assert.equal(
    cards[0].querySelector(".mindmap-case-body").innerHTML,
    'Done.<br><span style="color: var(--accent2);">Files reviewed:</span> <code>a.py</code> <code>b.py</code>',
  );
  assert.match(cards[0].querySelector(".mindmap-case-title b").innerHTML, /Send link &lt;b&gt;x&lt;\/b&gt;/);
  assert.match(cards[1].querySelector(".warn").textContent, /^All 2 reviewed cases came back uncovered\. 1 implementation file was read/);
  assert.equal(cards[2].querySelector(".mindmap-feature-title .badge").textContent, "not analyzed");
  assert.equal(cards[2].querySelector(".mindmap-feature-body > .muted").textContent, "4 test cases — run analysis to map them to code.");
});

test("not analysed: explains the last analysis", async (t) => {
  const h = harness(t, {
    "GET /api/projects/p1/mindmap": () => [
      200,
      {
        project_id: "p1",
        features: [MAP.features[2]],
        last_analysis: { at: 0, features_mapped: 0, note: "No impl files", errors: ["e1", "e2"], per_repo: [{ repo: "o/x", error: "404" }] },
      },
    ],
  });
  await h.open();
  const reason = h.$(".mindmap-empty-reason");
  assert.equal(reason.querySelector(".sub").textContent, "Last analysis mapped 0 features.");
  assert.equal(reason.querySelector(".warn").textContent, "No impl files");
  assert.equal(reason.querySelector(".muted").innerHTML, "<code>o/x</code> (branch default) — fetch error: 404");
  assert.equal(reason.querySelector(".err").innerHTML, "e1<br>e2");
  assert.match(h.$(".mindmap-summary-card .sub").textContent, /Not analyzed yet/);
});

test("load error and no features", async (t) => {
  let mode = "fail";
  const h = harness(t, {
    "GET /api/projects/p1/mindmap": () => (mode === "fail" ? [500, { detail: "boom" }] : [200, { project_id: "p1", features: [] }]),
  });
  await h.open();
  assert.equal(h.$("#mm-map").innerHTML, '<div class="card err">Couldn\'t load the coverage map. boom</div>');
  assert.equal(h.calls.graph.length, 0);
  mode = "empty";
  await h.click(h.$("#mm-refresh"));
  assert.equal(h.$("#mm-map").textContent, "No features in this project yet.");
});

test("analyze: validation, request, progress, completion and failure", async (t) => {
  let fail = false;
  const h = harness(t, {
    "POST /api/code-analysis": () => (fail ? [400, { detail: "No PAT" }] : [200, { job_id: "j1" }]),
  });
  await h.open();
  await h.change(h.$(".mm-repo-chk[value='r1']"));
  await h.click(h.$("#mm-analyze"));
  assert.deepEqual(h.calls.toast.at(-1), ["Select at least one repo", true]);
  await h.change(h.$(".mm-repo-chk[value='r1']"));
  await h.change(h.$(".mm-repo-chk[value='r2']"));
  await h.change(h.$(".mm-repo-branch[data-rid='r1']"), "dev");
  await h.click(h.$("#mm-analyze"));
  assert.deepEqual(h.requests.find(([m]) => m === "POST")[2], {
    project_id: "p1", repo_ids: ["r1", "r2"], branches: { r1: "dev" },
  });
  assert.equal(h.$("#mm-status").textContent, "Starting implementation coverage review for 2 repos…");
  assert.ok(h.$("#mm-analyze").disabled);
  assert.equal(h.$("#mm-analyze").getAttribute("aria-busy"), "true");
  assert.equal(h.$("#mm-diag").innerHTML, "");
  assert.match(h.$("#mm-map").innerHTML, /aria-label="Analyzing code coverage"/);
  await h.flush(() => h.calls.job({ status: "running", stage: "reviewing — Login", result: { code_chunks: 9, features_mapped: 1 } }));
  assert.equal(
    h.$("#mm-status").innerHTML,
    '⏳ Reviewing coverage for Login… <span class="muted">· 9 implementation chunks indexed · 1 feature reviewed</span>',
  );
  const loads = h.requests.filter(([, p]) => p.endsWith("/mindmap")).length;
  await h.flush(() =>
    h.calls.job({ status: "succeeded", result: { code_chunks: 9, features_mapped: 1, note: "n <b>", errors: ["x"], per_repo: [{ repo: "o/backend", reused: true, impl_files: 3 }] } }),
  );
  assert.equal(
    h.$("#mm-status").innerHTML,
    'Review complete · 9 implementation chunks indexed · 1 feature reviewed · <span class="warn">n &lt;b&gt;</span> · <span class="err">1 repo issue(s)</span>',
  );
  assert.equal(h.$("#mm-analyze").disabled, false);
  assert.equal(h.$("#mm-analyze").getAttribute("aria-busy"), null);
  assert.equal(h.requests.filter(([, p]) => p.endsWith("/mindmap")).length, loads + 1);
  await h.click(h.$("#mm-analyze"));
  await h.flush(() => h.calls.job({ status: "failed", error: "died" }));
  assert.equal(h.$("#mm-status").innerHTML, '<span class="err">Analysis failed: died</span>');
  fail = true;
  await h.click(h.$("#mm-analyze"));
  assert.equal(h.$("#mm-status").innerHTML, '<span class="err">No PAT</span>');
  assert.equal(h.$("#mm-analyze").disabled, false);
});

test("project change selects it in the runtime and reloads", async (t) => {
  const h = harness(t);
  await h.open();
  const before = h.requests.length;
  await h.change(h.$("#mm-proj"), "p2");
  assert.deepEqual(h.calls.project, ["p2"]);
  const paths = h.requests.slice(before).map(([, p]) => p);
  assert.ok(paths.includes("/api/projects/p2/repos?repo_type=app"));
  assert.ok(paths.includes("/api/projects/p2/mindmap"));
});

test("GitHub repo picker: lists unconnected repos, filters, adds, reports skips", async (t) => {
  const page1 = { repos: Array.from({ length: 30 }, (_, i) => ({ full_name: `o/r${i}`, default_branch: "main", private: i === 0, language: i === 1 ? "Go" : null })) };
  const h = harness(t, {
    "GET /api/projects/p1/github/accessible-repos?page=1": () => [200, page1],
    "GET /api/projects/p1/github/accessible-repos?page=2": () => [200, { repos: [{ full_name: "o/backend" }, { full_name: "o/extra", default_branch: "trunk" }] }],
    "GET /api/projects/p1/repos": () => [200, REPOS],
    "POST /api/projects/p1/repos": (o) => (JSON.parse(o.body).repo_full_name === "o/r2" ? [409, { detail: "exists" }] : [200, {}]),
  });
  await h.open();
  await h.click(h.$("#mm-add-git"));
  const list = document.querySelector("#gitrepo-list");
  assert.equal(list.querySelectorAll(".gitrepo-chk").length, 31);
  assert.equal(list.querySelector("label").textContent, "o/r0private");
  await h.click(document.querySelector("#gitrepo-add"));
  assert.deepEqual(h.calls.toast.at(-1), ["Select at least one repo", true]);
  const q = document.querySelector("#gitrepo-q");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await h.flush(() => {
    setter.call(q, "zzz");
    q.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  assert.equal(document.querySelector("#gitrepo-list").textContent, "No matches.");
  await h.flush(() => {
    setter.call(q, "");
    q.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  const boxes = document.querySelectorAll(".gitrepo-chk");
  boxes[2].click();
  boxes[30].click();
  await h.click(document.querySelector("#gitrepo-add"));
  const posts = h.requests.filter(([m]) => m === "POST").map(([, , b]) => b);
  assert.deepEqual(posts, [
    { repo_full_name: "o/r2", default_branch: "main", repo_type: "app" },
    { repo_full_name: "o/extra", default_branch: "trunk", repo_type: "app" },
  ]);
  assert.deepEqual(h.calls.toast.at(-1), ["1 repo(s) added · 1 skipped (already added or inaccessible)", false]);
  assert.equal(document.querySelector("#gitrepo-list"), null);
});

test("GitHub repo picker: PAT error and nothing new", async (t) => {
  let mode = "fail";
  const h = harness(t, {
    "GET /api/projects/p1/github/accessible-repos?page=1": () =>
      mode === "fail" ? [401, { detail: "bad PAT" }] : [200, { repos: [{ full_name: "o/backend" }] }],
    "GET /api/projects/p1/repos": () => [200, REPOS],
  });
  await h.open();
  await h.click(h.$("#mm-add-git"));
  assert.deepEqual(h.calls.toast.at(-1), [
    "Couldn't list repos for this project (bad PAT). Check the project's GitHub PAT under Projects & Repos.",
    true,
  ]);
  mode = "none";
  await h.click(h.$("#mm-add-git"));
  assert.deepEqual(h.calls.toast.at(-1), ["No new repos to add — all your accessible repos are already in this project", true]);
  assert.equal(document.querySelector("#gitrepo-list"), null);
});
