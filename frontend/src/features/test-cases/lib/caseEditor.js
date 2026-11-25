/**
 * Pure helpers for the test case editor and case delete (was 04-test-cases.js
 * / 07-library-and-crud.js).
 */
import { prioLabel, typeLabel } from "./testCases.js";

/** The PUT / POST body: trimmed fields, lower-cased tags, empty steps dropped. */
export function editorBody(form, steps) {
  return {
    title: form.title.trim(),
    type: form.type,
    priority: form.prio,
    preconditions: form.pre.trim(),
    tags: form.tags
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean),
    steps: steps
      .filter((s) => s.action || s.expected)
      .map((s) => (s.id ? { id: s.id, action: s.action, expected: s.expected } : { action: s.action, expected: s.expected })),
  };
}

/** Second line of the save confirmation. */
export const reviewLine = (body, sharedWith) =>
  `${typeLabel(body.type)} · ${prioLabel(body.priority)} · ${body.steps.length} step${body.steps.length === 1 ? "" : "s"}${
    sharedWith > 1 ? ` · linked to ${sharedWith} features` : ""
  }`;

/** Move the step at `from` to `to`. */
export function moveStep(steps, from, to) {
  const next = steps.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export const INHERITED_ORIGINS = ["reused", "carried", "carried_repaired", "inherited", "adapted"];
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** Copy and labels of the delete dialog: remove from the feature in scope, or delete. */
export function deletePlan(c, scopedFeature) {
  const links = c.shared_with_features || 0;
  const scopedLink = (c.features || []).find((f) => f.id === scopedFeature);
  if (scopedLink) {
    const others = links - 1;
    return {
      scoped: true,
      links,
      name: scopedLink.name,
      title: "Remove testcase from this feature",
      copy:
        links > 1
          ? `This removes “${c.title}” only from ${scopedLink.name}. Its ${plural(others, "other feature link")} will stay intact.`
          : `This is the testcase's only feature link, so removing it from ${scopedLink.name} will also remove the orphaned testcase.`,
      origin: INHERITED_ORIGINS.includes(scopedLink.origin) ? "Inherited / reused here" : "Created here",
      confirmLabel: `Remove from ${scopedLink.name}`,
      secondaryLabel: links > 1 ? "Delete everywhere" : null,
    };
  }
  return {
    scoped: false,
    links,
    title: "Delete testcase",
    copy:
      links > 1
        ? `This is a global delete. “${c.title}” will be removed from all ${links} linked features.`
        : `“${c.title}” will be permanently deleted.`,
    confirmLabel: links > 1 ? "Delete from all features" : "Delete testcase",
  };
}
