import assert from "node:assert/strict";
import test from "node:test";

import {
  CHECKLIST_TO_CHAPTER,
  STEPS,
  buildTour,
  isActionStep,
  keyAction,
  popoverPosition,
  resolveText,
  tourProgress,
} from "../src/features/onboarding/tourSteps.js";
import {
  _resetTourForTests,
  beginTour,
  endTour,
  getTourState,
  nextStep,
  previousStep,
  requestTour,
  subscribeTour,
} from "../src/features/onboarding/tourStore.js";

const FRESH = {
  llm_configured: false,
  has_project: false,
  has_repo: false,
  has_feature: false,
  has_test_cases: false,
};
const chapters = (steps) => [...new Set(steps.map((s) => s.chapter))];

test("every step has an id, chapter, title and body, and ids are unique", () => {
  const ids = new Set();
  for (const s of STEPS) {
    assert.ok(s.id && s.chapter && s.title && s.body, `incomplete step ${s.id}`);
    assert.ok(!ids.has(s.id), `duplicate id ${s.id}`);
    ids.add(s.id);
  }
});

test("admin on a fresh install gets every chapter in order", () => {
  const steps = buildTour({ role: "admin", setup: FRESH });
  assert.deepEqual(chapters(steps), ["welcome", "llm", "project", "generate", "results", "repo", "explore"]);
});

test("a working LLM skips the AI-model chapter", () => {
  const steps = buildTour({ role: "admin", setup: { ...FRESH, llm_configured: true } });
  assert.ok(!chapters(steps).includes("llm"));
});

test("editors never get the AI-model chapter (Configuration is admin-only)", () => {
  const steps = buildTour({ role: "editor", setup: FRESH });
  assert.deepEqual(chapters(steps), ["welcome", "project", "generate", "results", "repo", "explore"]);
});

test("viewers get a read-only tour: welcome and explore, including Projects", () => {
  const steps = buildTour({ role: "viewer", setup: FRESH });
  assert.deepEqual(chapters(steps), ["welcome", "explore"]);
  assert.ok(steps.some((s) => s.id === "explore-projects"));
  assert.ok(!steps.some((s) => s.advanceOnClick || (s.waitFor && s.chapter !== "explore")));
});

test("finished steps drop out: with everything done only welcome, results and explore remain", () => {
  const done = { llm_configured: true, has_project: true, has_repo: true, has_feature: true, has_test_cases: true };
  assert.deepEqual(chapters(buildTour({ role: "admin", setup: done })), ["welcome", "results", "explore"]);
});

test("Show me starts at that chapter, skips welcome, and continues with later chapters", () => {
  const steps = buildTour({ role: "admin", setup: { ...FRESH, llm_configured: true }, startChapter: "project" });
  assert.equal(steps[0].id, "project-new");
  assert.deepEqual(chapters(steps), ["project", "generate", "results", "repo", "explore"]);
});

test("Show me on the optional repo step works even though later chapters are fine", () => {
  const steps = buildTour({ role: "editor", setup: { ...FRESH, llm_configured: true, has_project: true, has_test_cases: true, has_feature: true }, startChapter: "repo" });
  assert.deepEqual(chapters(steps), ["repo", "explore"]);
});

test("unknown start chapter gives no steps; every checklist step maps to a chapter", () => {
  assert.deepEqual(buildTour({ role: "admin", setup: FRESH, startChapter: "nope" }), []);
  for (const chapter of Object.values(CHECKLIST_TO_CHAPTER)) {
    assert.ok(buildTour({ role: "admin", setup: FRESH, startChapter: chapter }).length > 0, chapter);
  }
});

test("generate chapter: new-feature path vs existing-feature path", () => {
  const ids = (setup) =>
    buildTour({ role: "editor", setup, startChapter: "generate" })
      .filter((s) => s.chapter === "generate")
      .map((s) => s.id);
  // No feature yet: open the project, create a feature, fill the form, generate, wait.
  assert.deepEqual(ids(FRESH), [
    "generate-open-project", "generate-new-feature", "generate-name",
    "generate-docs", "generate-mix", "generate-go", "generate-wait",
  ]);
  // A feature without cases: open it and regenerate instead.
  assert.deepEqual(ids({ ...FRESH, has_project: true, has_feature: true }), [
    "generate-open-project", "generate-open-feature", "generate-regenerate", "generate-wait",
  ]);
  // Generation already running: open the feature to follow it, no regenerate.
  assert.deepEqual(ids({ ...FRESH, has_project: true, has_feature: true, generating: true }), [
    "generate-open-project", "generate-open-feature", "generate-wait",
  ]);
  const env = (setup, view = "features") => ({ view, setup, role: "editor", visible: () => false });
  const byId = Object.fromEntries(STEPS.map((s) => [s.id, s]));
  // Already inside the project: no need to open it.
  assert.equal(byId["generate-open-project"].skip(env(FRESH, "features")), true);
  assert.equal(byId["generate-open-project"].skip(env(FRESH, "projects")), false);
  // The waiting step finishes when test cases exist.
  assert.equal(byId["generate-wait"].waitFor(env(FRESH)), false);
  assert.equal(byId["generate-wait"].waitFor(env({ ...FRESH, has_test_cases: true })), true);
});

test("grouped highlight for the requirements and waiting steps", () => {
  const byId = Object.fromEntries(STEPS.map((s) => [s.id, s]));
  assert.equal(byId["generate-docs"].group, true);
  assert.deepEqual(byId["generate-docs"].targets, ["#f-file", "#f-text"]);
  assert.equal(byId["generate-wait"].group, true);
});

