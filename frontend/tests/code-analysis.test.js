import assert from "node:assert/strict";
import test from "node:test";

import {
  analyzeTitle,
  daysInRange,
  doneText,
  formatCycleStage,
  impactNarrative,
  impactStatusBadge,
  lookbackDays,
  restoredCounts,
  riskBadge,
  runningText,
  signalLabel,
  startText,
} from "../src/features/code-analysis/lib/codeAnalysis.js";

test("lookback range, request days and the analyze button title", () => {
  for (const v of ["0", "181", "", "abc"]) assert.equal(daysInRange(v), false, v);
  for (const v of ["1", "180", "14"]) assert.equal(daysInRange(v), true, v);
  assert.equal(lookbackDays("30"), 30);
  assert.equal(lookbackDays(""), 14);
  assert.equal(analyzeTitle(false, true), "Lookback must be between 1 and 180 days");
  assert.equal(analyzeTitle(true, true), "Analysis in progress…");
  assert.equal(analyzeTitle(true, false), "");
});

test("status texts", () => {
  assert.equal(startText(1), "Starting change impact review for 1 repo…");
  assert.equal(startText(2), "Starting change impact review for 2 repos…");
  assert.equal(formatCycleStage(""), "Preparing change impact review…");
  assert.equal(formatCycleStage("Fetching GitHub commits for o/x"), "Reading recent commits from the selected repositories…");
  assert.equal(formatCycleStage("grounded matching"), "Matching changed code to impacted test cases…");
  assert.equal(formatCycleStage("LLM impact analysis 2/3"), "Reviewing the remaining cases for likely impact…");
  assert.equal(formatCycleStage("other"), "other");
  assert.equal(runningText("mapping", {}), "⏳ mapping");
  assert.equal(runningText("mapping", { commit_count: 3, changed_files: ["a", "b"] }), "⏳ mapping (3 commits, 2 files)");
  assert.equal(doneText({}), "Review complete · 0 commits · 0 files changed");
  assert.equal(doneText({ commit_count: 3, changed_files: ["a"], note: "n" }), "Review complete · 3 commits · 1 files changed · n");
});

test("badges, narrative and counts of a saved review", () => {
  assert.deepEqual(impactStatusBadge("matched"), { cls: "mm-covered", label: "Direct match" });
  assert.deepEqual(impactStatusBadge("partial"), { cls: "mm-partial", label: "Needs review" });
  assert.deepEqual(impactStatusBadge(null), { cls: "mm-uncovered", label: "Unverified" });
  assert.equal(riskBadge("P1").label, "High risk");
  assert.equal(riskBadge("p3").label, "Low risk");
  assert.equal(riskBadge(undefined).label, "Medium risk");
  assert.equal(riskBadge("odd").color, "#93c5fd");
  assert.match(impactNarrative({ signal_type: "endpoint", signal: "/x" }), /next regression pass/);
  assert.equal(impactNarrative({ signal_type: "ai", reason: "R" }), "R");
  assert.match(impactNarrative({ signal_type: "ai" }), /quick manual review/);
  assert.equal(impactNarrative({}), "This testcase appears related to the recent implementation changes.");
  assert.equal(signalLabel("symbol"), "Matched code signal");
  assert.equal(signalLabel("x"), "Reference");
  assert.deepEqual(restoredCounts([{ signal_type: "ai" }, { signal_type: "endpoint" }, {}]), { grounded: 1, ai: 1 });
});
