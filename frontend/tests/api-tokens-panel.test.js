import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

// react-dom decides at import time whether the DOM supports the "input" event
// (controlled inputs depend on it), so the DOM globals must exist first.
const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(
  new URL("../src/features/users/components/ApiTokensPanel.jsx", import.meta.url),
);
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
const TOKENS = {
  tokens: [
    { id: "t1", name: "ci-all", role: "viewer", all_projects: true, project_ids: [], active: true, last_used_at: null, expires_at: null },
    { id: "t2", name: "ci-some", role: "editor", all_projects: false, project_ids: ["p2"], active: false, last_used_at: 1700000000, expires_at: null },
    { id: "t3", name: "ci-none", role: "viewer", all_projects: false, project_ids: [], active: true },
  ],
};

function harness(t, routes) {
  for (const k of ["toast", "uiConfirm", "uiModalHTML", "loadApiTokens"]) delete window[k];
  const container = document.createElement("div");
  document.body.appendChild(container);
  const requests = [];
  const ui = [];
  window.toast = (...a) => ui.push(["toast", ...a]);
  window.uiConfirm = async (...a) => {
    ui.push(["confirm", ...a]);
    return true;
  };
  window.uiModalHTML = async (...a) => {
    ui.push(["modal", ...a]);
    return true;
  };
  async function fakeFetch(path, init = {}) {
    const method = init.method || "GET";
    requests.push({ method, path, body: init.body ? JSON.parse(init.body) : undefined });
    const handler = routes[`${method} ${path}`];
    const [status, body] = handler ? handler(init) : [404, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout,
  });
  const root = createRoot(container);
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  return {
    window, document, container, requests, ui, root,
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async load() {
      await act(async () => window.loadApiTokens());
    },
    text: () => container.textContent,
    async type(input, value) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      await act(async () => {
        setter.call(input, value);
        input.dispatchEvent(new window.Event("input", { bubbles: true }));
      });
    },
    async click(el) {
      await act(async () => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    },
    button: (label) =>
      [...container.querySelectorAll("button")].find((b) => b.textContent.trim() === label),
  };
}

const ok = (body) => () => [200, body];

test("does not fetch on mount and registers/unregisters window.loadApiTokens", async (t) => {
  const h = harness(t, { "GET /api/projects": ok(PROJECTS), "GET /api/api-tokens": ok(TOKENS) });
  await h.mount();
  assert.equal(h.requests.length, 0);
  assert.equal(typeof h.window.loadApiTokens, "function");
  await act(async () => h.root.unmount());
  assert.equal(h.window.loadApiTokens, undefined);
});

test("renders the token table with access, status and dates", async (t) => {
  const h = harness(t, { "GET /api/projects": ok(PROJECTS), "GET /api/api-tokens": ok(TOKENS) });
  await h.mount();
  await h.load();
  assert.deepEqual(h.requests.map((r) => r.path), ["/api/projects", "/api/api-tokens"]);
  const heads = [...h.container.querySelectorAll("th")].map((th) => th.textContent);
  assert.deepEqual(heads, ["Name", "Role", "Access", "Status", "Last used", "Expires", "Actions"]);
  const rows = [...h.container.querySelectorAll("tbody tr")].map((tr) =>
    [...tr.children].map((td) => td.textContent),
  );
  assert.deepEqual(rows[0], ["ci-all", "viewer", "All projects", "active", "never", "never", "Revoke"]);
  assert.deepEqual(rows[1], [
    "ci-some", "editor", "Beta", "revoked", new Date(1700000000 * 1000).toLocaleString(), "never", "",
  ]);
  assert.equal(rows[2][2], "No projects");
  assert.match(h.container.querySelector("tbody tr:nth-child(3) td:nth-child(3) span").className, /text-red/);
});

