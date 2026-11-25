/**
 * Pure helpers for a test case's detail panel (was caseDetailHtml and friends
 * in compat/runtime/controllers/04-test-cases.js).
 */
import { caseTitle, cleanRequirementText } from "./testCases.js";

/** Readable text for a metadata value (arrays become "• " lines, objects "key: value" lines). */
export function caseMetaText(value) {
  if (value === null || value === undefined || value === "") return "Not specified";
  if (Array.isArray(value))
    return value.length ? value.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join("\n• ") : "None";
  if (typeof value === "object")
    return Object.entries(value)
      .map(
        ([k, v]) =>
          `${k.replaceAll("_", " ")}: ${Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : v}`,
      )
      .join("\n");
  return String(value);
}

export const EXPECTED_LABELS = {
  status_code: "Status code",
  db_changes: "Database changes",
  side_effects: "Side effects",
  negative_assertions: "Must not happen",
};
const PREFERRED = ["status_code", "db_changes", "side_effects", "negative_assertions"];

/** Keys of a structured expected result: the known ones first, then the rest. */
export function expectedKeys(value) {
  return [
    ...PREFERRED.filter((k) => Object.prototype.hasOwnProperty.call(value, k)),
    ...Object.keys(value).filter((k) => !PREFERRED.includes(k)),
  ];
}

export const isStructured = (value) => !!value && typeof value === "object" && !Array.isArray(value);

/** Everything the detail panel shows, derived from GET /api/test-cases/{id}. */
export function caseDetail(c) {
  const m = c.metadata || {};
  const lineage = (c.features || [])
    .map((f) => `${f.name}${f.version ? ` v${f.version}` : ""}${f.origin ? ` · ${f.origin}` : ""}`)
    .join("\n");
  // Imported when the backend says so, or a feature link's origin is an import.
  const imported = !!(c.imported || (c.features || []).some((f) => String(f.origin || "").toLowerCase().includes("import")));
  return {
    title: caseTitle(c),
    imported,
    description: cleanRequirementText(m.description || m.intent || m.scenario || c.preconditions) || "No separate description was generated.",
    endpoint: [m.method, m.endpoint || m.path].filter(Boolean).join(" "),
    expected: m.expected_result || m.expected_behavior || m.result,
    lineage: (imported ? "Imported from sheet\n" : "") + (lineage || "No feature lineage recorded"),
    steps: c.steps || [],
  };
}
