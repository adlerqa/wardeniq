/**
 * Pure helpers for the Test Cases screen (was the list half of
 * compat/runtime/controllers/04-test-cases.js).
 *
 * typeLabel, caseTitle / cleanRequirementText and the priority helpers are
 * copies of the compat versions in 00-core.js, 03 and 04, which the feature
 * workspace and the case detail still use. When those move to React, they
 * should import these instead.
 */

export const PAGE_SIZE = 25;

export const DEFAULT_FILTERS = Object.freeze({
  project: "",
  feature: "",
  type: "",
  tag: "",
  status: "active",
  result: "",
  lineage: "",
  q: "",
});

export const TYPE_LABELS = {
  functional: "Business / functional",
  e2e: "End-to-end",
  api: "API",
  ui: "UI validation",
  nfr: "Edge & reliability",
  integration: "Integration",
};

export const typeLabel = (t) => TYPE_LABELS[t] || t;

export const LINEAGE_LABELS = {
  "": "Generated + reused",
  inherited: "Inherited / reused only",
  created: "Created in selected feature",
};

/** Strips "According to the PRD, ..." style prefixes from generated titles. */
export function cleanRequirementText(value) {
  let text = String(value || "").trim();
  const original = text.toLowerCase();
  const sourceKeyword = String.raw`(?:prd|hld|lld|spec|specification|document|requirements?|product|business|functional|technical|api|ui|ux|security|compliance|architecture|design|uploaded|source|reference)(?:\s+[\w.-]+){0,5}`;
  const sourceExact = String.raw`(?:[A-Z][A-Z0-9_-]{1,20}|[\w.-]+\.(?:pdf|docx?|md|txt))`;
  const kind = String.raw`(?:document|docs?|spec(?:ification)?|requirements?|rules?|design|architecture|guide|policy|story|ticket|epic|acceptance\s+criteria)`;
  const verb = String.raw`(?:requires?|states?|specifies?|defines?|indicates?|says?|suggests?|allows?|documents?|mandates?|notes?|describes?)`;
  text = text.replace(
    new RegExp(
      `^according\\s+to\\s+(?:the\\s+)?(?:${sourceExact}|${sourceKeyword})(?:\\s+${kind})?\\s*[,;:]\\s*`,
      "i",
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceExact}(?:\\s+${kind})?\\s*(?:rule|requirement)?(?:\\s*:\\s*|\\s+-\\s+)`,
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceKeyword}(?:\\s+${kind})?\\s*(?:rule|requirement)?(?:\\s*:\\s*|\\s+-\\s+)`,
      "i",
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceExact}(?:\\s+${kind})?\\s+${verb}\\s+(?:that\\s+)?`,
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceKeyword}(?:\\s+${kind})?\\s+${verb}\\s+(?:that\\s+)?`,
      "i",
    ),
    "",
  );
  if (original.includes("requires")) text = text.replace(/\bto be\b/i, "must be");
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

export const caseTitle = (c) =>
  cleanRequirementText(c?.title || "Untitled test case") || "Untitled test case";

export function prioKey(p) {
  const s = (p == null ? "" : p).toString().toLowerCase();
  if (["high", "critical", "p1", "1"].includes(s)) return "high";
  if (["medium", "mid", "p2", "2"].includes(s)) return "medium";
  return "low";
}

export function prioLabel(p) {
  return { high: "High", medium: "Medium", low: "Low" }[prioKey(p)];
}

/** [border, background, text] colours of the priority pill. */
export const PRIO_COLORS = {
  high: ["rgba(239,68,68,0.25)", "rgba(239,68,68,0.12)", "#fca5a5"],
  medium: ["rgba(59,130,246,0.25)", "rgba(59,130,246,0.12)", "#93c5fd"],
  low: ["rgba(34,197,94,0.25)", "rgba(34,197,94,0.12)", "#86efac"],
};

export const RESULT_OPTIONS = [
  ["untested", "Untested"],
  ["passed", "Passed"],
  ["failed", "Failed"],
  ["blocked", "Blocked"],
];

/** Query string for GET /api/test-cases (same parameter order as before). */
export function buildCaseQuery(filters, page) {
  const qp = new URLSearchParams();
  const m = {
    project_id: filters.project,
    feature_id: filters.feature,
    type: filters.type,
    tag: filters.tag,
    q: (filters.q || "").trim(),
    status: filters.status,
    execution_status: filters.result,
    lineage: filters.lineage,
  };
  Object.entries(m).forEach(([k, v]) => {
    if (v) qp.set(k, v);
  });
  qp.set("limit", PAGE_SIZE);
  qp.set("skip", page * PAGE_SIZE);
  return qp.toString();
}

/**
 * "N matching test case(s) · filter · filter" line.
 * `projectText` / `featureText` are the visible option labels.
 */
export function filterSummary(total, filters, { projectText = "", featureText = "" } = {}) {
  const q = (filters.q || "").trim();
  const active = [
    filters.project ? projectText : null,
    filters.feature ? featureText : null,
    filters.type ? typeLabel(filters.type) : null,
    filters.tag ? `tag: ${filters.tag}` : null,
    filters.status !== "active" ? `lifecycle: ${filters.status}` : null,
    filters.result ? `result: ${filters.result}` : null,
    filters.lineage ? `lineage: ${LINEAGE_LABELS[filters.lineage] ?? filters.lineage}` : null,
    q ? `search contains “${q}”` : null,
  ].filter(Boolean);
  return `${total} matching test case${total === 1 ? "" : "s"}${active.length ? ` · ${active.join(" · ")}` : ""}`;
}

export const pageCount = (total) => Math.max(1, Math.ceil(total / PAGE_SIZE));

/** Label for a project option (same text 02-projects.js used). */
export const projectOptionLabel = (p) =>
  `${p.name} — ${p.repo_count} repos · ${p.feature_count} features`;

/** Badge after the title: imported from a sheet, inherited, or none. */
export function lineageBadge(c) {
  if (c.imported || c.association_origin === "imported") return { kind: "imported", label: "Imported from sheet" };
  if (c.inherited)
    return {
      kind: "inherited",
      label: `Inherited${c.source_feature_name ? ` from ${c.source_feature_name}` : ""}`,
    };
  return null;
}

/** "API · 3 steps · linked to 2 features · deprecated" */
export function caseSubText(c) {
  return `${typeLabel(c.type)} · ${c.step_count} step${c.step_count === 1 ? "" : "s"}${
    c.shared_with_features > 1 ? ` · linked to ${c.shared_with_features} features` : ""
  }${c.deprecated ? " · deprecated" : ""}`;
}
