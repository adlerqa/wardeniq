import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSetupSteps,
  canAct,
  checklistState,
  effectiveSetup,
  isGenerating,
  isSetupComplete,
  needsLlmStatus,
  needsRunningJobs,
  normaliseRole,
  setupProgress,
} from "../src/features/onboarding/setupSteps.js";

const NONE = {
  llm_configured: false,
  has_project: false,
  has_repo: false,
  has_feature: false,
  has_test_cases: false,
};
const healthy = (model = "qwen2.5:3b") => ({ llm: { model, health: { ok: true } } });
const unhealthy = { llm: { model: "qwen2.5:3b", health: { ok: false, error: "unreachable" } } };

test("fresh install: four steps, AI model is next, nothing done", () => {
  const steps = buildSetupSteps(effectiveSetup(NONE, null));
  assert.deepEqual(steps.map((s) => s.id), ["llm", "project", "repo", "generate"]);
  assert.ok(steps.every((s) => !s.done));
  assert.deepEqual(steps.filter((s) => s.next).map((s) => s.id), ["llm"]);
  assert.deepEqual(setupProgress(steps), { done: 0, total: 3 });
});

test("/api/status is only needed while the LLM settings were never saved", () => {
  assert.equal(needsLlmStatus(NONE), true);
  assert.equal(needsLlmStatus({ ...NONE, llm_configured: true }), false);
  assert.equal(needsLlmStatus(null), false);
});

test("a healthy, never-saved LLM counts as set up (same rule as the boot gate, #279)", () => {
  const eff = effectiveSetup(NONE, healthy());
  assert.equal(eff.llm_configured, true);
  assert.equal(eff.llm_source, "default");
  const [llm, project] = buildSetupSteps(eff);
  assert.equal(llm.done, true);
  assert.match(llm.note, /built-in model \(qwen2\.5:3b\)/);
  assert.equal(project.next, true);
});

test("an unhealthy or missing status leaves the LLM step to do", () => {
  for (const status of [unhealthy, null, {}, { llm: {} }]) {
    const eff = effectiveSetup(NONE, status);
    assert.equal(eff.llm_configured, false);
    assert.equal(eff.llm_source, null);
  }
});

test("saved settings count regardless of health, with no 'built-in' note", () => {
  const eff = effectiveSetup({ ...NONE, llm_configured: true }, unhealthy);
  assert.equal(eff.llm_source, "saved");
  assert.equal(buildSetupSteps(eff)[0].note, null);
});

test("the optional repository step is never next and not needed to complete", () => {
  const eff = effectiveSetup({ ...NONE, llm_configured: true, has_project: true }, null);
  const steps = buildSetupSteps(eff);
  assert.equal(steps.find((s) => s.id === "repo").next, false);
  assert.equal(steps.find((s) => s.next).id, "generate");
  assert.equal(isSetupComplete({ ...eff, has_feature: true, has_test_cases: true }), true);
});

test("a feature without test cases keeps the generate step open, with a hint", () => {
  const eff = effectiveSetup(
    { ...NONE, llm_configured: true, has_project: true, has_feature: true }, null);
  const gen = buildSetupSteps(eff).find((s) => s.id === "generate");
  assert.equal(gen.done, false);
  assert.match(gen.note, /without test cases/);
  assert.equal(gen.action, "Open my project");
  assert.equal(isSetupComplete(eff), false);
});

test("complete needs AI model, project and test cases", () => {
  const all = { ...NONE, llm_configured: true, has_project: true, has_feature: true, has_test_cases: true };
  assert.equal(isSetupComplete(all), true);
  assert.equal(isSetupComplete({ ...all, llm_configured: false }), false);
  assert.equal(isSetupComplete({ ...all, has_project: false }), false);
  assert.equal(isSetupComplete({ ...all, has_test_cases: false }), false);
  assert.equal(isSetupComplete(null), false);
  const steps = buildSetupSteps(all);
  assert.equal(steps.filter((s) => s.next).length, 0);
  assert.deepEqual(setupProgress(steps), { done: 3, total: 3 });
});

test("checklistState: hidden without data or when complete; collapsed when dismissed", () => {
  const done = effectiveSetup({ ...NONE, has_project: true, has_test_cases: true }, healthy());
  assert.equal(checklistState(null, false), "hidden");
  assert.equal(checklistState(done, false), "hidden");
  assert.equal(checklistState(done, true), "hidden");
  assert.equal(checklistState(effectiveSetup(NONE, null), false), "open");
  assert.equal(checklistState(effectiveSetup(NONE, null), true), "collapsed");
});

test("roles: viewers get no actions, editors cannot configure the AI model", () => {
  const [llm, project] = buildSetupSteps(NONE);
  assert.equal(canAct(project, "viewer"), false);
  assert.equal(canAct(llm, "viewer"), false);
  assert.equal(canAct(project, "editor"), true);
  assert.equal(canAct(llm, "editor"), false);
  assert.equal(canAct(llm, "admin"), true);
  assert.equal(canAct(project, undefined), false);
  assert.equal(normaliseRole("something-else"), "viewer");
});

test("running generation is told apart from a feature that never generated", () => {
  const base = { ...NONE, llm_configured: true, has_project: true, has_feature: true };
  assert.equal(needsRunningJobs(base), true);
  assert.equal(needsRunningJobs({ ...base, has_test_cases: true }), false);
  assert.equal(needsRunningJobs(NONE), false);
  const running = { jobs: [{ type: "generate", status: "running" }] };
  assert.equal(isGenerating(running), true);
  assert.equal(isGenerating({ jobs: [{ type: "code_analysis", status: "running" }] }), false);
  assert.equal(isGenerating(null), false);
  const gen = buildSetupSteps(effectiveSetup(base, null, running)).find((s) => s.id === "generate");
  assert.match(gen.note, /Generation is running/);
  const idle = buildSetupSteps(effectiveSetup(base, null, { jobs: [] })).find((s) => s.id === "generate");
  assert.match(idle.note, /without test cases/);
});
