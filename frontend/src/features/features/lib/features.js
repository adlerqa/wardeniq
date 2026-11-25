/**
 * Pure helpers for the feature list and the "New feature" page (was the first
 * part of compat/runtime/controllers/03-features-and-usage.js).
 */

/** "Version 2 · 1 test case · WQ-1" under a feature card's name. */
export const cardMeta = (f) =>
  `Version ${f.version || 1} · ${f.case_count} test case${f.case_count === 1 ? "" : "s"}${f.key ? ` · ${f.key}` : ""}`;

/** "1 feature" under the Features title. */
export const featureCountText = (p) => `${p.feature_count} feature${p.feature_count === 1 ? "" : "s"}`;

/** Confluence / Figma links: one per line, or separated by spaces / commas. */
export const splitLinks = (value) =>
  (value || "")
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

// ---- test type mix (five sliders that always add up to 100) ----
export const FOCUS_TYPES = ["functional", "ui", "e2e", "api", "nfr"];
export const FOCUS_LABELS = {
  functional: "Functional",
  ui: "UI validations",
  e2e: "End-to-end",
  api: "API",
  nfr: "Edge & reliability",
};
export const DEFAULT_FOCUS = { functional: 20, ui: 20, e2e: 20, api: 20, nfr: 20 };

/** The other category with the most weight (ties: the earlier one), skipping `exclude`. */
export function largestFocusOther(changed, values, exclude = []) {
  return FOCUS_TYPES.filter((t) => t !== changed && !exclude.includes(t)).sort(
    (a, b) => values[b] - values[a] || FOCUS_TYPES.indexOf(a) - FOCUS_TYPES.indexOf(b),
  )[0];
}

/**
 * Move `changed` to `value` and take / give the difference from the partner
 * category (the largest other one, then the next largest when it runs out).
 * Returns the new values and the partner to keep for the rest of the drag.
 */
export function rebalanceFocus(previous, changed, value, partnerIn) {
  const values = { ...previous };
  const changedValue = Math.max(0, Math.min(100, value));
  let delta = changedValue - (previous[changed] || 0);
  values[changed] = changedValue;
  const exhausted = [];
  let partner = partnerIn;
  while (delta !== 0) {
    if (!partner || partner === changed || exhausted.includes(partner)) partner = largestFocusOther(changed, values, exhausted);
    if (!partner) break;
    if (delta > 0) {
      const taken = Math.min(delta, values[partner]);
      values[partner] -= taken;
      delta -= taken;
      if (values[partner] === 0) exhausted.push(partner);
    } else {
      values[partner] += -delta;
      delta = 0;
    }
  }
  return { values, partner };
}

export const focusTotal = (values) => FOCUS_TYPES.reduce((sum, t) => sum + values[t], 0);

// ---- pre-run cost estimate (issue #22) ----
/** Characters to estimate: pasted text plus file sizes (a rough stand-in until upload). */
export const estimateLength = (text, files) => (text ? text.length : 0) + files.reduce((sum, f) => sum + (f.size || 0), 0);

/** The cost line (only once there is a document) and any warning (e.g. a model on CPU). */
export function estimateParts(r, textLength, fmtUsd) {
  const cost = !textLength
    ? ""
    : r.low != null && r.high != null
      ? `Estimated cost: ${fmtUsd(r.low)}–${fmtUsd(r.high)} (${r.note})`
      : r.note || "";
  return { cost, warning: r.warning || "" };
}

// ---- generation progress ----
/** #64: "6 generated, 4 persisted (1 exemplar-copy, 1 no-source)" when filters rejected cases. */
export function filterSummaryLine(res) {
  const f = res && res.testgen_filter;
  if (!f || !f.rejected) return "";
  const breakdown = Object.entries(f.rejected_by_reason || {})
    .sort((a, b) => b[1] - a[1])
    .map(([reason, count]) => `${count} ${reason}`)
    .join(", ");
  return `${f.generated} generated, ${f.persisted} persisted (${breakdown})`;
}

export const casesLine = (res) =>
  `${res.cases_new || 0} new + ${res.cases_reused || 0} reused cases · ${res.steps_new || 0} new + ${res.steps_reused || 0} reused steps`;
