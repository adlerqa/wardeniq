import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

// Create the DOM globals before react-dom loads (see api-tokens-panel.test.js).
const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());
// jsdom has no layout, so scrolling is a no-op here.
window.HTMLElement.prototype.scrollIntoView = () => {};

const entry = fileURLToPath(new URL("../src/features/users/pages/UsersPage.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "neutral",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"],
  logLevel: "silent",
});
const code = bundled.outputFiles[0].text;
const require = createRequire(import.meta.url);

const PROJECTS = { projects: [{ id: "p1", name: "Alpha" }, { id: "p2", name: "Beta" }] };
const ME = { id: "u1", email: "admin", name: "Admin", role: "admin", active: true, invite_status: "active", all_projects: true, last_login: 1700000000 };
const PENDING = { id: "u2", email: "pat@x.io", name: "pat", role: "viewer", active: true, invite_status: "pending", all_projects: false, project_ids: ["p2"] };
const OFF = { id: "u3", email: "dan@x.io", name: "Dan", role: "editor", active: false, all_projects: true };
const LOGS = { logs: [
  { ts: 1700000000, action: "user.deleted", actor_email: "admin", target: "x@y.z", old: { role: "viewer" } },
  { ts: 1700000001, action: "auth.login", actor_email: "admin", target: "admin", detail: "password" },
] };

