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

const entry = fileURLToPath(new URL("../src/features/projects/pages/ProjectsPage.jsx", import.meta.url));
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
  { id: "pA", name: "Alpha <b>x</b>", repo_count: 1, feature_count: 1 },
  { id: "pB", name: "Beta", repo_count: 2, feature_count: 0 },
];
const REPOS = [
  { id: "r1", full_name: "o/backend", kind: "BE", pr_count: 3, watch: true },
  { id: "r2", full_name: "o/web <i>", kind: "infra", pr_count: 0, watch: false },
];
const GIT = [
  { full_name: "o/backend", private: true, default_branch: "main" },
  { full_name: "o/web-app_ui", private: false, default_branch: "" },
];

function harness(t, routes = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { toast: [], project: [], synced: [], features: [], backbar: 0, status: 0, analyze: [], confirm: [], prompt: [], cc: [] };
  let current = "pA";
  const state = { promptAnswer: null };
  Object.assign(window, {
    getCurrentProject: () => current,
    setCurrentProject: (p) => {
      current = p;
      calls.project.push(p);
    },
    syncFeatureProjects: (list, cur) => calls.synced.push([list.length, cur]),
    openProjectFeatures: async (p) => calls.features.push(p),
    goToProjectFeatures: () => calls.features.push("goto"),
    updateBackbar: () => calls.backbar++,
    refreshStatus: () => calls.status++,
    gotoAnalyze: (rid, pid) => calls.analyze.push([rid, pid]),
    uiConfirm: async (...a) => {
      calls.confirm.push(a);
      return state.confirmAnswer;
    },
    toast: (m, o) => calls.toast.push([m, o === true ? "err" : (o && o.type) || "ok", o && o.title]),
    uiPrompt: async (...a) => {
      calls.prompt.push(a);
      return state.promptAnswer;
    },
    openCaseConfirmation: (o) => calls.cc.push(o),
  });
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    const method = opts.method || "GET";
    requests.push([method, path, opts.body ? JSON.parse(opts.body) : undefined, (opts.headers || {})["X-Provider-PAT"]]);
    const key = Object.keys(routes).find((k) => k === `${method} ${path}`);
    const [status, body] = key
      ? routes[key](opts)
      : path === "/api/projects" && method === "GET"
        ? [200, { projects: state.empty ? [] : PROJECTS }]
        : path === "/api/projects" && method === "POST"
          ? [200, { id: "pNew" }]
          : path.startsWith("/api/test-cases")
            ? [200, { total: 42 }]
            : path === "/api/atlassian/accessible-jira-projects"
              ? [200, { projects: [{ key: "WQ", name: "Warden" }, { key: "OLD", name: "Old", in_use: true }] }]
              : path === "/api/atlassian/accessible-confluence-spaces"
                ? [200, { spaces: [{ key: "SP", name: "Space" }] }]
                : path.startsWith("/api/git/accessible-repos")
                  ? [200, { repos: path.endsWith("page=1") ? GIT : [] }]
                  : path === "/api/sync/status"
                    ? [200, { poll_interval_s: 300, github_authenticated: true, ingested: 12, mapped: 9, errors: ["old", "boom <b>x</b>"], gitlab_host: "gitlab.acme.io" }]
                    : path.match(/^\/api\/projects\/[^/]+$/) && method === "GET"
                      ? [200, { id: "x", default_git_provider: state.provider || "github" }]
                      : path.match(/\/(github|gitlab)\/pat$/) && method === "GET"
                        ? [200, { configured: !!state.patOn }]
                        : path.match(/\/(github|gitlab)\/accessible-repos\?page=1$/)
                          ? [200, { repos: GIT }]
                          : path.match(/^\/api\/projects\/[^/]+\/repos$/) && method === "GET"
                            ? [200, { repos: state.noRepos ? [] : REPOS }]
                            : path.match(/^\/api\/projects\/[^/]+$/) && method === "DELETE"
                    ? [200, { features: 2, removed_orphan_cases: 3, preserved_shared_cases: 1 }]
                    : [200, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, clearTimeout, URL,
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
  const setValue = (el, v, ev = "input") =>
    flush(() => {
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v);
      el.dispatchEvent(new window.Event(ev, { bubbles: true }));
    });
  return {
    $, calls, requests, flush, container, state, setValue,
    async open() {
      await act(async () => root.render(React.createElement(module.exports.default)));
      await flush(() => window.loadProjects());
    },
    click: (el) => flush(() => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))),
  };
}

