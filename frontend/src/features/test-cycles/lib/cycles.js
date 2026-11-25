/**
 * Pure helpers for the Test Cycles screen (was the Test Cycles half of
 * compat/runtime/controllers/08-code-analysis-and-cycles.js).
 */

export const ITEM_STATUSES = ["pending", "passed", "failed", "skipped", "blocked"];

/** Executed count and percent of a cycle. */
export function cycleProgress(c) {
  const cc = c.counts || {};
  const done = (cc.passed || 0) + (cc.failed || 0) + (cc.skipped || 0) + (cc.blocked || 0);
  return { done, pct: c.total ? Math.round((done / c.total) * 100) : 0 };
}

/** "3/5 executed · 1 passed · … · staging" under a cycle in the list. */
export function cycleListMeta(c) {
  const cc = c.counts || {};
  const { done } = cycleProgress(c);
  return `${done}/${c.total} executed · ${cc.passed || 0} passed · ${cc.failed || 0} failed · ${cc.skipped || 0} skipped · ${
    cc.blocked || 0
  } blocked · ${c.environment || "environment not set"}`;
}

/** Failed / blocked items with saved details keep their editor open. */
export function needsInlineEditor(item, editItemId) {
  return (
    editItemId === item.id ||
    ((item.execution_status === "failed" || item.execution_status === "blocked") &&
      !!(item.actual_result || item.notes || item.defect_link))
  );
}

/** YYYY-MM-DD part of a stored date (or ""). */
export const dateOnly = (v) => (v ? String(v).slice(0, 10) : "");

/** Badge next to the schedule: Scheduled / Ended / Active / none. */
export function scheduleBadge(start, end, today) {
  if (start && today < start) return { cls: "badge mm-partial", text: "Scheduled" };
  if (end && today > end) return { cls: "badge", text: "Ended" };
  if (start || end) return { cls: "badge mm-covered", text: "Active" };
  return null;
}

/** Start / end after changing one of them; `error` when end is before start. */
export function scheduleChange(cycle, field, value) {
  const start = field === "scheduled_start_at" ? value : dateOnly(cycle.scheduled_start_at);
  const end = field === "scheduled_end_at" ? value : dateOnly(cycle.scheduled_end_at);
  return { start, end, error: !!(start && end && end < start) };
}

/** Steps as { action, expected } — accepts dicts or "action → expected" strings. */
export function normalizeSteps(steps) {
  return (steps || []).map((s) => {
    if (typeof s === "string") {
      const p = s.split(/\s*(?:→|->)\s*/);
      return { action: p[0] || "", expected: p.slice(1).join(" → ") };
    }
    return { action: s.action || "", expected: s.expected || "" };
  });
}

/** Project cases not yet in the cycle. */
export function availableCases(items, cycle) {
  const existing = new Set(((cycle || {}).items || []).map((i) => i.case_id));
  return items.filter((c) => !existing.has(c.id));
}

/** Filter the add-cases list by title or display ID. */
export function filterCases(cases, query) {
  const q = (query || "").toLowerCase();
  return cases.filter(
    (c) => !q || (c.title || "").toLowerCase().includes(q) || (c.display_id || "").toLowerCase().includes(q),
  );
}

/** Body of PATCH /api/test-cycles/{id}/items. */
export function itemPatch(itemId, status, fields = {}) {
  return {
    item_id: itemId,
    status,
    actual_result: fields.actual_result || "",
    notes: fields.notes || "",
    defect_link: fields.defect_link || "",
  };
}
