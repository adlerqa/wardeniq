import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

import { handleInviteLink, runBoot, startApp, watchFields } from "../src/app/boot.js";

function deps(over = {}) {
  const log = [];
  let user = over.user === undefined ? { email: "a@x.io", role: "editor" } : over.user;
  const store = new Map(over.nav ? [["wq_nav", JSON.stringify(over.nav)]] : []);
  const session = new Map();
  const d = {
    log, session,
    api: async (p) => { log.push(["api", p]); return over.apiReply ? over.apiReply(p) : { configured: true }; },
    fetch: async (u) => { log.push(["fetch", u]); return over.verify || { ok: false }; },
    currentUser: () => user,
    checkAuth: async () => { log.push(["checkAuth"]); if (over.signedInAs !== undefined) user = over.signedInAs; return !!user; },
    maybeShowInvite: async () => { log.push(["maybeShowInvite"]); return !!over.invite; },
    showLogin: (o) => log.push(["showLogin", o || null]),
    toast: (m, e) => log.push(["toast", m, e]),
    openChangePasswordModal: async (m) => { log.push(["password", m]); return true; },
    refreshStatus: () => log.push(["refreshStatus"]),
    navigateTo: (v) => log.push(["nav", v]),
    setCurrentProject: (p) => log.push(["project", p]),
    setCurrentFeature: (f) => log.push(["feature", f]),
    location: { hash: over.hash || "", search: over.search || "", pathname: over.pathname || "/" },
    history: { replaceState: (_s, _t, url) => log.push(["url", url]) },
    storage: { getItem: (k) => store.get(k) ?? null },
    session: { setItem: (k, v) => session.set(k, v), removeItem: (k) => session.delete(k), get: (k) => session.get(k) },
    document: { getElementById: (id) => (id === "login-email" ? (d.emailField ||= { value: "" }) : null) },
  };
  return d;
}

test("startApp: mandatory password first, then the saved project / feature and view", async () => {
  const d = deps({ user: { email: "admin", role: "editor", must_change_password: true }, nav: { project: "p1", feature: "f1", view: "features" } });
  await startApp(d);
  assert.deepEqual(d.log, [["password", true], ["refreshStatus"], ["project", "p1"], ["feature", "f1"], ["nav", "features"]]);
});

test("startApp: the URL hash wins over the saved view; an unconfigured admin goes to Configuration", async () => {
  const d = deps({ hash: "#cases", nav: { view: "features" } });
  await startApp(d);
  assert.deepEqual(d.log.at(-1), ["nav", "cases"]);
  const admin = deps({ user: { email: "admin", role: "admin" }, apiReply: (p) => (p === "/api/settings" ? { configured: false } : { llm: { health: { ok: false } } }) });
  await startApp(admin);
  assert.deepEqual(admin.log.slice(1), [["api", "/api/settings"], ["api", "/api/status"], ["nav", "config"]]);
  const fresh = deps({ user: null });
  await startApp(fresh);
  assert.deepEqual(fresh.log, [["refreshStatus"], ["nav", "dashboard"]]);
});

test("runBoot: signed in → invite gate → app; signed out stops at sign-in", async () => {
  const d = deps({ nav: { view: "projects" } });
  await runBoot(d);
  assert.deepEqual(d.log.map((x) => x[0]), ["checkAuth", "maybeShowInvite", "refreshStatus", "nav"]);
  const invited = deps({ invite: true });
  await runBoot(invited);
  assert.deepEqual(invited.log.map((x) => x[0]), ["checkAuth", "maybeShowInvite"]);
  const out = deps({ user: null });
  await runBoot(out);
  assert.deepEqual(out.log, [["checkAuth"]]);
});

test("invite links: bad token, signed in as the invitee, someone else", async () => {
  const bad = deps({ search: "?token=a b", pathname: "/invite" });
  assert.equal(await handleInviteLink(bad), true);
  assert.deepEqual(bad.log, [
    ["url", "/"], ["fetch", "/api/invite/verify?token=a%20b"], ["showLogin", null],
    ["toast", "This invitation link is invalid or has expired.", true],
  ]);
  assert.equal(bad.session.get("wq_invite_token"), "a b");

  const info = { email: "a@x.io", invite: { workspace: "Acme", role: "editor" } };
  const mine = deps({ search: "?token=t", verify: { ok: true, json: async () => info }, invite: true });
  assert.equal(await handleInviteLink(mine), true);
  assert.deepEqual(mine.log.slice(2).map((x) => x[0]), ["checkAuth", "maybeShowInvite"]);
  assert.equal(mine.session.get("wq_invite_token"), undefined);

  const other = deps({ search: "?token=t", verify: { ok: true, json: async () => info }, signedInAs: null });
  assert.equal(await handleInviteLink(other), true);
  assert.deepEqual(other.log.at(-1), ["showLogin", { msg: "You've been invited to Acme as editor. Sign in as a@x.io to accept." }]);
  assert.equal(other.emailField.value, "a@x.io");

  assert.equal(await handleInviteLink(deps()), false);
});

test("field hardening: existing and later fields, forms", async () => {
  const { window } = new JSDOM('<!doctype html><body><form><input type="password"><select></select></form></body>');
  const doc = window.document;
  const stop = watchFields(doc, window.MutationObserver);
  const pw = doc.querySelector("input");
  assert.equal(pw.getAttribute("autocomplete"), "new-password");
  assert.equal(pw.dataset.wqNoauto, "1");
  assert.equal(doc.querySelector("form").getAttribute("autocomplete"), "off");
  const div = doc.createElement("div");
  div.innerHTML = "<textarea></textarea>";
  doc.body.appendChild(div);
  const t = doc.createElement("input");
  doc.body.appendChild(t);
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual([div.firstChild, t].map((e) => [e.getAttribute("autocomplete"), e.getAttribute("spellcheck"), e.getAttribute("data-lpignore")]),
    [["off", "false", "true"], ["off", "false", "true"]]);
  stop();
  window.close();
});
