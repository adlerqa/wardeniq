import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

import {
  VIEWER_TIP,
  applyRoleDom,
  enforceViewerReadOnly,
  fmtDate,
  inviteRows,
  passwordProblem,
} from "../src/features/auth/lib/identity.js";

function page() {
  const { window } = new JSDOM(`<!doctype html><body>
    <div id="usermenu" hidden></div><div id="ro-banner" hidden></div>
    <nav><button data-view="users" data-admin="1" hidden></button><button data-view="config" data-admin="1"></button></nav>
    <section class="view" hidden><button>Delete hidden view</button></section>
    <section class="view"><button>Create project</button><button>Cancel</button><button>Export CSV</button>
      <button>View details</button><button title="Keep me" class="needs-editor">x</button><button></button></section>
  </body>`);
  return window.document;
}

test("applyRoleDom: admin sees admin nav, viewer gets the banner and body class", () => {
  const doc = page();
  applyRoleDom({ email: "admin", role: "admin" }, doc);
  assert.equal(doc.getElementById("usermenu").hidden, false);
  assert.deepEqual([...doc.querySelectorAll("nav button")].map((b) => b.hidden), [false, false]);
  assert.equal(doc.getElementById("ro-banner").hidden, true);
  applyRoleDom({ email: "v", role: "viewer" }, doc);
  assert.deepEqual([...doc.querySelectorAll("nav button")].map((b) => b.hidden), [true, true]);
  assert.equal(doc.getElementById("ro-banner").hidden, false);
  assert.equal(doc.body.className, "role-viewer");
  applyRoleDom({ email: "e" }, doc); // no role counts as viewer
  assert.equal(doc.body.className, "role-viewer");
  applyRoleDom({ email: "e", role: "editor" }, doc);
  assert.equal(doc.body.className, "role-editor");
});

test("enforceViewerReadOnly marks write buttons in the visible view and explains why", () => {
  const doc = page();
  enforceViewerReadOnly({ role: "viewer" }, doc);
  const visible = [...doc.querySelectorAll(".view:not([hidden]) button")];
  assert.deepEqual(visible.map((b) => b.classList.contains("needs-editor")), [true, false, true, false, true, false]);
  assert.equal(doc.querySelector(".view[hidden] button").classList.contains("needs-editor"), false);
  assert.ok(visible.filter((b) => b.classList.contains("needs-editor")).every((b) => b.title === VIEWER_TIP));
  enforceViewerReadOnly({ role: "editor" }, doc);
  assert.equal(visible[4].title, "Keep me");
  assert.equal(visible[0].hasAttribute("title"), false);
});

test("change-password checks and invite rows", () => {
  assert.equal(passwordProblem("", "a", "a"), "Enter your current password.");
  assert.equal(passwordProblem("o", "", ""), "Enter a new password.");
  assert.equal(passwordProblem("o", "a", "b"), "New passwords don't match.");
  assert.equal(passwordProblem("o", "a", "a"), "");
  assert.equal(fmtDate(0), "");
  assert.deepEqual(inviteRows({ role: "editor", invited_by: { name: "Al", email: "al@x.io" } }), [
    ["Invited by", { text: "Al (al@x.io)" }],
    ["Workspace", { text: "WardenIQ" }],
    ["Role granted", { role: "editor" }],
    ["Sent", { text: "—" }],
  ]);
  assert.equal(inviteRows({ invited_by: { email: "b@x.io" } })[0][1].text, "b@x.io");
  assert.equal(inviteRows({})[0][1].text, "an administrator");
});
