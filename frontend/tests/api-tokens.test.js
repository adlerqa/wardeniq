import assert from "node:assert/strict";
import test from "node:test";

import {
  EMPTY_TEXT,
  MSG_NAME_REQUIRED,
  MSG_SELECT_PROJECT,
  buildCreateBody,
  formatTimestamp,
  revokeConfirmMessage,
  scopeFromForm,
  tokenAccess,
  tokenCreatedHtml,
  validateTokenForm,
} from "../src/features/users/lib/apiTokens.js";

const projects = [
  { id: "p1", name: "Alpha" },
  { id: "p2", name: "" },
];

test("access: all projects, no projects, and project names with id fallback", () => {
  assert.deepEqual(tokenAccess({ all_projects: true, project_ids: ["p1"] }, projects), {
    kind: "all",
  });
  assert.deepEqual(tokenAccess({ all_projects: false, project_ids: [] }, projects), {
    kind: "none",
  });
  assert.deepEqual(tokenAccess({ all_projects: false }, projects), { kind: "none" });
  assert.deepEqual(
    tokenAccess({ all_projects: false, project_ids: ["p1", "p2", "gone"] }, projects),
    { kind: "projects", names: ["Alpha", "p2", "gone"] },
  );
});

test("scope from the form", () => {
  assert.deepEqual(scopeFromForm("all", ["p1"]), { all_projects: true, project_ids: [] });
  assert.deepEqual(scopeFromForm("some", ["p1", "p2"]), {
    all_projects: false,
    project_ids: ["p1", "p2"],
  });
  assert.deepEqual(scopeFromForm("some", []), { all_projects: false, project_ids: [] });
});

test("validation messages, name first", () => {
  const all = scopeFromForm("all", []);
  const none = scopeFromForm("some", []);
  assert.equal(validateTokenForm({ name: "", scope: none }), MSG_NAME_REQUIRED);
  assert.equal(validateTokenForm({ name: "   ", scope: all }), MSG_NAME_REQUIRED);
  assert.equal(validateTokenForm({ name: "ci", scope: none }), MSG_SELECT_PROJECT);
  assert.equal(validateTokenForm({ name: "ci", scope: all }), null);
  assert.equal(
    validateTokenForm({ name: "ci", scope: scopeFromForm("some", ["p1"]) }),
    null,
  );
  assert.equal(MSG_NAME_REQUIRED, "Name required");
  assert.equal(MSG_SELECT_PROJECT, "Select at least one project, or choose All projects.");
});

test("request body: trimmed name, expires only when given", () => {
  assert.deepEqual(
    buildCreateBody({ name: "  ci  ", role: "editor", expiresDays: "", scope: scopeFromForm("all") }),
    { name: "ci", role: "editor", all_projects: true, project_ids: [] },
  );
  assert.deepEqual(
    buildCreateBody({
      name: "ci",
      role: "viewer",
      expiresDays: " 30 ",
      scope: scopeFromForm("some", ["p1"]),
    }),
    { name: "ci", role: "viewer", all_projects: false, project_ids: ["p1"], expires_in_days: 30 },
  );
});

test("dates are local date-time, or never", () => {
  assert.equal(formatTimestamp(null), "never");
  assert.equal(formatTimestamp(undefined), "never");
  assert.equal(formatTimestamp(0), "never");
  assert.equal(formatTimestamp(1700000000), new Date(1700000000 * 1000).toLocaleString());
});

test("copy text is unchanged", () => {
  assert.equal(
    EMPTY_TEXT,
    "No API tokens yet. Create one above for a CI job or other machine caller.",
  );
  assert.equal(
    revokeConfirmMessage("ci"),
    'Revoke the token "ci"? Any caller using it loses access immediately.',
  );
});

test("token dialog escapes the plaintext into a read-only, click-to-select field", () => {
  const html = tokenCreatedHtml('wq_a"b<c>');
  assert.match(html, /won't be shown again/);
  assert.match(html, /<input readonly value="wq_a&quot;b&lt;c&gt;" onclick="this\.select\(\)"/);
});
