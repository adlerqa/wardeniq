import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM(`<!doctype html><body>
  <nav><button data-view="dashboard" class="active"></button><button data-view="projects"></button><button data-view="cases"></button></nav>
  <section class="view" id="view-dashboard"></section><section class="view" id="view-projects" hidden></section>
  <section class="view" id="view-features" hidden><div id="feature-create-page" hidden></div></section>
  <section class="view" id="view-cases" hidden></section><section class="view" id="view-validator" hidden></section>
  <div id="project-detail-page" hidden></div><span id="features-page-title">Tour QA</span>
</body>`, { url: "http://localhost/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, history: dom.window.history, location: dom.window.location, localStorage: dom.window.localStorage });
test.after(() => dom.window.close());

const { nav, navFunctions, installNavGlobals } = await import("../src/app/navState.js");
const navigation = await import("../src/app/navigation.js");
const calls = [];
for (const n of ["loadDashboard", "showProjectList", "loadProjects", "loadSyncStatus", "loadFeatures", "openFeature", "showFeatureList", "initCases", "initValidator", "enforceViewerReadOnly"])
  dom.window[n] = (...a) => calls.push([n, ...a]);
const toasts = [];
dom.window.toast = (m) => toasts.push(m);
const $ = (s) => document.querySelector(s);

test("navigateTo: sidebar entry, visible view, title, loaders, #hash and wq_nav", () => {
  navFunctions.setCurrentProject("p1");
  navigation.navigateTo("features");
  assert.deepEqual([...document.querySelectorAll("nav button.active")].map((b) => b.dataset.view), ["projects"]);
  assert.deepEqual([...document.querySelectorAll(".view")].filter((v) => !v.hidden).map((v) => v.id), ["view-features"]);
  assert.equal(nav.get().title, "Features");
  assert.equal(location.hash, "#features");
  assert.deepEqual(JSON.parse(localStorage.getItem("wq_nav")), { view: "features", project: "p1", feature: null });
  assert.deepEqual(calls.filter((c) => c[0] !== "enforceViewerReadOnly"), [["loadProjects"], ["loadFeatures"], ["showFeatureList"]]);
  calls.length = 0;
  navFunctions.setCurrentFeature("f1");
  navigation.navigateTo("features");
  assert.ok(calls.some((c) => c[0] === "openFeature" && c[1] === "f1"));
});

test("back bar: project list, feature workspace, sub-screens, create page", () => {
  navFunctions.setCurrentFeature(null);
  navigation.navigateTo("features");
  let m = navigation.backbarModel();
  assert.deepEqual(m.crumbs.map((c) => [c.label, !!c.onClick]), [["Projects & Repos", true], ["Tour QA", false]]);
  navFunctions.setCurrentFeature("f1");
  navFunctions.setCurrentFeatureData({ name: "Login", test_cases: [1] });
  assert.deepEqual(nav.get().featureCases, [1]);
  navigation.navigateTo("validator");
  m = navigation.backbarModel();
  assert.equal(m.show, true);
  assert.deepEqual(m.crumbs.map((c) => c.label), ["Projects & Repos", "Tour QA", "Login", "Validator"]);
  calls.length = 0;
  m.onBack();
  assert.equal(nav.get().view, "features");
  $("#feature-create-page").hidden = false;
  assert.deepEqual(navigation.backbarModel().crumbs.map((c) => c.label), ["Projects & Repos", "Tour QA", "Create feature"]);
  $("#feature-create-page").hidden = true;
  navigation.navigateTo("dashboard");
  assert.equal(navigation.backbarModel().show, false);
});

test("breadcrumb steps need a project / feature; compat globals read the same state", () => {
  navFunctions.setCurrentProject(null);
  navigation.clickBreadcrumb("features");
  navFunctions.setCurrentProject("p2");
  navFunctions.setCurrentFeature(null);
  navigation.clickBreadcrumb("workspace");
  assert.deepEqual(toasts, ["Please select a project first.", "Please select a feature first."]);
  const win = {};
  const off = installNavGlobals(win);
  assert.equal(win.currentProject, "p2");
  win.currentFeature = "f9";
  assert.equal(navFunctions.getCurrentFeatureId(), "f9");
  win.currentFeatureData = { name: "X", test_cases: [2, 3] };
  assert.deepEqual(win.currentFeatureCases, [2, 3]);
  off();
  assert.equal("currentProject" in win, false);
});
