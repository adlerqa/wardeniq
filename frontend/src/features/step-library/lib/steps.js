/**
 * Pure logic for the Step Library screen, ported from the compat
 * 05-step-workflows.js and the step half of 07-library-and-crud.js.
 * Unit-tested in frontend/tests/steps.test.js.
 */

export const MSG_ACTION_REQUIRED = "Action / Description is required";
export const NO_EXPECTED = "No separate expected result defined.";
export const NO_CASES = "Not referenced by any active test cases.";

const PREFIXES = [
  ["given ", "given"],
  ["when ", "when"],
  ["then ", "then"],
  ["and ", "and"],
  ["but ", "and"],
];

/** "given" | "when" | "then" | "and" (And/But) | "other", from the action's first word. */
export function stepType(action) {
  const clean = (action || "").trim().toLowerCase();
  for (const [p, t] of PREFIXES) if (clean.startsWith(p)) return t;
  return "other";
}

/** The action without its Given/When/Then/And/But keyword. */
export function stepBase(action) {
  const clean = (action || "").trim();
  const lower = clean.toLowerCase();
  for (const [p] of PREFIXES) if (lower.startsWith(p)) return clean.slice(p.length).trim();
  return clean;
}

const KEYWORD = { given: "Given", when: "When", then: "Then" };

/**
 * How a step reads in the list: { type, keyword | null, text }. Only
 * Given/When/Then get a coloured keyword; And/But and plain actions show the
 * base text, capitalised.
 */
export function stepLine(action) {
  const type = stepType(action);
  const keyword = KEYWORD[type] || null;
  let text = stepBase(action);
  if (!keyword && text) text = text.charAt(0).toUpperCase() + text.slice(1);
  return { type, keyword, text };
}

/** Label of the type badge in the detail pane. */
export function typeLabel(type) {
  if (type === "other") return "Action";
  if (type === "and") return "And/But";
  return type.toUpperCase();
}

/** List filters: search (action or expected), type ("Given".."Other"), usage ("used" | "unused"). */
export function filterSteps(steps, { q = "", type = "", usage = "" } = {}) {
  const query = q.trim().toLowerCase();
  return steps.filter((s) => {
    if (
      query &&
      !(s.action || "").toLowerCase().includes(query) &&
      !(s.expected || "").toLowerCase().includes(query)
    )
      return false;
    const t = stepType(s.action);
    if (type) {
      if (type === "Other") {
        if (["given", "when", "then", "and"].includes(t)) return false;
      } else if (type === "And") {
        if (t !== "and") return false;
      } else if (t !== type.toLowerCase()) return false;
    }
    if (usage === "used" && s.used_in_cases === 0) return false;
    if (usage === "unused" && s.used_in_cases > 0) return false;
    return true;
  });
}

/** Usage pill: { unused, label, title }. */
export function usagePill(used) {
  if (used > 0) {
    const plural = used === 1 ? "" : "s";
    return { unused: false, label: `${used} case${plural}`, title: `Used in ${used} test case${plural}` };
  }
  return { unused: true, label: "Unused", title: "Not referenced by any test case yet" };
}

/** Fields of the edit dialog for an existing step. */
export function editFields(step) {
  const t = stepType(step.action);
  return {
    prefix: ["given", "when", "then", "and"].includes(t) ? step.action.split(" ")[0] : "",
    action: stepBase(step.action),
    expected: step.expected || "",
    warn:
      step.used_in_cases > 0
        ? `Warning: This step is referenced by ${step.used_in_cases} active testcase(s). Updating it will immediately affect all of them.`
        : "",
  };
}

/** Action sent to the API: the prefix (if any) and the trimmed text. */
export function composeAction(prefix, rawAction) {
  const raw = (rawAction || "").trim();
  return prefix ? `${prefix} ${raw}` : raw;
}

export const blockedDeleteMessage = (n) => `Cannot delete: Step is referenced by ${n} case(s).`;
export const updatedMessage = (n) => `Updated — affects ${n} case(s) ✓`;
