import assert from "node:assert/strict";
import test from "node:test";

import {
  availableCases,
  cycleListMeta,
  cycleProgress,
  dateOnly,
  filterCases,
  itemPatch,
  needsInlineEditor,
  normalizeSteps,
  scheduleBadge,
  scheduleChange,
} from "../src/features/test-cycles/lib/cycles.js";

test("progress and list line", () => {
  const c = { total: 5, counts: { passed: 1, failed: 1, blocked: 1, skipped: 0 }, environment: "staging" };
  assert.deepEqual(cycleProgress(c), { done: 3, pct: 60 });
  assert.deepEqual(cycleProgress({ total: 0, counts: {} }), { done: 0, pct: 0 });
  assert.equal(cycleListMeta(c), "3/5 executed · 1 passed · 1 failed · 0 skipped · 1 blocked · staging");
  assert.equal(cycleListMeta({ total: 0 }), "0/0 executed · 0 passed · 0 failed · 0 skipped · 0 blocked · environment not set");
});

test("inline editor, schedule badge and date checks", () => {
  assert.equal(needsInlineEditor({ id: "a", execution_status: "failed", notes: "x" }, null), true);
  assert.equal(needsInlineEditor({ id: "a", execution_status: "failed" }, null), false);
  assert.equal(needsInlineEditor({ id: "a", execution_status: "passed", notes: "x" }, null), false);
  assert.equal(needsInlineEditor({ id: "a", execution_status: "pending" }, "a"), true);
  assert.equal(dateOnly("2026-11-20T00:00:00"), "2026-11-20");
  assert.equal(dateOnly(null), "");
  const today = "2026-11-25";
  assert.deepEqual(scheduleBadge("2026-12-01", "", today), { cls: "badge mm-partial", text: "Scheduled" });
  assert.deepEqual(scheduleBadge("", "2026-11-01", today), { cls: "badge", text: "Ended" });
  assert.deepEqual(scheduleBadge("2026-11-01", "2026-12-01", today), { cls: "badge mm-covered", text: "Active" });
  assert.equal(scheduleBadge("", "", today), null);
  const cy = { scheduled_start_at: "2026-11-20T00:00:00", scheduled_end_at: "2026-11-30T00:00:00" };
  assert.equal(scheduleChange(cy, "scheduled_end_at", "2026-11-10").error, true);
  assert.equal(scheduleChange(cy, "scheduled_start_at", "").error, false);
  assert.equal(scheduleChange(cy, "scheduled_start_at", "2026-12-05").error, true);
});

test("steps, available cases, filter, item patch", () => {
  assert.deepEqual(normalizeSteps([{ action: "A", expected: "B" }, "Do -> See → More", "Only"]), [
    { action: "A", expected: "B" },
    { action: "Do", expected: "See → More" },
    { action: "Only", expected: "" },
  ]);
  const cases = [{ id: "1", title: "Reset", display_id: "TQ-1" }, { id: "2", title: "Login" }];
  assert.deepEqual(availableCases(cases, { items: [{ case_id: "1" }] }).map((c) => c.id), ["2"]);
  assert.deepEqual(filterCases(cases, "tq-").map((c) => c.id), ["1"]);
  assert.deepEqual(filterCases(cases, "LOG").map((c) => c.id), ["2"]);
  assert.deepEqual(itemPatch("i1", "failed", { notes: "n" }), {
    item_id: "i1", status: "failed", actual_result: "", notes: "n", defect_link: "",
  });
});
