import assert from "node:assert/strict";
import test from "node:test";

import { exportUrls, planHeader, planSections } from "../src/features/test-plan/lib/testPlan.js";

test("header: feature name, project line only with a project", () => {
  assert.deepEqual(planHeader({ meta: { featureName: "Login" } }), {
    title: "Login",
    projectLine: null,
  });
  assert.deepEqual(
    planHeader({ meta: { featureName: "Login", projectName: "Shop", featureVersionNumber: 3 } }),
    { title: "Login", projectLine: "Project: Shop · Version: 3" },
  );
  assert.deepEqual(planHeader({ meta: { projectName: "Shop" } }), {
    title: "Test Plan",
    projectLine: "Project: Shop · Version: ",
  });
  assert.equal(planHeader({}).title, "Test Plan");
});

test("no sections renders nothing", () => {
  assert.deepEqual(planSections(null), []);
  assert.deepEqual(planSections({}), []);
});

test("each section type maps to render data", () => {
  const sections = planSections({
    sections: [
      { title: "Intro", type: "paragraph", content: "Hello" },
      { title: "Risks", type: "bullets", content: ["a", 2, null] },
      { title: "Done", type: "checklist", content: "not a list" },
      { title: "Env", type: "key_value", content: [{ key: "OS", value: "Linux" }] },
      {
        title: "Scope",
        type: "grouped_list",
        content: { in_scope: ["login"], out_of_scope: [] },
      },
      {
        title: "Matrix",
        type: "table",
        content: {
          columns: ["ID", "Name"],
          rows: [["1", "A"], { ID: "2", Name: "B" }, { ID: "3" }, "skip"],
        },
      },
      { title: "Other", type: "mystery", content: { a: 1 } },
    ],
  });
  assert.deepEqual(sections, [
    { title: "Intro", kind: "paragraph", text: "Hello" },
    { title: "Risks", kind: "list", items: ["a", "2", ""] },
    { title: "Done", kind: "empty" },
    { title: "Env", kind: "keyValue", rows: [{ key: "OS", value: "Linux" }] },
    { title: "Scope", kind: "grouped", groups: [{ label: "In Scope:", items: ["login"] }] },
    {
      title: "Matrix",
      kind: "table",
      columns: ["ID", "Name"],
      rows: [["1", "A"], ["2", "B"], ["3", ""]],
    },
    { title: "Other", kind: "json", text: '{\n  "a": 1\n}' },
  ]);
});

test("export links", () => {
  assert.deepEqual(exportUrls("r1"), {
    csv: "/api/test-plan/runs/r1/export/csv",
    pdf: "/api/test-plan/runs/r1/export/pdf",
  });
});
