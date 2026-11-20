/**
 * Pure logic for the Test Plan screen. Turns a generated test plan into plain
 * render data, matching what the compat renderTestPlan() produced, so the
 * React components only map data to elements. Unit-tested in
 * frontend/tests/test-plan.test.js.
 */

const text = (v) => (v ?? "").toString();

/** Header of a rendered plan: { title, projectLine | null }. */
export function planHeader(plan) {
  const meta = (plan && plan.meta) || {};
  return {
    title: text(meta.featureName || "Test Plan"),
    projectLine: meta.projectName
      ? `Project: ${text(meta.projectName)} · Version: ${text(meta.featureVersionNumber)}`
      : null,
  };
}

/**
 * Sections of a plan as render data. Each item is { title, kind, ... }:
 *   paragraph → { text }
 *   list      → { items }                 (bullets / checklist)
 *   keyValue  → { rows: [{ key, value }] }
 *   grouped   → { groups: [{ label, items }] }  (in scope / out of scope)
 *   table     → { columns, rows: string[][] }
 *   json      → { text }                  (unknown section type)
 *   empty     → nothing to show under the title
 * Returns [] when the plan has no sections.
 */
export function planSections(plan) {
  if (!plan || !plan.sections) return [];
  return plan.sections.map((sec) => {
    const title = text(sec.title);
    const { type, content } = sec;
    if (type === "paragraph") return { title, kind: "paragraph", text: text(content) };
    if (type === "bullets" || type === "checklist") {
      return Array.isArray(content)
        ? { title, kind: "list", items: content.map(text) }
        : { title, kind: "empty" };
    }
    if (type === "key_value") {
      return Array.isArray(content)
        ? {
            title,
            kind: "keyValue",
            rows: content.map((x) => ({ key: text(x && x.key), value: text(x && x.value) })),
          }
        : { title, kind: "empty" };
    }
    if (type === "grouped_list") {
      if (!content || typeof content !== "object") return { title, kind: "empty" };
      const groups = [];
      for (const [key, label] of [
        ["in_scope", "In Scope:"],
        ["out_of_scope", "Out of Scope:"],
      ]) {
        const items = content[key];
        if (Array.isArray(items) && items.length) groups.push({ label, items: items.map(text) });
      }
      return { title, kind: "grouped", groups };
    }
    if (type === "table") {
      if (!content || typeof content !== "object") return { title, kind: "empty" };
      const columns = (content.columns || []).map(text);
      const rows = [];
      for (const r of content.rows || []) {
        if (Array.isArray(r)) rows.push(r.map(text));
        else if (r && typeof r === "object") rows.push(columns.map((c) => text(r[c] || "")));
      }
      return { title, kind: "table", columns, rows };
    }
    return { title, kind: "json", text: text(JSON.stringify(content, null, 2)) };
  });
}

export const exportUrls = (runId) => ({
  csv: `/api/test-plan/runs/${runId}/export/csv`,
  pdf: `/api/test-plan/runs/${runId}/export/pdf`,
});
