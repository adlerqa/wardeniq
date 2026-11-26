/**
 * Pure helpers for the feature workspace (was openFeature and friends in
 * compat/runtime/controllers/03-features-and-usage.js).
 */

/** "Version 3 · WQ-5 · 4 test cases" above the summary. */
export const featureMeta = (f) =>
  `Version ${f.version || 1}${f.key ? ` · ${f.key}` : ""} · ${f.test_cases.length} test case${f.test_cases.length === 1 ? "" : "s"}`;

/** One-paragraph summary: the saved summary, else a sentence from the requirement text, else a stock line. */
export function featureSummaryText(f) {
  const summary = String(f.summary || "")
    .replace(/\s+/g, " ")
    .trim();
  if (summary && !/^(###|Document:|PRD|HLD|LLD)\b/i.test(summary)) return summary;
  const text = String(f.text || "")
    .replace(/\s+/g, " ")
    .trim();
  const stripped = text
    .replace(/###\s*(document|uploaded documents?|pasted requirement|requirements?)\s*:?.*?(?=\n|$)/gi, "")
    .replace(/\b[A-Za-z0-9_-]+\.pdf\b/gi, "")
    .replace(/\b(PRD|HLD|LLD)\s*[—-]\s*[^.?!\n]{0,180}/gi, "")
    .replace(/\b(PRD|HLD|LLD)\b\s*:?/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  const sentence = (stripped.match(/[^.!?]{40,260}[.!?]/) || [])[0];
  if (sentence) return sentence.trim();
  if (stripped.length > 80) return stripped.slice(0, 240).trim() + "…";
  return `${f.name} is ready for review with generated test coverage across functional, API, end-to-end, and reliability scenarios.`;
}

/** Case groups in display order: [type, label, help]. */
export const CASE_GROUPS = [
  ["api", "API", "Endpoint happy paths, validation, authorization, and failure handling"],
  ["ui", "UI validations", "Visible fields, controls, and client-side validation"],
  ["functional", "Business / functional", "Business rules and requirement behavior"],
  ["e2e", "End-to-end", "Complete user journeys across UI, API, and persisted state"],
  ["nfr", "Edge & reliability", "Concurrency, resilience, limits, latency, and degraded dependencies"],
  ["integration", "Integration", "Cross-feature scenarios: cases inherited / linked from other features"],
];

/** Cases by group (category, else type). */
export function groupCases(cases) {
  const bt = {};
  cases.forEach((c) => {
    const k = c.category || c.type;
    (bt[k] = bt[k] || []).push(c);
  });
  return bt;
}

/** Every grouped case in display order (cases of other types are not shown). */
export const orderedCases = (bt) => CASE_GROUPS.flatMap(([t]) => bt[t] || []);

/** The version-diff note: { kind: "version", version, kept, retired } | { kind: "replace", removed } | null. */
export function versionInfo(vd = {}) {
  if (vd.mode === "version" || (vd.retired && vd.retired.length))
    return { kind: "version", version: vd.version, kept: vd.kept || 0, retired: vd.retired || [] };
  if (vd.mode === "replace") return { kind: "replace", removed: vd.retired_orphans || 0 };
  return null;
}

export const genCaption = (j) => {
  const res = j.result || {};
  return `${j.stage || "Generating test cases…"} · ${res.cases_new || 0} new · ${res.cases_reused || 0} reused so far`;
};

/** Case row "origin · type" text and badge, as the workspace shows them. */
export const INHERITED = ["reused", "carried", "carried_repaired", "inherited", "adapted"];
