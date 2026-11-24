/**
 * Pure helpers for the spreadsheet import dialogs (was
 * compat/runtime/controllers/15-imports.js).
 */

/** How long the import status is polled before giving up (ms). */
export const IMPORT_POLL_MS = 1500;
export const IMPORT_POLL_LIMIT_MS = 5 * 60 * 1000;

/** "Open forgot password · Enter email" or "3 steps". */
export function stepsText(it) {
  return (it.steps_preview || []).join(" · ") || `${it.steps_count || 0} steps`;
}

/** Source row shown on a review card (row_number, else row_index + 1). */
export function sourceRow(it) {
  return String(it.row_number || it.row_index + 1 || "");
}

/** Pill colour for an imported row's priority. */
export const priorityTone = (p) => (String(p).toLowerCase() === "high" ? "red" : "amber");

/** "feature anchor matches; intent similarity 0.14" — why a row was matched. */
export function breakdownReason(breakdown) {
  if (!breakdown || typeof breakdown !== "object") return "";
  const fmt = (v) => ((v || 0).toFixed ? v.toFixed(2) : v);
  const parts = [];
  if (breakdown.feature_anchor) parts.push("feature anchor matches");
  if (breakdown.route_family) parts.push("route family matches feature context");
  if (breakdown.intent_similarity) parts.push(`intent similarity ${fmt(breakdown.intent_similarity)}`);
  if (breakdown.title_similarity) parts.push(`title similarity ${fmt(breakdown.title_similarity)}`);
  return parts.join("; ");
}

/** Review decisions seeded from the scorer: "matched" rows start included. */
export function initialReview(items) {
  return items.map((it) => ({
    rid: it.project_imported_row_id || null,
    hash: it.identity_hash || null,
    included: it.action === "matched",
    note: "",
  }));
}

/** Body of POST …/tests/import/{id}/review. */
export function reviewPayload(review) {
  return {
    reviews: review.map((r) => ({
      project_imported_row_id: r.rid,
      identity_hash: r.hash,
      action: r.included ? "include" : "exclude",
      note: r.note || "",
    })),
  };
}

/** KPI tiles of a finished import: [label, value, tone, icon]. */
export function importKpis(items, data) {
  return [
    ["Included", items.filter((i) => i.action === "matched").length, "green", "OK"],
    ["Stored for later", items.filter((i) => i.action !== "matched").length, "amber", "BOX"],
    ["Rejected", data.rejected_count || 0, "red", "!"],
    ["Duplicate merges", items.filter((i) => i.already_uploaded).length, "purple", "NET"],
  ];
}

/** Library rows sorted by file, then sheet, then best score first. */
export function sortLibrary(items) {
  return [...items].sort(
    (a, b) =>
      String(a.original_filename || "").localeCompare(String(b.original_filename || "")) ||
      String(a.sheet || "").localeCompare(String(b.sheet || "")) ||
      (b.score || 0) - (a.score || 0),
  );
}

/** Rows grouped per uploaded sheet, in first-seen order. */
export function libraryGroups(items) {
  const groups = new Map();
  for (const it of items) {
    const key = `${it.feature_import_id || ""}::${it.original_filename || ""}::${it.sheet || ""}`;
    if (!groups.has(key))
      groups.set(key, {
        key,
        feature_import_id: it.feature_import_id || "",
        original_filename: it.original_filename || "",
        sheet: it.sheet || "",
        rows: [],
      });
    groups.get(key).rows.push(it);
  }
  return Array.from(groups.values());
}

/** Hashes to add to / remove from the feature to reach the desired state. */
export function libraryChanges(items, desired) {
  return {
    add: items.filter((it) => !it.is_in_feature && desired[it.identity_hash]).map((it) => it.identity_hash),
    remove: items.filter((it) => it.is_in_feature && !desired[it.identity_hash]).map((it) => it.identity_hash),
  };
}

/** KPI tiles of the library dialog. */
export function libraryKpis(items, desired, groupCount) {
  const included = items.filter((it) => desired[it.identity_hash]).length;
  return [
    ["Sheets", groupCount, "green", "DOC"],
    ["Rows", items.length, "purple", "GRID"],
    ["Included", included, "green", "OK"],
    ["Stored for later", items.length - included, "amber", "BOX"],
  ];
}
