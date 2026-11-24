import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_FILTERS,
  buildCaseQuery,
  caseSubText,
  caseTitle,
  filterSummary,
  lineageBadge,
  pageCount,
  prioKey,
  prioLabel,
  projectOptionLabel,
} from "../src/features/test-cases/lib/testCases.js";

test("buildCaseQuery keeps the old parameter order and skips empty filters", () => {
  assert.equal(buildCaseQuery(DEFAULT_FILTERS, 0), "status=active&limit=25&skip=0");
  const all = {
    project: "p1",
    feature: "f1",
    type: "api",
    tag: "smoke",
    q: "  reset ",
    status: "all",
    result: "passed",
    lineage: "inherited",
  };
  assert.equal(
    buildCaseQuery(all, 2),
    "project_id=p1&feature_id=f1&type=api&tag=smoke&q=reset&status=all&execution_status=passed&lineage=inherited&limit=25&skip=50",
  );
});

test("filterSummary matches the old summary line", () => {
  assert.equal(filterSummary(10, DEFAULT_FILTERS), "10 matching test cases");
  assert.equal(filterSummary(1, DEFAULT_FILTERS), "1 matching test case");
  const f = {
    project: "p1",
    feature: "f1",
    type: "e2e",
    tag: "api-test",
    q: " reset ",
    status: "all",
    result: "passed",
    lineage: "inherited",
  };
  assert.equal(
    filterSummary(0, f, { projectText: "Tour QA — 0 repos · 1 features", featureText: "WQ test - Password reset" }),
    "0 matching test cases · Tour QA — 0 repos · 1 features · WQ test - Password reset · End-to-end · tag: api-test · lifecycle: all · result: passed · lineage: Inherited / reused only · search contains “reset”",
  );
});

test("pageCount, project label, priority", () => {
  assert.equal(pageCount(0), 1);
  assert.equal(pageCount(25), 1);
  assert.equal(pageCount(26), 2);
  assert.equal(projectOptionLabel({ name: "Tour QA", repo_count: 0, feature_count: 1 }), "Tour QA — 0 repos · 1 features");
  assert.equal(prioKey("P1"), "high");
  assert.equal(prioKey("mid"), "medium");
  assert.equal(prioKey(undefined), "low");
  assert.equal(prioLabel("2"), "Medium");
});

test("caseTitle strips source prefixes; lineage badge and sub text", () => {
  assert.equal(caseTitle({ title: "According to the PRD, user can reset password" }), "User can reset password");
  assert.equal(caseTitle({ title: "" }), "Untitled test case");
  assert.deepEqual(lineageBadge({ imported: true }), { kind: "imported", label: "Imported from sheet" });
  assert.deepEqual(lineageBadge({ association_origin: "imported" }), { kind: "imported", label: "Imported from sheet" });
  assert.deepEqual(lineageBadge({ inherited: true, source_feature_name: "Login" }), {
    kind: "inherited",
    label: "Inherited from Login",
  });
  assert.equal(lineageBadge({}), null);
  assert.equal(caseSubText({ type: "api", step_count: 1 }), "API · 1 step");
  assert.equal(
    caseSubText({ type: "nfr", step_count: 3, shared_with_features: 2, deprecated: true }),
    "Edge & reliability · 3 steps · linked to 2 features · deprecated",
  );
});