test("progress is by part (chapter) and step within it", () => {
  const steps = buildTour({ role: "admin", setup: { ...FRESH, llm_configured: true } });
  const first = tourProgress(steps, 0);
  assert.deepEqual(first, { part: 1, parts: 6, title: "Welcome", step: 1, steps: 2 });
  const i = steps.findIndex((s) => s.id === "project-name");
  assert.deepEqual(tourProgress(steps, i), { part: 2, parts: 6, title: "Create a project", step: 2, steps: 3 });
  assert.equal(tourProgress(steps, 999), null);
});

test("project chapter waits for the real actions", () => {
  const byId = Object.fromEntries(STEPS.map((s) => [s.id, s]));
  const env = (view, visibleSel = []) => ({ view, setup: FRESH, role: "admin", visible: (s) => visibleSel.includes(s) });
  assert.equal(byId["project-new"].waitFor(env("projects")), false);
  assert.equal(byId["project-new"].waitFor(env("projects", ["#proj-create-card"])), true);
  assert.equal(byId["project-save"].waitFor(env("projects")), false);
  assert.equal(byId["project-save"].waitFor(env("features")), true);
});

test("welcome text adapts to the role", () => {
  const intro = STEPS.find((s) => s.id === "welcome-intro");
  assert.match(resolveText(intro.body, { role: "viewer", setup: FRESH }), /where everything is/);
  assert.match(resolveText(intro.body, { role: "admin", setup: FRESH }), /walks you through setup/);
  const done = { llm_configured: true, has_project: true, has_test_cases: true };
  assert.match(resolveText(intro.body, { role: "admin", setup: done }), /where everything is/);
  assert.equal(resolveText("plain", {}), "plain");
});

test("keyboard: Esc always closes; arrows navigate but never while typing or on action steps", () => {
  assert.equal(keyAction("Escape", { typing: true }), "close");
  assert.equal(keyAction("ArrowRight"), "next");
  assert.equal(keyAction("ArrowLeft"), "back");
  assert.equal(keyAction("ArrowRight", { typing: true }), null);
  assert.equal(keyAction("ArrowLeft", { typing: true }), null);
  assert.equal(keyAction("ArrowRight", { actionStep: true }), null);
  assert.equal(keyAction("Enter"), null);
  assert.equal(isActionStep(STEPS.find((s) => s.id === "project-new")), true);
  assert.equal(isActionStep(STEPS.find((s) => s.id === "welcome-intro")), false);
});

test("popup placement: below, above, side, centred, always inside the viewport", () => {
  const vp = { width: 1200, height: 800 };
  const pop = { width: 340, height: 200 };
  const r = (top, left, w = 100, h = 40) => ({ top, left, width: w, height: h, bottom: top + h, right: left + w });
  assert.equal(popoverPosition(r(100, 500), pop, vp).placement, "bottom");
  assert.equal(popoverPosition(r(700, 500), pop, vp).placement, "top");
  assert.equal(popoverPosition(r(50, 20, 300, 700), pop, vp).placement, "right");
  const c = popoverPosition(null, pop, vp);
  assert.equal(c.placement, "center");
  assert.equal(c.left, (1200 - 340) / 2);
  // Form steps prefer a side, so the popup does not cover the fields below.
  assert.equal(popoverPosition(r(100, 400, 300, 40), pop, vp, { prefer: "side" }).placement, "right");
  assert.equal(popoverPosition(r(100, 700, 300, 40), pop, vp, { prefer: "side" }).placement, "left");
  assert.equal(popoverPosition(r(100, 200, 900, 40), pop, vp, { prefer: "side" }).placement, "bottom");
  for (const rect of [r(0, 0), r(760, 1150), r(400, -50), null]) {
    const p = popoverPosition(rect, pop, vp);
    assert.ok(p.left >= 12 && p.left + pop.width <= vp.width - 12, JSON.stringify(p));
    assert.ok(p.top >= 12 && p.top + pop.height <= vp.height - 12, JSON.stringify(p));
  }
});

test("tour store: request → begin → next/back → end", () => {
  _resetTourForTests();
  let notified = 0;
  const unsub = subscribeTour(() => notified++);
  requestTour("project");
  assert.equal(getTourState().status, "loading");
  assert.equal(getTourState().chapter, "project");
  beginTour([{ id: "a" }, { id: "b" }]);
  assert.equal(getTourState().status, "active");
  previousStep(); // no-op on the first step
  assert.equal(getTourState().index, 0);
  nextStep();
  assert.equal(getTourState().index, 1);
  previousStep();
  assert.equal(getTourState().index, 0);
  nextStep();
  nextStep(); // past the last step ends the tour
  assert.equal(getTourState().status, "idle");
  requestTour();
  beginTour([]); // nothing to show
  assert.equal(getTourState().status, "idle");
  requestTour();
  beginTour([{ id: "a" }]);
  endTour();
  assert.equal(getTourState().status, "idle");
  beginTour([{ id: "x" }]); // ignored unless a start was requested
  assert.equal(getTourState().status, "idle");
  assert.ok(notified > 0);
  unsub();
});

test("onboarding flags are scoped per user, and safe without storage or DOM", async () => {
  const { scopedKey, readFlag, writeFlag, currentUser } = await import(
    "../src/features/onboarding/storage.js"
  );
  assert.equal(scopedKey("wq_tour_seen", "Admin"), "wq_tour_seen:admin");
  assert.equal(scopedKey("wq_tour_seen", " jo@example.com "), "wq_tour_seen:jo@example.com");
  assert.equal(scopedKey("wq_tour_seen", ""), "wq_tour_seen");
  assert.equal(scopedKey("wq_tour_seen", null), "wq_tour_seen");
  // No document / localStorage here (plain node): never throws, uses the fallback.
  assert.equal(currentUser(), "");
  assert.equal(readFlag("x", true), true);
  assert.doesNotThrow(() => writeFlag("x", true));
});
