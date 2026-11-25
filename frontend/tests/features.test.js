import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_FOCUS,
  cardMeta,
  estimateParts,
  filterSummaryLine,
  rebalanceFocus,
  splitLinks,
} from "../src/features/features/lib/features.js";

test("card text and links", () => {
  assert.equal(cardMeta({ case_count: 1 }), "Version 1 · 1 test case");
  assert.equal(cardMeta({ version: 2, case_count: 3, key: "K" }), "Version 2 · 3 test cases · K");
  assert.deepEqual(splitLinks(" a, b\nc  "), ["a", "b", "c"]);
  assert.deepEqual(splitLinks(""), []);
});

test("test type mix rebalancing", () => {
  let r = rebalanceFocus(DEFAULT_FOCUS, "api", 50, null);
  assert.deepEqual(r.values, { functional: 0, ui: 10, e2e: 20, api: 50, nfr: 20 });
  r = rebalanceFocus(r.values, "api", 30, r.partner);
  assert.deepEqual(r.values, { functional: 0, ui: 30, e2e: 20, api: 30, nfr: 20 });
  assert.deepEqual(rebalanceFocus(DEFAULT_FOCUS, "ui", 20, null).values, DEFAULT_FOCUS);
  assert.equal(Object.values(rebalanceFocus(DEFAULT_FOCUS, "nfr", 100, null).values).reduce((a, b) => a + b), 100);
});

test("cost estimate parts and the filter summary", () => {
  const fmt = (n) => `$${n}`;
  assert.deepEqual(estimateParts({ low: 1, high: 2, note: "n", warning: "w" }, 10, fmt), { cost: "Estimated cost: $1–$2 (n)", warning: "w" });
  assert.deepEqual(estimateParts({ note: "free" }, 10, fmt), { cost: "free", warning: "" });
  assert.deepEqual(estimateParts({ low: 1, high: 2, note: "n" }, 0, fmt), { cost: "", warning: "" });
  assert.equal(filterSummaryLine({}), "");
  assert.equal(filterSummaryLine({ testgen_filter: { rejected: 3, generated: 5, persisted: 2, rejected_by_reason: { a: 1, b: 2 } } }), "5 generated, 2 persisted (2 b, 1 a)");
});
