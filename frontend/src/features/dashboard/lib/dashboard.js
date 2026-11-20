/**
 * Pure logic for the Dashboard, ported from the compat 01-dashboard.js.
 * Unit-tested in frontend/tests/dashboard.test.js.
 */

export const clampPercent = (value) => Math.max(0, Math.min(100, Number(value) || 0));

/** KPI tiles in display order: [count key, label, tone]. */
export const METRICS = [
  ["projects", "Projects", "cyan"],
  ["features", "Features", "violet"],
  ["test_cases", "Test cases", "blue"],
  ["test_steps", "Test steps", "indigo"],
  ["documents", "Documents", "amber"],
  ["repos", "Repositories", "emerald"],
  ["pull_requests", "Pull requests", "rose"],
];

/** Bar colours of "Test cases by type" (compat RC_COLORS order). */
export const TYPE_PALETTE = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#fb7185", "#2dd4bf"];

/** Rows of "Test cases by type": { type, value, width (percent of the largest), color }. */
export function typeRows(byType) {
  const entries = Object.entries(byType || {});
  const max = Math.max(...entries.map(([, v]) => Number(v)), 1);
  return entries.map(([type, count], i) => {
    const value = Number(count) || 0;
    return { type, value, width: (value / max) * 100, color: TYPE_PALETTE[i % TYPE_PALETTE.length] };
  });
}

export const projectsLabel = (n) => `${n ?? 0} ${Number(n) === 1 ? "project" : "projects"}`;
