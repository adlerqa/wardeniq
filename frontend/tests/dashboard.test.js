import assert from "node:assert/strict";
import test from "node:test";

import { METRICS, clampPercent, projectsLabel, typeRows } from "../src/features/dashboard/lib/dashboard.js";

test("clampPercent", () => {
  assert.equal(clampPercent(-5), 0);
  assert.equal(clampPercent(150), 100);
  assert.equal(clampPercent("42"), 42);
  assert.equal(clampPercent(undefined), 0);
});

test("type rows: width relative to the largest, palette in order", () => {
  assert.deepEqual(typeRows({ functional: 2, api: 4, ui: 0 }), [
    { type: "functional", value: 2, width: 50, color: "#38bdf8" },
    { type: "api", value: 4, width: 100, color: "#a78bfa" },
    { type: "ui", value: 0, width: 0, color: "#34d399" },
  ]);
  assert.deepEqual(typeRows({}), []);
  assert.equal(typeRows({ a: 1, b: 1, c: 1, d: 1, e: 1, f: 1, g: 1 })[6].color, "#38bdf8");
});

test("labels and tile order", () => {
  assert.equal(projectsLabel(1), "1 project");
  assert.equal(projectsLabel(3), "3 projects");
  assert.equal(projectsLabel(undefined), "0 projects");
  assert.deepEqual(METRICS.map((m) => m[1]), [
    "Projects", "Features", "Test cases", "Test steps", "Documents", "Repositories", "Pull requests",
  ]);
});
