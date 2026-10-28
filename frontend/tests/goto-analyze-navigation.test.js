import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// Regression tests for adlerqa/wardeniq#176 ("Analyze" on a repository
// leads nowhere): the repo list offered Analyze for test-type repos that
// Code Analysis can never select (it loads ?repo_type=app only), and
// gotoAnalyze hand-rolled its view switch, leaving the breadcrumb on
// Settings and the URL on #projects. The harness executes the real
// loadRepos/gotoAnalyze slices from 02-projects.js with stubbed DOM/API,
// following the pattern of the other compat controller tests.
// WQ_CONTROLLER_SRC overrides the controller path so the same tests can
// run against pristine code for a fail-before check.
const controllerPath =
  process.env.WQ_CONTROLLER_SRC ||
  new URL("../src/compat/runtime/controllers/02-projects.js", import.meta.url);
const source = readFileSync(controllerPath, "utf8");
const loadReposSrc = source.slice(
  source.indexOf("async function loadRepos()"),
  source.indexOf("window.gotoAnalyze"),
);
const gotoAnalyzeSrc = source.slice(
  source.indexOf("window.gotoAnalyze"),
  source.indexOf("window.delRepo"),
);

function harness(repos) {
  const nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, { hidden: false, textContent: "", value: "", innerHTML: "" });
    return nodes.get(selector);
  };
  const $ = (selector) => node(selector);
  const navButtons = [
    { dataset: { view: "projects" }, classList: { toggle() {} } },
    { dataset: { view: "cycles" }, classList: { toggle() {} } },
  ];
  const views = [
    { id: "view-projects", hidden: false },
    { id: "view-cycles", hidden: true },
  ];
  const checkboxes = [
    { value: "repo-app", checked: false },
    { value: "repo-test", checked: false },
  ];
  const calls = {
    history: [],
    storage: {},
    breadcrumbs: 0,
    loadCycles: 0,
    toasts: [],
  };
  const sandbox = {
    $,
    api: async () => ({ repos }),
    esc: (s) => String(s),
    repoKindClass: () => "be",
    repoKindLabel: (k) => k,
    document: {
      querySelectorAll: (sel) => {
        if (sel === "nav button") return navButtons;
        if (sel === ".view") return views;
        if (sel === ".cyc-repo-chk") return checkboxes;
        return [];
      },
    },
    history: {
      replaceState: (...args) => calls.history.push(args),
    },
    localStorage: {
      setItem: (k, v) => {
        calls.storage[k] = v;
      },
    },
    TITLES: { cycles: "Code Analysis" },
    currentProject: "proj-1",
    currentViewName: "projects",
    currentFeature: null,
    renderBreadcrumbs: () => {
      calls.breadcrumbs += 1;
    },
    loadProjects: async () => {},
    loadCycleRepos: async () => {},
    loadCycles: () => {
      calls.loadCycles += 1;
    },
    toast: (msg) => {
      calls.toasts.push(msg);
    },
    window: {},
    setTimeout: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(loadReposSrc, context);
  vm.runInContext(gotoAnalyzeSrc, context);
  return {
    context,
    calls,
    views,
    checkboxes,
    repoListHtml: () => node("#repo-list").innerHTML,
    gotoAnalyze: context.window.gotoAnalyze,
    loadRepos: () => context.loadRepos(),
  };
}

const REPOS = [
  { id: "repo-app", full_name: "org/app", kind: "BE", pr_count: 3, watch: true, repo_type: "app" },
  { id: "repo-test", full_name: "org/app-tests", kind: "test", pr_count: 0, watch: false, repo_type: "test" },
  { id: "repo-legacy", full_name: "org/legacy", kind: "BE", pr_count: 1, watch: false },
];

test("test-type repos get a disabled Analyze button, app and legacy repos keep a live one", async () => {
  const h = harness(REPOS);
  await h.loadRepos();
  const html = h.repoListHtml();
  assert.match(html, /gotoAnalyze\('repo-app','proj-1'\)/);
  assert.match(html, /gotoAnalyze\('repo-legacy','proj-1'\)/);
  assert.doesNotMatch(html, /gotoAnalyze\('repo-test'/);
  assert.match(html, /disabled title="Code Analysis covers app repos only">Analyze/);
});

test("gotoAnalyze updates the view name, URL hash, and saved nav state", async () => {
  const h = harness(REPOS);
  await h.gotoAnalyze("repo-app", "proj-1");
  assert.equal(h.context.currentViewName, "cycles");
  assert.equal(h.calls.breadcrumbs, 1);
  assert.deepEqual(h.calls.history, [[null, "", "#cycles"]]);
  assert.equal(JSON.parse(h.calls.storage.wq_nav).view, "cycles");
  assert.equal(JSON.parse(h.calls.storage.wq_nav).project, "proj-1");
  assert.equal(h.views.find((v) => v.id === "view-cycles").hidden, false);
  assert.equal(h.views.find((v) => v.id === "view-projects").hidden, true);
  assert.equal(h.checkboxes.find((c) => c.value === "repo-app").checked, true);
  assert.equal(h.checkboxes.find((c) => c.value === "repo-test").checked, false);
  assert.equal(h.calls.loadCycles, 1);
  assert.equal(h.calls.toasts[0], "Repo selected — set days & click Analyze changes");
});
