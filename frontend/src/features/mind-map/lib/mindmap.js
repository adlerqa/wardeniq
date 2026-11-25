/**
 * Pure helpers for the Mind Map controls and coverage list (was the first
 * half of compat/runtime/controllers/09-mind-map-and-jobs.js).
 */

export const STATUSES = ["covered", "partial", "uncovered"];

/** Sort order of case statuses: covered, partial, uncovered, anything else. */
export const statusRank = (s) => ({ covered: 0, partial: 1, uncovered: 2 })[s] ?? 3;

/** Repo kind label / pill class / pre-checked for analysis (02-projects.js helpers). */
export function repoKindLabel(k) {
  return { BE: "BE", FE: "FE", test: "Test", infra: "Infra", other: "Other" }[k] || k || "BE";
}
export const repoKindClass = (k) => (k || "BE").toLowerCase();
/** Infrastructure repos are opt-in for analysis; everything else starts ticked. */
export const repoAnalysisDefaultChecked = (k) => (k || "").toLowerCase() !== "infra";

/** Friendly text for an analysis job stage. */
export function formatMindmapStage(stage) {
  const s = (stage || "").toLowerCase();
  if (!s) return "Preparing implementation coverage review…";
  if (s.startsWith("fetching github code") || s.startsWith("fetching gitlab code"))
    return "Downloading repository code…";
  if (s.startsWith("reusing index")) return "Reusing the existing code index for unchanged repositories…";
  if (s.startsWith("indexed ")) return "Indexing implementation files and preparing coverage checks…";
  if (s.startsWith("reviewing — "))
    return `Reviewing coverage for ${stage.split("reviewing — ")[1] || "the selected feature"}…`;
  return stage;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** "120 implementation chunks indexed · 1 feature reviewed" while the job runs. */
export function progressBits(result = {}) {
  return [
    result.code_chunks ? `${result.code_chunks} implementation chunks indexed` : null,
    result.features_mapped ? `${plural(result.features_mapped, "feature")} reviewed` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Plain-text part of the "Review complete" line (note / errors are added by the view). */
export function completeText(result = {}) {
  const mapped = result.features_mapped || 0;
  return `Review complete · ${result.code_chunks || 0} implementation chunks indexed · ${plural(mapped, "feature")} reviewed${
    result.tests_skipped ? ` · ${result.tests_skipped} test files excluded` : ""
  }`;
}

/** Totals over all features. */
export function coverageTotals(features) {
  const tot = { covered: 0, partial: 0, uncovered: 0 };
  features.forEach((f) => STATUSES.forEach((k) => (tot[k] += f.counts[k])));
  return tot;
}

/** Widths (whole percents) of the coverage bar segments. */
export function barPercents(counts, total) {
  return Object.fromEntries(STATUSES.map((k) => [k, Math.round(((counts[k] || 0) / total) * 100)]));
}

/** One line per repo of the last analysis, for the "why is it empty" card. */
export function emptyReasonLine(r) {
  const branch = r.branch || "default";
  if (r.error) return { repo: r.repo, text: ` (branch ${branch}) — fetch error: ${r.error}` };
  if (r.reused)
    return {
      repo: r.repo,
      text: ` (branch ${branch}): ${r.impl_files || 0} implementation file(s) indexed (reused, unchanged since last run)`,
    };
  return {
    repo: r.repo,
    text: ` (branch ${branch}): ${r.files_in_repo ?? 0} file(s) total, ${r.impl_files ?? 0} remaining after excluding ${
      r.test_files || 0
    } test file(s) and ${r.non_impl_files || 0} non-implementation file(s)`,
  };
}

/** Whether the "why is it empty" card has anything to say. */
export function hasEmptyReason(last) {
  return !!last && !!(last.note || (last.per_repo || []).length || (last.errors || []).length);
}

/** Accessible GitHub repos not yet connected to the project, filtered by a query (max 300). */
export function filterPickerRepos(repos, query) {
  const q = (query || "").toLowerCase();
  return repos.filter((r) => !q || (r.full_name || "").toLowerCase().includes(q)).slice(0, 300);
}

/** Drop repos already connected (case-insensitive full name). */
export function withoutConnected(accessible, connected) {
  const existing = new Set((connected || []).map((r) => (r.full_name || "").toLowerCase()));
  return accessible.filter((r) => !existing.has((r.full_name || "").toLowerCase()));
}

/** Branch picks for POST /api/code-analysis: { repoId: branch } for non-blank ones. */
export function branchMap(rows) {
  const m = {};
  rows.forEach((r) => {
    if ((r.branch || "").trim()) m[r.id] = r.branch.trim();
  });
  return m;
}