test("empty state and load error", async (t) => {
  let fail = false;
  const h = harness(t, {
    "GET /api/projects": () => [500, {}],
    "GET /api/api-tokens": () => (fail ? [500, { detail: "db down" }] : [200, { tokens: [] }]),
  });
  await h.mount();
  await h.load();
  assert.match(h.text(), /No API tokens yet\. Create one above for a CI job or other machine caller\./);
  fail = true;
  await h.load();
  assert.match(h.text(), /db down/);
  assert.equal(h.container.querySelector("table"), null);
});

test("validation errors, then create with specific projects and show the copy dialog", async (t) => {
  let created;
  const h = harness(t, {
    "GET /api/projects": ok(PROJECTS),
    "GET /api/api-tokens": ok({ tokens: [] }),
    "POST /api/api-tokens": (init) => {
      created = JSON.parse(init.body);
      return [200, { token: { id: "t9" }, plaintext: "wq_secret" }];
    },
  });
  await h.mount();
  await h.load();
  const create = h.button("Create token");

  await h.click(create);
  assert.deepEqual(h.ui.at(-1), ["toast", "Name required", true]);

  const [nameInput, expiresInput] = h.container.querySelectorAll("input:not([type=radio])");
  await h.type(nameInput, "  GitHub CI ");
  const some = h.container.querySelector('input[type=radio][value="some"]');
  await h.click(some);
  assert.ok(h.text().includes("Beta"));
  await h.click(create);
  assert.deepEqual(h.ui.at(-1), ["toast", "Select at least one project, or choose All projects.", true]);
  assert.equal(created, undefined);

  await h.click(h.container.querySelector('input[type=checkbox][value="p2"]'));
  await h.type(expiresInput, "30");
  await h.click(create);
  assert.deepEqual(created, {
    name: "GitHub CI", role: "viewer", all_projects: false, project_ids: ["p2"], expires_in_days: 30,
  });
  const modal = h.ui.find((c) => c[0] === "modal");
  assert.equal(modal[1], "Token created — copy it now");
  assert.match(modal[2], /value="wq_secret"/);
  assert.equal(modal[3], "Done");
  assert.equal(nameInput.value, "");
  assert.equal(expiresInput.value, "");
  assert.equal(h.requests.at(-1).path, "/api/api-tokens");
  assert.equal(h.requests.at(-1).method, "GET");
});

test("create with all projects omits expires", async (t) => {
  let created;
  const h = harness(t, {
    "GET /api/projects": ok(PROJECTS),
    "GET /api/api-tokens": ok({ tokens: [] }),
    "POST /api/api-tokens": (init) => {
      created = JSON.parse(init.body);
      return [200, { plaintext: "wq_x" }];
    },
  });
  await h.mount();
  await h.load();
  await h.type(h.container.querySelector("input"), "ci");
  await h.click(h.button("Create token"));
  assert.deepEqual(created, { name: "ci", role: "viewer", all_projects: true, project_ids: [] });
});

test("revoke asks for confirmation, deletes, toasts and reloads", async (t) => {
  const h = harness(t, {
    "GET /api/projects": ok(PROJECTS),
    "GET /api/api-tokens": ok(TOKENS),
    "DELETE /api/api-tokens/t1": ok({ revoked: "t1" }),
  });
  await h.mount();
  await h.load();
  assert.equal([...h.container.querySelectorAll("button")].filter((b) => b.textContent === "Revoke").length, 2);
  await h.click(h.button("Revoke"));
  assert.deepEqual(h.ui[0], [
    "confirm",
    'Revoke the token "ci-all"? Any caller using it loses access immediately.',
    "Revoke Token",
    "Revoke",
    true,
  ]);
  assert.ok(h.requests.some((r) => r.method === "DELETE" && r.path === "/api/api-tokens/t1"));
  assert.deepEqual(h.ui.at(-1), ["toast", "Token revoked", undefined]);
  assert.equal(h.requests.at(-1).path, "/api/api-tokens");
});