test("registers window hooks without fetching; loads cards, header and the Features screen picker", async (t) => {
  const h = harness(t);
  await act(async () => {});
  assert.equal(h.requests.length, 0);
  await h.open();
  for (const k of ["loadProjects", "showProjectList", "showProjectCreate", "openProjectSettings", "selectProject"])
    assert.equal(typeof window[k], "function", k);
  assert.equal(JSON.stringify(window.allProjects), JSON.stringify(PROJECTS));
  const cards = h.container.querySelectorAll("[data-project-card]");
  assert.equal(cards.length, 2);
  assert.equal(cards[0].querySelector(".entity-name").innerHTML, "Alpha &lt;b&gt;x&lt;/b&gt;");
  assert.equal(cards[1].querySelector(".entity-meta").textContent, "0 features · 2 repositories");
  assert.deepEqual(h.calls.synced, [[2, "pA"]]);
  assert.equal(h.$("#active-proj-title").textContent, "Alpha <b>x</b>");
  assert.equal(h.$("#active-proj-stats").textContent, "1 repositories · 1 features");
  assert.equal(h.$("#project-case-count").textContent, "42");
  assert.equal(h.requests.filter((r) => r[1].endsWith("/repos")).length, 0);
});

test("card click, menu toggling, outside click and Escape", async (t) => {
  const h = harness(t);
  await h.open();
  const card = (id) => h.$(`[data-project-card="${id}"]`);
  await h.click(card("pB").querySelector(".entity-name"));
  assert.deepEqual(h.calls.features, ["pB"]);
  await h.click(card("pB").querySelector(".entity-menu-btn"));
  assert.equal(card("pB").classList.contains("menu-open"), true);
  assert.deepEqual(h.calls.features, ["pB"]);
  await h.click(card("pA").querySelector(".entity-menu-btn"));
  assert.deepEqual([card("pA").classList.contains("menu-open"), card("pB").classList.contains("menu-open")], [true, false]);
  await h.click(card("pA").querySelector(".entity-menu-btn"));
  assert.equal(card("pA").classList.contains("menu-open"), false);
  await h.click(card("pA").querySelector(".entity-menu-btn"));
  await h.flush(() => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape" })));
  assert.equal(card("pA").classList.contains("menu-open"), false);
  await h.click(card("pA").querySelector(".entity-menu-btn"));
  await h.flush(() => document.body.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  assert.equal(card("pA").classList.contains("menu-open"), false);
});

test("empty list and the empty-state create button", async (t) => {
  const h = harness(t);
  h.state.empty = true;
  await h.open();
  assert.match(h.$("#project-cards-container").textContent, /No projects yet/);
  assert.deepEqual(h.calls.project, [""]);
  assert.equal(h.$("#project-case-count").textContent, "—");
  await h.click(h.$("#project-cards-container .go"));
  assert.equal(h.$("#proj-create-card").style.display, "block");
  assert.equal(h.$("#project-cards-container").style.display, "none");
  assert.equal(h.$("#project-list-toolbar").style.display, "none");
});

test("rename and delete from a card", async (t) => {
  const h = harness(t);
  await h.open();
  const menu = (id) => h.$(`[data-project-card="${id}"] .entity-menu`);
  await h.click(menu("pB").querySelectorAll("button")[1]);
  assert.deepEqual(h.calls.prompt[0], ["Rename project", "New name for the project", "Beta"]);
  assert.equal(h.requests.filter((r) => r[0] === "PATCH").length, 0);
  h.state.promptAnswer = "Renamed";
  await h.click(menu("pB").querySelectorAll("button")[1]);
  assert.deepEqual(h.requests.filter((r) => r[0] === "PATCH"), [["PATCH", "/api/projects/pB", { name: "Renamed" }, undefined]]);
  assert.deepEqual(h.calls.toast.at(-1), ["Project renamed", "ok", undefined]);
  await h.click(menu("pA").querySelectorAll("button")[2]);
  const cc = h.calls.cc[0];
  assert.equal(cc.summary, "<b>Alpha &lt;b&gt;x&lt;/b&gt;</b>");
  assert.equal(cc.confirmLabel, "Delete project");
  assert.equal(h.calls.project.at(-1), "pA");
  await h.flush(() => cc.onConfirm());
  assert.ok(h.requests.some((r) => r[0] === "DELETE" && r[1] === "/api/projects/pA"));
  assert.equal(h.calls.status, 1);
  assert.deepEqual(h.calls.toast.at(-1)[0], "Project deleted · 2 feature(s), 3 orphan test case(s) removed, 1 shared test case(s) preserved");
});

test("project settings: header, rename, delete, back and view features", async (t) => {
  const h = harness(t, { "PATCH /api/projects/pB": () => [400, { detail: "Rename failed" }] });
  await h.open();
  await h.flush(() => window.openProjectSettings("pB"));
  assert.equal(h.$("#project-list-page").hidden, true);
  assert.equal(h.$("#project-detail-page").hidden, false);
  assert.equal(h.$("#active-proj-title").textContent, "Beta");
  assert.ok(h.requests.some((r) => r[1] === "/api/projects/pB" && r[0] === "GET"));
  assert.ok(h.requests.some((r) => r[1] === "/api/projects/pB/repos"));
  assert.ok(h.calls.backbar > 0);
  h.state.promptAnswer = "B2";
  await h.click(h.$("#proj-rename-btn"));
  assert.deepEqual(h.calls.prompt.at(-1), ["Rename project", "New name for the project", "Beta"]);
  assert.deepEqual(h.calls.toast.at(-1), ["Rename failed", "err", "Couldn't rename project"]);
  await h.click(h.$("#proj-del-btn"));
  assert.equal(h.calls.cc.at(-1).summary, '<b>Beta</b><div class="muted" style="margin-top:6px">2 repositories · 0 features</div>');
  await h.click(h.$("#proj-features-btn"));
  assert.deepEqual(h.calls.features, ["goto"]);
  await h.click(h.$("#project-detail-back"));
  assert.equal(h.$("#project-list-page").hidden, false);
  assert.equal(h.$("#project-detail-page").hidden, true);
});

test("create wizard: reset, lists, repos, provider switch and create", async (t) => {
  const h = harness(t);
  await h.open();
  await h.click(h.$("#proj-new-btn"));
  assert.equal(h.$("#proj-create-card").style.display, "block");
  assert.deepEqual([...h.$("#new-proj-jira").options].map((o) => o.textContent), ["— none —", "WQ — Warden"]);
  assert.equal(h.$("#new-proj-jira-status").textContent, "1 project(s) available · 1 already linked");
  await h.click(h.$("#new-proj-load-repos"));
  assert.equal(h.$("#new-proj-pat-status").innerHTML, '<span class="err">Enter a PAT first</span>');
  await h.setValue(h.$("#new-proj-pat"), " ghp_k ");
  await h.click(h.$("#new-proj-load-repos"));
  assert.equal(h.$("#new-proj-pat-status").innerHTML, '<span class="ok">2 repos loaded</span>');
  assert.equal(h.requests.find((r) => r[1].startsWith("/api/git/"))[3], "ghp_k");
  await h.click(h.$('#new-proj-app-picker .cp-repo-add[data-fn="o/backend"]'));
  await h.click(h.$('#new-proj-test-picker .cp-repo-add[data-fn="o/web-app_ui"]'));
  assert.equal(h.$('#new-proj-test-picker .cp-repo-label-input').value, "web app ui");
  assert.equal(h.$("#new-proj-app-picker").querySelectorAll(".cp-repo-row").length, 1);
  assert.deepEqual([h.$("#new-proj-app-count").textContent, h.$("#new-proj-test-count").textContent], ["1", "1"]);
  await h.setValue(h.$('#new-proj-test-picker .cp-repo-kind-input'), "infra", "change");
  await h.click(h.$("#proj-create-save"));
  assert.equal(h.$("#new-proj-name-err").textContent, "Project name is required.");
  await h.setValue(h.$("#new-proj-name"), "  New ");
  await h.setValue(h.$("#new-proj-jira"), "WQ", "change");
  h.requests.length = 0;
  await h.click(h.$("#proj-create-save"));
  assert.deepEqual(
    h.requests.filter((r) => r[0] !== "GET").map((r) => [r[0], r[1], r[2]]),
    [
      ["POST", "/api/projects", { name: "New", description: "", jira_project_key: "WQ", jira_project_name: "Warden", confluence_space_key: null, confluence_space_name: null, default_git_provider: "github" }],
      ["PUT", "/api/projects/pNew/github/pat", { pat: "ghp_k" }],
      ["POST", "/api/projects/pNew/repos", { repo_full_name: "o/backend", label: "backend", repo_type: "app", git_provider: "github", kind: "BE" }],
      ["POST", "/api/projects/pNew/repos", { repo_full_name: "o/web-app_ui", label: "web app ui", repo_type: "test", git_provider: "github", kind: "infra" }],
    ],
  );
  assert.deepEqual(h.calls.toast.at(-1), ["Project created · 2 repo(s) connected", "ok", undefined]);
  assert.deepEqual(h.calls.features, ["pNew"]);
  assert.equal(h.$("#proj-create-status").textContent, "");
  assert.equal(h.$("#proj-create-save").disabled, false);
  await h.click(h.$("#proj-new-btn"));
  assert.equal(h.$("#new-proj-name").value, "");
  await h.click(h.$('.cp-prov[data-provider="gitlab"]'));
  assert.equal(h.$("#new-proj-pat").placeholder, "glpat-...");
});

test("create wizard: create error stays on the form", async (t) => {
  const h = harness(t, { "POST /api/projects": () => [400, { detail: "Name taken" }] });
  await h.open();
  await h.click(h.$("#proj-new-btn"));
  await h.setValue(h.$("#new-proj-name"), "X");
  await h.click(h.$("#proj-create-save"));
  assert.equal(h.$("#proj-create-status").innerHTML, '<span class="err">Name taken</span>');
  assert.equal(h.$("#proj-create-save").disabled, false);
  assert.equal(h.$("#proj-create-card").style.display, "block");
});

test("settings: provider from the project, PAT status, provider switch, save / clear PAT", async (t) => {
  const h = harness(t, { "DELETE /api/projects/pA/github/pat": () => [400, { detail: "nope" }] });
  h.state.provider = "gitlab";
  h.state.patOn = true;
  await h.open();
  await h.flush(() => window.openProjectSettings("pA"));
  const prov = () => [...h.container.querySelectorAll("[data-pd-provider]")].map((b) => b.classList.contains("active"));
  assert.deepEqual(prov(), [false, true]);
  assert.equal(h.$("#pd-pat").placeholder, "glpat-...");
  assert.equal(h.$("#pd-pat-status").innerHTML, '<span class="ok">GitLab PAT configured</span>');
  assert.ok(!h.requests.some((r) => r[0] === "PATCH"));
  h.state.patOn = false;
  h.requests.length = 0;
  await h.click(h.$('[data-pd-provider="github"]'));
  assert.deepEqual(h.requests.map((r) => [r[0], r[1], r[2]]), [
    ["PATCH", "/api/projects/pA", { default_git_provider: "github" }],
    ["GET", "/api/projects/pA/github/pat", undefined],
  ]);
  assert.equal(h.$("#pd-pat-status").innerHTML, '<span class="muted">No GitHub PAT set for this project</span>');
  await h.click(h.$("#pd-pat-save"));
  assert.deepEqual(h.calls.toast.at(-1), ["Enter a PAT first", "err", undefined]);
  await h.setValue(h.$("#pd-pat"), "  ghp_n  ");
  h.requests.length = 0;
  await h.click(h.$("#pd-pat-save"));
  assert.deepEqual(h.requests[0], ["PUT", "/api/projects/pA/github/pat", { pat: "ghp_n" }, undefined]);
  assert.equal(h.$("#pd-pat").value, "");
  assert.deepEqual(h.calls.toast.at(-1), ["PAT saved", "ok", undefined]);
  await h.click(h.$("#pd-pat-clear"));
  assert.deepEqual(h.calls.toast.at(-1), ["nope", "err", "Couldn't clear project token"]);
});

test("settings: repo list, actions, sync status and connect", async (t) => {
  const h = harness(t);
  h.state.confirmAnswer = false;
  await h.open();
  await h.flush(() => window.loadSyncStatus());
  assert.equal(h.$("#sync-status").innerHTML, 'poller every 300s · authenticated · ingested 12, mapped 9 · <span class="err">boom &lt;b&gt;x&lt;/b&gt;</span>');
  await h.flush(() => window.openProjectSettings("pA"));
  const cards = h.container.querySelectorAll("#repo-list .repo-item-card");
  assert.equal(cards.length, 2);
  assert.equal(cards[1].querySelector(".badge").textContent, "Infra");
  const btn = (i, label) => [...cards[i].querySelectorAll("button")].find((b) => b.textContent === label);
  await h.click(btn(0, "Analyze"));
  assert.deepEqual(h.calls.analyze, [["r1", "pA"]]);
  h.requests.length = 0;
  await h.click(btn(1, "Resume"));
  assert.deepEqual(h.requests.map((r) => [r[0], r[1], r[2]]), [["POST", "/api/repos/r2/watch", { watch: true }], ["GET", "/api/projects/pA/repos", undefined]]);
  await h.click(btn(0, "Remove"));
  assert.deepEqual(h.calls.confirm[0], ["Remove this repo and its tracked PRs?", "Delete Repository", "Remove", true]);
  h.requests.length = 0;
  await h.click(btn(0, "Sync"));
  assert.deepEqual(h.requests.map((r) => r[1]), ["/api/repos/r1/sync"]);
  assert.equal(h.$("#sync-status").textContent, "sync started…");
  await h.click(h.$("#repo-add"));
  await h.setValue(h.$("#repo-url"), " o/new ");
  await h.setValue(h.$("#repo-type"), "test", "change");
  h.requests.length = 0;
  await h.click(h.$("#repo-add"));
  assert.deepEqual(h.requests[0], ["POST", "/api/projects/pA/repos", { url: "o/new", kind: "BE", repo_type: "test", git_provider: "github" }, undefined]);
  assert.equal(h.$("#repo-url").value, "");
  assert.deepEqual(h.calls.toast.at(-1), ["Repo added & watching", "ok", undefined]);
  h.state.noRepos = true;
  await h.flush(() => window.loadProjects());
  assert.equal(h.$("#repo-list").innerHTML, '<span class="muted">no repos yet</span>');
});

test("settings: repository suggestions and provider from a pasted URL", async (t) => {
  const h = harness(t);
  await h.open();
  await h.flush(() => window.openProjectSettings("pA"));
  const box = () => h.$("#repo-url-suggest");
  await h.flush(() => h.$("#repo-url").dispatchEvent(new window.FocusEvent("focus")));
  assert.equal(box().hidden, true);
  await h.click(h.$("#repo-pick"));
  assert.equal(box().hidden, false);
  assert.equal(box().querySelectorAll(".repo-suggest-row").length, 2);
  await h.setValue(h.$("#repo-url"), "WEB");
  assert.deepEqual([...box().querySelectorAll(".repo-suggest-row")].map((r) => r.dataset.fullName), ["o/web-app_ui"]);
  await h.setValue(h.$("#repo-url"), "zzz");
  assert.equal(box().textContent, "No matches.");
  await h.click(h.$("#repo-url"));
  assert.equal(box().querySelectorAll(".repo-suggest-row").length, 2);
  await h.flush(() => box().querySelector(".repo-suggest-row").dispatchEvent(new window.MouseEvent("mousedown", { bubbles: true })));
  assert.equal(h.$("#repo-url").value, "o/backend");
  assert.equal(box().hidden, true);
  await h.click(h.$("#repo-url"));
  await h.flush(() => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape" })));
  assert.equal(box().hidden, true);
  await h.click(h.$("#repo-url"));
  await h.flush(() => document.body.dispatchEvent(new window.MouseEvent("mousedown", { bubbles: true })));
  assert.equal(box().hidden, true);
  h.requests.length = 0;
  await h.setValue(h.$("#repo-url"), "https://gitlab.acme.io/g/p");
  assert.deepEqual(h.requests.map((r) => [r[0], r[1]]), [
    ["GET", "/api/sync/status"],
    ["PATCH", "/api/projects/pA"],
    ["GET", "/api/projects/pA/gitlab/pat"],
  ]);
  assert.equal(h.$('[data-pd-provider="gitlab"]').classList.contains("active"), true);
  h.requests.length = 0;
  await h.setValue(h.$("#repo-url"), "git@github.com:o/r.git");
  assert.deepEqual(h.requests.map((r) => r[0] + " " + r[1]), ["PATCH /api/projects/pA", "GET /api/projects/pA/github/pat"]);
  h.requests.length = 0;
  await h.setValue(h.$("#repo-url"), "https://bitbucket.org/x");
  assert.equal(h.requests.length, 0);
});