function harness(t, routes, { confirm = true, modalOk = true } = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  for (const k of ["toast", "uiConfirm", "uiModalHTML", "getCurrentUser", "loadUsers", "loadAudit", "loadProjectPicker", "loadApiTokens"])
    delete window[k];
  const ui = [];
  window.getCurrentUser = () => ME;
  window.toast = (...a) => ui.push(["toast", ...a]);
  window.uiConfirm = async (...a) => {
    ui.push(["confirm", ...a]);
    return confirm;
  };
  window.uiModalHTML = async (title, html, label) => {
    ui.push(["modal", title, label]);
    // Mimic the compat modal: the body stays in the DOM after it resolves.
    let m = document.getElementById("hm-body");
    if (!m) {
      m = document.createElement("div");
      m.id = "hm-body";
      document.body.appendChild(m);
    }
    m.innerHTML = html;
    return modalOk;
  };
  const requests = [];
  async function fakeFetch(path, init = {}) {
    const method = init.method || "GET";
    requests.push({ method, path, body: init.body ? JSON.parse(init.body) : undefined });
    const handler = routes[`${method} ${path}`];
    const [status, body] = handler ? handler() : [404, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports, require, window, document, console,
    fetch: fakeFetch, setTimeout, clearTimeout,
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
    document.getElementById("hm-body")?.remove();
  });
  const card = (title) => [...container.querySelectorAll(".card")].find((c) => c.querySelector("h2").textContent === title);
  return {
    container, requests, ui, root, card,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await act(async () => {
        window.loadProjectPicker();
        window.loadUsers();
        window.loadAudit();
      });
    },
    async click(el) {
      await act(async () => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    },
    async type(el, value) {
      const proto = el.tagName === "SELECT" ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      await act(async () => {
        setter.call(el, value);
        el.dispatchEvent(new window.Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
      });
    },
    button: (scope, label) => [...scope.querySelectorAll("button")].find((b) => b.textContent.trim() === label),
  };
}

const base = () => ({
  "GET /api/projects": () => [200, PROJECTS],
  "GET /api/users": () => [200, { users: [ME, PENDING, OFF] }],
  "GET /api/audit-logs?limit=100": () => [200, LOGS],
});

test("registers the navigateTo hooks without fetching, and removes them on unmount", async (t) => {
  const h = harness(t, base());
  await h.mount();
  assert.equal(typeof window.loadUsers, "function");
  assert.equal(typeof window.loadAudit, "function");
  assert.equal(typeof window.loadProjectPicker, "function");
  assert.deepEqual(h.requests, []);
  assert.match(h.card("Audit log").textContent, /Loading…/);
  await act(async () => h.root.unmount());
  assert.equal(window.loadUsers, undefined);
  assert.equal(window.loadAudit, undefined);
  assert.equal(window.loadProjectPicker, undefined);
});

test("users list: rows, access, status, actions, count and filters", async (t) => {
  const h = harness(t, base());
  await h.mount();
  await h.open();
  const list = h.card("Users");
  const rows = [...list.querySelectorAll("tbody tr")].map((r) => [...r.cells].map((c) => c.textContent));
  assert.deepEqual(rows[0].slice(0, 6), ["admin (you)", "Admin", "viewereditoradmin", "All projects (admin)", "active", new Date(1700000000 * 1000).toLocaleString()]);
  assert.equal(rows[0][6], "Add admin to unlock");
  assert.deepEqual(rows[1].slice(3), ["Beta", "invite pending", "awaiting first sign-in", "AccessResendCancel"]);
  assert.deepEqual(rows[2].slice(3), ["All projects", "disabled", "never", "AccessEnableDelete"]);
  assert.match(list.textContent, /3 of 3/);

  await h.type(list.querySelector('input[type="search"]'), "zzz");
  assert.match(list.textContent, /No users match these filters\./);
  assert.match(list.textContent, /0 of 3/);
  await h.type(list.querySelector('input[type="search"]'), "");
  await h.type(list.querySelector('select[aria-label="Filter by status"]'), "pending");
  assert.match(list.textContent, /1 of 3/);
});

test("audit log rows", async (t) => {
  const h = harness(t, base());
  await h.mount();
  await h.open();
  const rows = [...h.card("Audit log").querySelectorAll("tbody tr")].map((r) => [...r.cells].map((c) => c.textContent));
  assert.deepEqual(rows[0].slice(1), ["user.deleted", "admin", "x@y.z", 'from {"role":"viewer"}']);
  assert.match(h.card("Audit log").querySelector("tbody tr td:nth-child(2) span").className, /text-red/);
  assert.equal(rows[1][4], "password");
});

test("invite: validation, admin forces all projects, hint text, request and message", async (t) => {
  let posted;
  const routes = base();
  routes["POST /api/users"] = () => {
    posted = true;
    return [200, { message: "User created, but no invitation email was sent.", delivery: "refused" }];
  };
  const h = harness(t, routes);
  await h.mount();
  await h.open();
  const inv = h.card("Invite a user");
  assert.match(inv.textContent, /Admins always have access to all projects\./); // legacy initial hint

  await h.click(h.button(inv, "Invite"));
  assert.deepEqual(h.ui.at(-1), ["toast", "Email required", true]);

  await h.type(inv.querySelector("#u-email"), " pat@x.io ");
  await h.click(inv.querySelector('input[name="u-scope"][value="some"]'));
  assert.match(inv.textContent, /Select the projects this user can access\./);
  await h.click(h.button(inv, "Invite"));
  assert.deepEqual(h.ui.at(-1), ["toast", "Select at least one project, or choose All projects.", true]);

  await h.type(inv.querySelector("#u-role"), "admin");
  assert.equal(inv.querySelector('input[name="u-scope"]').disabled, true);
  assert.equal(inv.querySelector('input[type="checkbox"]'), null);
  assert.match(inv.textContent, /Admins always have access/);

  await h.type(inv.querySelector("#u-role"), "viewer");
  await h.click(inv.querySelector('input[type="checkbox"][value="p2"]'));
  await h.click(h.button(inv, "Invite"));
  assert.ok(posted);
  assert.deepEqual(h.requests.find((r) => r.method === "POST").body, {
    email: "pat@x.io", name: "", role: "viewer", all_projects: false, project_ids: ["p2"],
  });
  assert.equal(inv.querySelector("#u-email").value, "");
  assert.match(inv.textContent, /User created, but no invitation email was sent\./);
  // The options object comes from the bundle's own realm, so compare its JSON.
  assert.equal(JSON.stringify(h.ui.at(-1)[2]), JSON.stringify({ type: "warn", title: "User created, but invitation email failed" }));
  assert.equal(h.requests.at(-1).path, "/api/users");
});

test("role change confirms, patches and reloads; cancel reloads without a patch", async (t) => {
  const routes = base();
  routes["PATCH /api/users/u3"] = () => [200, {}];
  const h = harness(t, routes, { confirm: false });
  await h.mount();
  await h.open();
  const select = h.card("Users").querySelector('select[aria-label="Role for dan@x.io"]');
  await h.type(select, "viewer");
  assert.deepEqual(h.ui.at(-1).slice(0, 4), [
    "confirm",
    "Change Dan's role to \"viewer\"? They'll be re-authenticated with the new permissions.",
    "Change role",
    "Change role",
  ]);
  assert.equal(h.requests.filter((r) => r.method === "PATCH").length, 0);
  assert.equal(h.card("Users").querySelector('select[aria-label="Role for dan@x.io"]').value, "editor");
});

test("enable, delete, resend, cancel invite and access dialog", async (t) => {
  const routes = base();
  routes["PATCH /api/users/u3"] = () => [200, {}];
  routes["DELETE /api/users/u3"] = () => [200, {}];
  routes["POST /api/users/u2/resend-invite"] = () => [200, { message: "Invite re-sent." }];
  routes["POST /api/users/u2/cancel-invite"] = () => [200, {}];
  routes["PATCH /api/users/u2"] = () => [200, {}];
  const h = harness(t, routes);
  await h.mount();
  await h.open();
  const row = (email) => [...h.card("Users").querySelectorAll("tbody tr")].find((r) => r.cells[0].textContent.startsWith(email));

  await h.click(h.button(row("dan@x.io"), "Enable"));
  assert.deepEqual(h.requests.find((r) => r.method === "PATCH").body, { active: true });
  assert.deepEqual(h.ui.at(-1), ["toast", "Enabled", undefined]);

  await h.click(h.button(row("dan@x.io"), "Delete"));
  assert.deepEqual(h.ui.at(-2), ["confirm", "Delete dan@x.io?", "Delete User", "Delete", true]);
  assert.deepEqual(h.ui.at(-1), ["toast", "User deleted", undefined]);

  await h.click(h.button(row("pat@x.io"), "Resend"));
  assert.match(h.card("Invite a user").textContent, /Invite re-sent\./);

  await h.click(h.button(row("pat@x.io"), "Cancel"));
  assert.deepEqual(h.ui.at(-2), ["confirm", "Cancel the pending invite for pat@x.io?", "Cancel Invite", "Cancel invite", true]);
  assert.deepEqual(h.ui.at(-1), ["toast", "Invite cancelled", undefined]);

  await h.click(h.button(row("pat@x.io"), "Access"));
  assert.deepEqual(h.ui.at(-2), ["modal", "Project access — pat@x.io", "Save access"]);
  const patches = h.requests.filter((r) => r.method === "PATCH" && r.path === "/api/users/u2");
  assert.deepEqual(patches.at(-1).body, { all_projects: false, project_ids: ["p2"] });
  assert.deepEqual(h.ui.at(-1), ["toast", "Project access updated", undefined]);
});

test("admin hand-off presets the invite role to Admin", async (t) => {
  const h = harness(t, base());
  await h.mount();
  await h.open();
  await h.click(h.button(h.card("Users"), "Add admin to unlock"));
  assert.deepEqual(h.ui[0], ["modal", "Add another admin first", "Assign an admin email"]);
  assert.equal(h.card("Invite a user").querySelector("#u-role").value, "admin");
  assert.deepEqual(h.ui.at(-1), ["toast", "Role preset to Admin — enter their email above and click Invite.", undefined]);
});
