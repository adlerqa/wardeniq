import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

import {
  HINT_ADMIN,
  accessDialogHtml,
  auditDanger,
  auditDetail,
  countActiveAdmins,
  deliveryFailed,
  inviteHint,
  inviteScope,
  lastLoginText,
  matchesFilters,
  readAccessDialog,
  roleChangeMessage,
  rowActions,
  userAccess,
  userStatus,
  validateInvite,
} from "../src/features/users/lib/users.js";

const projects = [{ id: "p1", name: "Alpha" }, { id: "p2", name: "" }];

test("invite hint, scope and validation", () => {
  assert.equal(inviteHint("admin", "some"), HINT_ADMIN);
  assert.equal(inviteHint("viewer", "some"), "Select the projects this user can access.");
  assert.equal(inviteHint("editor", "all"), "This user will have access to every project.");
  assert.deepEqual(inviteScope("admin", "some", ["p1"]), { all_projects: true, project_ids: [] });
  assert.deepEqual(inviteScope("viewer", "some", ["p1"]), { all_projects: false, project_ids: ["p1"] });
  assert.equal(validateInvite(" ", inviteScope("viewer", "all")), "Email required");
  assert.equal(
    validateInvite("a@b.c", inviteScope("viewer", "some", [])),
    "Select at least one project, or choose All projects.",
  );
  assert.equal(validateInvite("a@b.c", inviteScope("viewer", "all")), null);
  assert.equal(deliveryFailed({ delivery: "refused" }), true);
  assert.equal(deliveryFailed({ delivery: "sent" }), false);
});

test("filters", () => {
  const pending = { email: "p@x.io", name: "Pat", role: "viewer", active: true, invite_status: "pending" };
  const active = { email: "a@x.io", name: "Ann", role: "admin", active: true };
  const off = { email: "d@x.io", name: "Dan", role: "editor", active: false };
  assert.equal(matchesFilters(pending, { q: "PAT" }), true);
  assert.equal(matchesFilters(pending, { q: "zzz" }), false);
  assert.equal(matchesFilters(active, { role: "editor" }), false);
  assert.equal(matchesFilters(pending, { status: "pending" }), true);
  assert.equal(matchesFilters(pending, { status: "active" }), false);
  assert.equal(matchesFilters(active, { status: "active" }), true);
  assert.equal(matchesFilters(off, { status: "disabled" }), true);
  assert.equal(matchesFilters(pending, { status: "disabled" }), false);
});

test("access, status and last login", () => {
  assert.deepEqual(userAccess({ role: "admin" }, projects), { kind: "admin" });
  assert.deepEqual(userAccess({ role: "viewer", all_projects: true }, projects), { kind: "all" });
  assert.deepEqual(userAccess({ role: "viewer", project_ids: [] }, projects), { kind: "none" });
  assert.deepEqual(userAccess({ role: "viewer", project_ids: ["p1", "p2", "x"] }, projects), {
    kind: "projects",
    names: ["Alpha", "p2", "x"],
  });
  assert.equal(userStatus({ invite_status: "pending", active: true }), "pending");
  assert.equal(userStatus({ active: false }), "disabled");
  assert.equal(lastLoginText({ invite_status: "pending" }), "awaiting first sign-in");
  assert.equal(lastLoginText({}), "never");
  assert.equal(lastLoginText({ last_login: 1700000000 }), new Date(1700000000 * 1000).toLocaleString());
});

test("row actions", () => {
  const me = { id: "me", role: "admin", active: true };
  assert.deepEqual(rowActions(me, { selfId: "me", activeAdmins: 1 }), ["unlock"]);
  assert.deepEqual(rowActions(me, { selfId: "me", activeAdmins: 2 }), ["disable"]);
  assert.deepEqual(rowActions({ id: "a2", role: "admin", active: true }, { selfId: "me", activeAdmins: 2 }), [
    "disable",
    "delete",
  ]);
  assert.deepEqual(rowActions({ id: "p", role: "viewer", invite_status: "pending" }, { selfId: "me", activeAdmins: 1 }), [
    "access",
    "resend",
    "cancel",
  ]);
  assert.deepEqual(rowActions({ id: "d", role: "editor", active: false }, { selfId: "me", activeAdmins: 1 }), [
    "access",
    "enable",
    "delete",
  ]);
  assert.equal(
    countActiveAdmins([{ role: "admin", active: true }, { role: "admin", active: false }, { role: "viewer", active: true }]),
    1,
  );
});

test("role change message escapes the name like before", () => {
  assert.equal(
    roleChangeMessage("Tom & Jerry", "editor", ""),
    'Change Tom &amp; Jerry\'s role to "editor"? They\'ll be re-authenticated with the new permissions.',
  );
  assert.equal(
    roleChangeMessage("Ann", "viewer", "Read-only."),
    'Change Ann\'s role to "viewer"? Read-only. They\'ll be re-authenticated with the new permissions.',
  );
});

test("audit helpers", () => {
  assert.equal(auditDetail({ detail: "password" }), "password");
  assert.equal(auditDetail({ old: { a: 1 }, new: { a: 2 } }), 'from {"a":1} to {"a":2}');
  assert.equal(auditDetail({}), "");
  assert.equal(auditDanger("user.deleted"), true);
  assert.equal(auditDanger("auth.login"), false);
});

test("access dialog html keeps the ma-* contract and reads back the choice", () => {
  const dom = new JSDOM("<body></body>");
  const doc = dom.window.document;
  doc.body.innerHTML = accessDialogHtml({ all_projects: false, project_ids: ["p1"] }, projects);
  assert.ok(doc.querySelector('input[name="ma-scope"][value="some"]').checked);
  assert.ok(doc.querySelector('#ma-list input[data-pid="p1"]').checked);
  assert.deepEqual(readAccessDialog(doc), { all_projects: false, project_ids: ["p1"] });
  doc.querySelector('input[name="ma-scope"][value="all"]').checked = true;
  assert.deepEqual(readAccessDialog(doc), { all_projects: true, project_ids: [] });
  doc.body.innerHTML = accessDialogHtml({ all_projects: true }, []);
  assert.match(doc.body.textContent, /No projects exist yet\./);
  assert.ok(doc.getElementById("ma-list").hidden);
  dom.window.close();
});
