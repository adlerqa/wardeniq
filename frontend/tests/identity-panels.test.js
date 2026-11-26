import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

const dom = new JSDOM("<!doctype html><body><div id=\"login\"></div></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));
const bundle = async (rel) =>
  (await build({
    entryPoints: [fileURLToPath(new URL(rel, import.meta.url))], bundle: true, write: false, format: "cjs",
    platform: "neutral", jsx: "automatic", external: ["react", "react/jsx-runtime", "react-dom"],
    loader: { ".css": "empty" }, logLevel: "silent",
  })).outputFiles[0].text;
const sources = {
  header: await bundle("../src/layouts/Header.jsx"),
  password: await bundle("../src/components/overlays/modals/PasswordModal.jsx"),
  invite: await bundle("../src/features/auth/components/InviteGate.jsx"),
};

async function mount(t, name, routes) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { req: [], win: [] };
  let me = null;
  Object.assign(window, {
    toast: (m) => calls.win.push(["toast", m]),
    getCurrentUser: () => me,
    setCurrentUser: (u) => { me = u; },
    showLogin: () => calls.win.push(["showLogin"]),
    startApp: () => calls.win.push(["startApp"]),
    navigateTo: (v) => calls.win.push(["nav", v]),
    getCurrentViewName: () => "users",
    uiConfirm: async () => true,
  });
  const reply = (status, body) => ({ status, ok: status < 400, text: async () => JSON.stringify(body), json: async () => body });
  async function fakeFetch(path, opts = {}) {
    calls.req.push([opts.method || "GET", path, opts.body ? JSON.parse(opts.body) : null]);
    const r = routes[path];
    return typeof r === "function" ? r() : reply(200, r || {});
  }
  const module = { exports: {} };
  vm.runInNewContext(sources[name], {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, clearTimeout,
  });
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(module.exports.default)));
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  const flush = (fn) =>
    act(async () => {
      await fn?.();
      for (let i = 0; i < 8; i++) await settle();
    });
  const setValue = (el, v) =>
    flush(() => {
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v);
      el.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
  return { $: (s) => container.querySelector(s), calls, flush, setValue, reply, setMe: (u) => { me = u; }, me: () => me };
}

test("header: checkAuth / applyRole fill the user menu; refreshMe follows a role change", async (t) => {
  let meUser = { email: "verylongemailaddress@example.com", role: "admin" };
  const h = await mount(t, "header", { "/api/auth/me": () => ({ status: 200, ok: true, text: async () => JSON.stringify({ user: meUser }), json: async () => ({ user: meUser }) }) });
  assert.equal(h.$("#user-email").textContent, "");
  assert.equal(await window.checkAuth(), true);
  await h.flush();
  assert.equal(document.getElementById("login").hidden, true);
  assert.equal(h.$("#user-email").textContent, "verylongemailaddress@example.com");
  assert.equal(h.$("#user-email").title, "verylongemailaddress@example.com");
  assert.equal(h.$("#user-role").className, "rolebadge admin");
  assert.equal(h.$("#change-pw-btn").hidden, true);
  h.setMe({ email: "admin", role: "admin" });
  await h.flush(() => window.applyRole());
  assert.equal(h.$("#change-pw-btn").hidden, false);
  meUser = { email: "admin", role: "editor" };
  await h.flush(() => window.refreshMe());
  assert.equal(h.$("#user-role").textContent, "editor");
  assert.deepEqual(h.calls.win, [["toast", 'Your role is now "editor".'], ["nav", "dashboard"]]);
  h.calls.win.length = 0;
  await h.flush(() => window.refreshMe());
  assert.deepEqual(h.calls.win, []);
});

