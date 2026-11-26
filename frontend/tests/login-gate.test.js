import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

const dom = new JSDOM("<!doctype html><body><div id=\"usermenu\"></div></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(new URL("../src/features/auth/components/LoginGate.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry], bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], loader: { ".css": "empty" }, logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

async function mount(t, routes) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { req: [], win: [] };
  Object.assign(window, {
    toast: () => {},
    setCurrentUser: (u) => calls.win.push(["user", u && u.email]),
    applyRole: () => calls.win.push(["applyRole"]),
    maybeShowInvite: async () => { calls.win.push(["maybeShowInvite"]); return false; },
    startApp: () => calls.win.push(["startApp"]),
  });
  const reply = (status, body) => ({ status, ok: status < 400, text: async () => JSON.stringify(body), json: async () => body });
  async function fakeFetch(path, opts = {}) {
    calls.req.push([opts.method || "GET", path, opts.body ? JSON.parse(opts.body) : null]);
    const r = routes[path];
    if (!r) return reply(404, { detail: "unmocked" });
    return typeof r === "function" ? r(opts) : reply(200, r);
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch,
    setTimeout, clearTimeout, sessionStorage: window.sessionStorage,
  });
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(module.exports.default)));
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  const $ = (s) => container.querySelector(s);
  const flush = (fn) =>
    act(async () => {
      await fn?.();
      for (let i = 0; i < 8; i++) await settle();
    });
  const type = (sel, v) => { $(sel).value = v; };
  const visible = () => ["login-step1", "login-step2", "login-password", "login-forgot-nosmtp", "login-forgot-step1", "login-forgot-step2"]
    .filter((id) => !$("#" + id).hidden);
  return { $, calls, flush, type, visible, reply };
}

