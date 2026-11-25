/**
 * Pure helpers for the Code Analysis (change impact) screen (was the code
 * analysis half of compat/runtime/controllers/08-code-analysis-and-cycles.js).
 */

// Lookback bounds — kept in sync with the min/max on #cyc-days and with
// AnalyzeIn's server-side Field(ge=1, le=180). The button has no wrapping
// <form>, so min/max alone never block a click: the button's disabled state
// is driven from the value.
export const DAYS_MIN = 1;
export const DAYS_MAX = 180;
export const DEFAULT_DAYS = 14;
export const DAYS_RANGE_TEXT = `Lookback must be between ${DAYS_MIN} and ${DAYS_MAX} days`;

export function daysInRange(value) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) && n >= DAYS_MIN && n <= DAYS_MAX;
}

/** Days sent with a request: the input's number, or 14. */
export const lookbackDays = (value) => parseInt(value) || DEFAULT_DAYS;

/** Hover text of #cyc-analyze explaining why it is disabled. */
export function analyzeTitle(inRange, running) {
  if (!inRange) return DAYS_RANGE_TEXT;
  return running ? "Analysis in progress…" : "";
}

export const startText = (n) => `Starting change impact review for ${n} repo${n === 1 ? "" : "s"}…`;

/** Friendly text for an analysis job stage. */
export function formatCycleStage(stage) {
  const s = (stage || "").toLowerCase();
  if (!s) return "Preparing change impact review…";
  if (s.startsWith("fetching github commits") || s.startsWith("fetching gitlab commits"))
    return "Reading recent commits from the selected repositories…";
  if (s.startsWith("grounded matching")) return "Matching changed code to impacted test cases…";
  if (s.startsWith("llm impact analysis")) return "Reviewing the remaining cases for likely impact…";
  return stage;
}

/** "⏳ stage (3 commits, 2 files)" while the job runs. */
export function runningText(stage, a = {}) {
  return `⏳ ${formatCycleStage(stage)}${a.commit_count ? ` (${a.commit_count} commits, ${(a.changed_files || []).length} files)` : ""}`;
}

export function doneText(a = {}) {
  return `Review complete · ${a.commit_count || 0} commits · ${(a.changed_files || []).length} files changed${
    a.note ? ` · ${a.note}` : ""
  }`;
}

export const restoredText = (n) => `↻ Restored the latest saved impact review · ${n} impacted case(s)`;
export const NO_SAVED_TEXT = "No saved impact analysis for this project yet — click Analyze changes.";

/** Direct-evidence / model-reviewed counts of a saved review. */
export function restoredCounts(results) {
  return {
    grounded: results.filter((r) => r.signal_type && r.signal_type !== "ai").length,
    ai: results.filter((r) => r.signal_type === "ai").length,
  };
}

export function impactStatusBadge(status) {
  const s = (status || "").toLowerCase();
  if (s === "matched" || s === "covered") return { cls: "mm-covered", label: "Direct match" };
  if (s === "review_needed" || s === "partial") return { cls: "mm-partial", label: "Needs review" };
  return { cls: "mm-uncovered", label: "Unverified" };
}

const RISK_COLORS = {
  high: ["rgba(239,68,68,0.25)", "rgba(239,68,68,0.12)", "#fca5a5"],
  medium: ["rgba(59,130,246,0.25)", "rgba(59,130,246,0.12)", "#93c5fd"],
  low: ["rgba(34,197,94,0.25)", "rgba(34,197,94,0.12)", "#86efac"],
};

/** Risk level of a case: high (high / critical / p1), low (low / p3), else medium. */
export function riskBadge(risk) {
  const s = (risk || "medium").toString().trim().toLowerCase();
  const k = ["high", "critical", "p1"].includes(s) ? "high" : ["low", "p3"].includes(s) ? "low" : "medium";
  const [border, background, color] = RISK_COLORS[k];
  return { label: `${{ high: "High", medium: "Medium", low: "Low" }[k]} risk`, border, background, color };
}

export function impactNarrative(c) {
  if (c.signal_type === "endpoint")
    return c.signal
      ? `A changed API endpoint directly maps to this testcase, so it should be part of the next regression pass.`
      : `A changed API endpoint directly maps to this testcase.`;
  if (c.signal_type === "symbol")
    return `A changed implementation signal overlaps with this testcase closely enough to treat it as directly impacted.`;
  if (c.signal_type === "ai")
    return c.reason || `The broader change set looks related to this testcase, so it is included for a quick manual review.`;
  return c.reason || "This testcase appears related to the recent implementation changes.";
}

export function signalLabel(signalType) {
  if (signalType === "endpoint") return "Matched endpoint";
  if (signalType === "symbol") return "Matched code signal";
  return "Reference";
}

export const sourceLabel = (c) => (c.signal_type === "ai" ? "Model-reviewed suggestion" : "Direct code evidence");

export const evidenceFileLine = (e) => `${e.file || ""}${e.line ? `:${e.line}` : ""}`;

export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