test("password dialog: checks, saves, resolves; mandatory mode can't be dismissed", async (t) => {
  const h = await mount(t, "password", { "/api/auth/change-password": { user: { email: "admin", role: "admin" } } });
  let result = "pending";
  await h.flush(() => { window.openChangePasswordModal(false).then((v) => { result = v; }); });
  assert.ok(h.$("#pwd-modal").classList.contains("show"));
  assert.equal(h.$("#pwd-title").textContent, "Change password");
  await h.flush(() => h.$("#pwd-save").click());
  assert.equal(h.$("#pwd-err").textContent, "Enter your current password.");
  await h.setValue(h.$("#pwd-current"), "old");
  await h.setValue(h.$("#pwd-new"), "n1");
  await h.setValue(h.$("#pwd-confirm"), "n2");
  await h.flush(() => h.$("#pwd-confirm").dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  assert.equal(h.$("#pwd-err").textContent, "New passwords don't match.");
  await h.setValue(h.$("#pwd-confirm"), "n1");
  await h.flush(() => h.$("#pwd-save").click());
  assert.deepEqual(h.calls.req, [["POST", "/api/auth/change-password", { current_password: "old", new_password: "n1" }]]);
  assert.deepEqual(h.calls.win, [["toast", "Password changed."]]);
  assert.equal(result, true);
  assert.equal(h.me().email, "admin");
  assert.equal(h.$("#pwd-modal").classList.contains("show"), false);

  result = "pending";
  await h.flush(() => { window.openChangePasswordModal(true).then((v) => { result = v; }); });
  assert.equal(h.$("#pwd-title").textContent, "Set a new password");
  assert.equal(h.$("#pwd-current").value, "");
  assert.equal(h.$("#pwd-cancel").style.display, "none");
  await h.flush(() => h.$("#pwd-cancel").click());
  assert.equal(result, "pending");
  assert.ok(h.$("#pwd-modal").classList.contains("show"));

  result = "pending";
  await h.flush(() => { window.openChangePasswordModal(false).then((v) => { result = v; }); });
  await h.flush(() => h.$("#pwd-x").click());
  assert.equal(result, false);
});

test("invite gate: shows a pending invite, accept starts the app, decline signs out", async (t) => {
  let accept = () => ({ status: 400, ok: false, text: async () => JSON.stringify({ detail: "Expired" }) });
  const h = await mount(t, "invite", {
    "/api/auth/my-invite": { invite: { pending: true, workspace: "Acme <co>", role: "editor", invited_by: { name: "Al <b>", email: "al@x.io" } } },
    "/api/auth/invite/accept": () => accept(),
    "/api/auth/invite/decline": { ok: true },
  });
  window.applyRole = () => h.calls.win.push(["applyRole"]);
  let shown;
  await h.flush(async () => { shown = await window.maybeShowInvite(); });
  assert.equal(shown, true);
  assert.equal(h.$("#invite-gate").hidden, false);
  assert.equal(h.$("#invite-workspace").textContent, "Acme <co>");
  assert.equal(h.$("#invite-meta").innerHTML,
    '<div class="row"><span>Invited by</span><span>Al &lt;b&gt; (al@x.io)</span></div>' +
    '<div class="row"><span>Workspace</span><span>Acme &lt;co&gt;</span></div>' +
    '<div class="row"><span>Role granted</span><span><span class="rolebadge editor">editor</span></span></div>' +
    '<div class="row"><span>Sent</span><span>—</span></div>');
  await h.flush(() => h.$("#invite-accept").click());
  assert.equal(h.$("#invite-err").textContent, "Expired");
  accept = () => h.reply(200, { user: { email: "n@x.io", role: "editor" } });
  await h.flush(() => h.$("#invite-accept").click());
  assert.equal(h.$("#invite-gate").hidden, true);
  assert.deepEqual(h.calls.win, [["applyRole"], ["toast", "Invitation accepted — welcome!"], ["startApp"]]);
  assert.equal(h.me().email, "n@x.io");
  await h.flush(async () => { await window.maybeShowInvite(); });
  h.calls.win.length = 0;
  await h.flush(() => h.$("#invite-decline").click());
  assert.equal(h.$("#invite-gate").hidden, true);
  assert.equal(h.me(), null);
  assert.deepEqual(h.calls.win, [["showLogin"], ["toast", "Invitation declined."]]);
});