test("password sign-in when SMTP is off: checks, then hands off to the app", async (t) => {
  const h = await mount(t, {
    "/api/auth/boot-status": { ready: true },
    "/api/auth/smtp-status": { smtp_setup: false },
    "/api/auth/login-password": { user: { email: "admin", role: "admin" } },
  });
  await h.flush(() => window.showLogin());
  assert.equal(h.$("#login").hidden, false);
  assert.equal(document.getElementById("usermenu").hidden, true);
  assert.deepEqual(h.calls.req.map((c) => c[1]), ["/api/auth/boot-status", "/api/auth/smtp-status"]);
  assert.deepEqual(h.visible(), ["login-password"]);
  assert.equal(h.$("#login-intro").textContent, "Sign in with your admin credentials. (SMTP is not configured)");
  await h.flush(() => h.$("#login-signin").click());
  assert.equal(h.$("#login-err").textContent, "Enter your username");
  h.type("#login-username", " admin ");
  await h.flush(() => h.$("#login-signin").click());
  assert.equal(h.$("#login-err").textContent, "Enter your password");
  h.type("#login-pw", "pw1");
  h.calls.win.length = 0;
  await h.flush(() => h.$("#login-pw").dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  assert.deepEqual(h.calls.req.at(-1), ["POST", "/api/auth/login-password", { username: "admin", password: "pw1" }]);
  assert.deepEqual(h.calls.win, [["user", "admin"], ["applyRole"], ["maybeShowInvite"], ["startApp"]]);
  assert.equal(h.$("#login").hidden, true);
});

test("one-time code: send shows the demo code escaped, paste fills the boxes and verifies", async (t) => {
  const h = await mount(t, {
    "/api/auth/boot-status": { ready: false, detail: "Mongo <down>." },
    "/api/auth/smtp-status": { smtp_setup: true },
    "/api/auth/request-otp": { sent: true, delivery: "log", dev_code: "<12>" },
    "/api/auth/verify-otp": { user: { email: "a@x.io", role: "editor" } },
    "/api/auth/me": { user: { email: "a@x.io", role: "viewer" } },
  });
  await h.flush(() => window.showLogin({ msg: "Invited <b>" }));
  assert.deepEqual(h.visible(), ["login-step1"]);
  assert.equal(h.$("#login-boot-status").hidden, false);
  assert.equal(h.$("#login-boot-status").textContent, "Mongo <down>.");
  assert.equal(h.$("#login-msg").textContent, "Invited <b>");
  h.type("#login-email", " a@x.io ");
  await h.flush(() => h.$("#login-send").click());
  assert.deepEqual(h.visible(), ["login-step2"]);
  assert.equal(h.$("#login-to").textContent, "a@x.io");
  assert.match(h.$("#login-msg").innerHTML, /Demo sign-in code: <b [^>]*>&lt;12&gt;<\/b>/);
  await h.flush(() => h.$("#login-verify").click());
  assert.equal(h.$("#login-err").textContent, "Enter the code");
  const boxes = [...h.$("#login-code").querySelectorAll("input")];
  const paste = new window.Event("paste", { bubbles: true, cancelable: true });
  paste.clipboardData = { getData: () => "code: 654-321" };
  h.calls.win.length = 0;
  await h.flush(() => boxes[0].dispatchEvent(paste));
  assert.equal(boxes.map((b) => b.value).join(""), "654321");
  assert.deepEqual(h.calls.req.slice(-2).map((c) => [c[1], c[2]]), [
    ["/api/auth/verify-otp", { email: "a@x.io", code: "654321" }],
    ["/api/auth/me", null],
  ]);
  assert.deepEqual(h.calls.win, [["user", "a@x.io"], ["applyRole"], ["maybeShowInvite"], ["startApp"]]);
});

test("one-time code: a session that didn't stick returns to sign-in with an explanation", async (t) => {
  const h = await mount(t, {
    "/api/auth/boot-status": { ready: true },
    "/api/auth/smtp-status": { smtp_setup: true },
    "/api/auth/request-otp": { sent: true, message: "If that email exists, a code is on its way." },
    "/api/auth/verify-otp": { user: { email: "a@x.io" } },
    "/api/auth/me": () => ({ status: 401, ok: false, text: async () => "{}", json: async () => ({}) }),
  });
  await h.flush(() => window.showLogin());
  h.type("#login-email", "a@x.io");
  await h.flush(() => h.$("#login-send").click());
  assert.equal(h.$("#login-sent-text").textContent, "We emailed a 6-digit code to ");
  assert.equal(h.$("#login-msg").textContent, "If that email exists, a code is on its way.");
  const boxes = [...h.$("#login-code").querySelectorAll("input")];
  boxes.forEach((b, i) => { b.value = String(i); });
  const err = console.error;
  console.error = () => {};
  try {
    await h.flush(() => boxes[5].dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  } finally {
    console.error = err;
  }
  assert.deepEqual(h.visible(), ["login-step1"]);
  assert.match(h.$("#login-err").textContent, /^Your code was accepted, but the login session could not be saved/);
  assert.equal(boxes.map((b) => b.value).join(""), "");
});

test("forgot password: prefilled target, reset code request, then the new password", async (t) => {
  const h = await mount(t, {
    "/api/auth/boot-status": { ready: true },
    "/api/auth/smtp-status": { smtp_setup: true },
    "/api/auth/request-password-reset": { smtp_configured: true },
    "/api/auth/reset-password": { message: "Done" },
  });
  await h.flush(() => window.showLogin());
  h.type("#login-username", " bob ");
  await h.flush(() => h.$("#login-forgot-btn").click());
  assert.deepEqual(h.visible(), ["login-forgot-step1"]);
  assert.equal(h.$("#reset-target").value, "bob");
  await h.flush(() => h.$("#reset-request-btn").click());
  assert.deepEqual(h.visible(), ["login-forgot-step2"]);
  assert.equal(h.$("#login-msg").textContent, "Reset code sent. Please check your email.");
  await h.flush(() => h.$("#reset-submit-btn").click());
  assert.equal(h.$("#login-err").textContent, "Enter the 6-digit reset code");
  h.type("#reset-code", " 123456 ");
  h.type("#reset-new-pw", "np");
  await h.flush(() => h.$("#reset-submit-btn").click());
  assert.deepEqual(h.calls.req.find((c) => c[1] === "/api/auth/reset-password")[2],
    { username_or_email: "bob", code: "123456", new_password: "np" });
  assert.deepEqual(h.visible(), ["login-step1"]);
});

test("forgot password without SMTP: master-secret reset", async (t) => {
  const h = await mount(t, {
    "/api/auth/boot-status": { ready: true },
    "/api/auth/smtp-status": { smtp_setup: false },
    "/api/auth/reset-password-master": () => ({ status: 403, ok: false, text: async () => JSON.stringify({ detail: "Wrong secret" }) }),
  });
  await h.flush(() => window.showLogin());
  await h.flush(() => h.$("#login-forgot-btn").click());
  assert.deepEqual(h.visible(), ["login-forgot-nosmtp"]);
  await h.flush(() => h.$("#reset-master-submit-btn").click());
  assert.equal(h.$("#login-err").textContent, "Enter App Master Secret (APP_SECRET)");
  h.type("#reset-master-secret", " s ");
  h.type("#reset-master-new-pw", "np");
  await h.flush(() => h.$("#reset-master-submit-btn").click());
  assert.deepEqual(h.calls.req.at(-1), ["POST", "/api/auth/reset-password-master", { username: "admin", app_secret: "s", new_password: "np" }]);
  assert.equal(h.$("#login-err").textContent, "Wrong secret");
  assert.equal(h.$("#reset-master-submit-btn").disabled, false);
});
