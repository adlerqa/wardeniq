/**
 * Pure helpers for the Gap Analysis screen (was
 * compat/runtime/controllers/13-gap-analysis.js).
 */

export const TYPE_TITLES = {
  functional: "Business tests",
  e2e: "End-to-End",
  api: "API tests",
  ui: "UI validations",
  nfr: "Edge cases",
  other: "Other tests",
};
export const TYPE_ORDER = ["functional", "e2e", "api", "ui", "nfr", "other"];

export const typeTitle = (t) => TYPE_TITLES[t] || t.toUpperCase();
export const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : "");
export const isActiveRun = (run) => run.status === "running" || run.status === "pending";

/** One PR coverage run card. Partial matches are shown but not counted (#291). */
export function runCard(run) {
  const total = run.tests_total ?? 0;
  const covered = run.tests_covered ?? 0;
  const partial = run.tests_partial ?? 0;
  return {
    id: run.id,
    prId: run.pr_id,
    number: run.pr_number,
    title: run.pr_title || `PR #${run.pr_number}`,
    status: run.status,
    needsRerun: !!run.needs_rerun,
    excluded: !!run.excluded,
    repo: run.repo_full_name || "",
    branch: run.pr_branch || "",
    when: fmtTime(run.completed_at || run.created_at),
    covered,
    total,
    pct: total ? Math.round((100 * covered) / total) : 0,
    partial,
    source: run.source || "webhook",
  };
}

/**
 * A run's detail: feature cases grouped by type into covered / missing. An entry
 * saved before `status` existed was full coverage; "partial" was never confirmed,
 * so it is listed as missing with a note (#291).
 */
export function runDetail(r) {
  const result = r.result || {};
  const covered = result.covered || [];
  const cmp = result.comparison || {};
  const isConfirmed = (c) => (c.status ?? "covered") === "covered";
  const coveredById = {};
  for (const c of covered) coveredById[c.test_case_id] = c;
  const allCases = r.feature_cases || [];
  const sections = {};
  for (const c of allCases) {
    const t = (c.type || "other").toLowerCase();
    sections[t] = sections[t] || { covered: [], missing: [] };
    const ev = coveredById[c.id];
    if (ev && isConfirmed(ev)) sections[t].covered.push({ ...c, rationale: ev.rationale, by_dev_test: !!ev.by_dev_test });
    else if (ev) sections[t].missing.push({ ...c, partial: true, rationale: ev.rationale });
    else sections[t].missing.push(c);
  }
  const total = allCases.length || (r.tests_total ?? 0);
  const cov = covered.filter(isConfirmed).length;
  return {
    sections: TYPE_ORDER.filter((t) => sections[t]).map((t) => ({ type: t, ...sections[t] })),
    newly: new Set(cmp.newly_covered || []),
    lost: new Set(cmp.no_longer_covered || []),
    cov,
    total,
    partialCount: covered.filter((c) => c.status === "partial").length,
    gaps: Math.max(0, total - cov),
    newlyCount: cmp.newly_covered_detail ? cmp.newly_covered_detail.length : (cmp.newly_covered || []).length,
  };
}

/** Automation coverage priority class for an item's priority. */
export function autoPriority(p) {
  return (
    {
      p1: "high",
      p2: "medium",
      p3: "low",
      1: "high",
      2: "medium",
      3: "low",
      critical: "high",
      mid: "medium",
      high: "high",
      medium: "medium",
      low: "low",
    }[(p || "low").toString().toLowerCase()] || "low"
  );
}

/** The automation tab's items grouped by generated type. */
export function autoSections(items) {
  const sections = {};
  for (const it of items || []) {
    const t = (it.generated_type || "other").toLowerCase();
    sections[t] = sections[t] || { covered: [], missing: [] };
    if (it.status === "covered") sections[t].covered.push(it);
    else sections[t].missing.push(it);
  }
  return TYPE_ORDER.filter((t) => sections[t]).map((t) => ({ type: t, ...sections[t] }));
}

/** Framework badge class: known frameworks get their colour, the rest "unknown". */
export const frameworkClass = (fw) =>
  ["playwright", "cypress", "cucumber", "jest"].includes((fw || "").toLowerCase()) ? fw.toLowerCase() : "unknown";

/** Last three path segments of a test file. */
export const shortPath = (p) => (p || "").split("/").slice(-3).join("/");

/** "login_f__pr_coverage.csv" from the feature name. */
export function exportFileName(featureName, kind, fmt) {
  const base = (featureName || "feature").replace(/[^a-z0-9]+/gi, "_").toLowerCase();
  return `${base}_${kind === "pr-coverage" ? "pr_coverage" : "automation_coverage"}.${fmt}`;
}

/**
 * Body for a manual PR coverage run from what the user typed: a PR / MR URL, or a
 * PR number on the project's first App repo. Returns { body } or { error }.
 */
export function manualRunBody(featureId, text, repos) {
  const v = String(text).trim();
  const body = { feature_id: featureId };
  if (/https?:\/\//i.test(v)) return { body: { ...body, pr_url: v } };
  const appRepos = (repos || []).filter((rp) => (rp.repo_type || "app") === "app");
  if (!appRepos.length) return { error: "No App repos connected on this project" };
  const pn = parseInt(v.replace(/[^0-9]/g, ""));
  if (!pn) return { error: "Enter a numeric PR number or a full PR/MR URL" };
  return { body: { ...body, repo_id: appRepos[0].id, pr_number: pn } };
}
