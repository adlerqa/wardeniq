import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after, before } from "node:test";
import vm from "node:vm";

import axe from "axe-core";
import { JSDOM } from "jsdom";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const WCAG_TAGS = ["wcag2a", "wcag2aa"];
let vite;

before(async () => {
  vite = await createServer({
    configFile: "./vite.config.js",
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
});

after(async () => {
  await vite?.close();
});

function sourceFunction(path, startMarker, endMarker) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const start = source.indexOf(startMarker);
  const end = endMarker ? source.indexOf(endMarker, start) : -1;
  assert.notEqual(start, -1, `Missing ${startMarker} in ${path}`);
  assert.notEqual(end, -1, `Missing ${endMarker} in ${path}`);
  return source.slice(start, end);
}

async function renderModule(path) {
  const module = await vite.ssrLoadModule(path);
  return renderToStaticMarkup(createElement(module.default));
}

function createDocument(markup) {
  const dom = new JSDOM(
    `<!doctype html><html lang="en"><head><title>Accessibility test</title></head><body>${markup}</body></html>`,
    {
      pretendToBeVisual: true,
      runScripts: "outside-only",
      url: "http://localhost/",
    },
  );
  dom.window.document.querySelectorAll("[hidden]").forEach((node) => {
    node.removeAttribute("hidden");
  });
  return dom;
}

function addRuntimeUsers(dom) {
  const renderUsersSource = sourceFunction(
    "../src/compat/runtime/controllers/11-users.js",
    "function renderUsers()",
    "// Guided hand-off:",
  );
  const context = vm.createContext({
    $: (selector) => dom.window.document.querySelector(selector),
    ME: { id: "self" },
    accessCell: () => "All projects",
    esc: (value) => String(value ?? "").replaceAll("<", "&lt;"),
    escAttr: (value) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("<", "&lt;"),
    window: {
      _USERS_CACHE: [
        {
          id: "user-1",
          active: true,
          email: "user@example.com",
          invite_status: "accepted",
          name: "Test User",
          role: "editor",
        },
      ],
    },
    _userMatchesFilters: () => true,
  });
  vm.runInContext(renderUsersSource, context);
  context.renderUsers();
}

function addRuntimeRepoBranch(dom, target) {
  const repoBranchRowsSource = sourceFunction(
    "../src/compat/runtime/controllers/09-mind-map-and-jobs.js",
    "function repoBranchRows",
    "// populate each repo's branch",
  );
  const context = vm.createContext({
    esc: (value) => String(value ?? "").replaceAll("<", "&lt;"),
    escAttr: (value) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("<", "&lt;"),
    repoAnalysisDefaultChecked: () => true,
    repoKindClass: () => "repo",
    repoKindLabel: () => "Repository",
  });
  vm.runInContext(repoBranchRowsSource, context);
  const rows = context.repoBranchRows(
    [{ id: "repo-1", full_name: "example/repo", kind: "BE" }],
    "runtime",
  );
  dom.window.document.querySelector(target).innerHTML = rows;
}

function addRuntimeModal(dom) {
  const createRuntimeModalSource = sourceFunction(
    "../src/compat/runtime/controllers/00-core.js",
    "function createRuntimeModal",
    "function uiConfirm",
  );
  const context = vm.createContext({
    document: dom.window.document,
  });
  vm.runInContext(createRuntimeModalSource, context);
  const modal = context.createRuntimeModal("runtime-modal-title");
  modal.innerHTML =
    '<div><h2 id="runtime-modal-title">Runtime dialog</h2><button>Close</button></div>';
  dom.window.document.body.appendChild(modal);
}

async function audit(markup, populate) {
  const dom = createDocument(markup);
  populate?.(dom);
  dom.window.eval(axe.source);
  const results = await dom.window.axe.run(dom.window.document, {
    rules: {
      "color-contrast": { enabled: false },
    },
    runOnly: { type: "tag", values: WCAG_TAGS },
  });
  const failures = results.violations.map((violation) => ({
    id: violation.id,
    nodes: violation.nodes.map((node) => node.target.join(" ")),
    summary: violation.help,
  }));
  assert.equal(
    failures.length,
    0,
    `Axe violations:\n${JSON.stringify(failures, null, 2)}`,
  );
  dom.window.close();
}

test("Users screen has no WCAG 2 A/AA axe violations", async () => {
  const markup = await renderModule("/src/features/users/pages/UsersPage.jsx");
  await audit(markup, addRuntimeUsers);
});

test("Configuration screen has no WCAG 2 A/AA axe violations", async () => {
  await audit(
    await renderModule(
      "/src/features/configuration/pages/ConfigurationPage.jsx",
    ),
  );
});

test("Cycles screens have no WCAG 2 A/AA axe violations", async () => {
  const analysis = await renderModule(
    "/src/features/code-analysis/pages/CodeAnalysisPage.jsx",
  );
  await audit(analysis, (dom) => addRuntimeRepoBranch(dom, "#cyc-repos"));
  await audit(
    await renderModule("/src/features/test-cycles/pages/TestCyclesPage.jsx"),
  );
});

test("Mind Map screen has no WCAG 2 A/AA axe violations", async () => {
  const markup = await renderModule("/src/features/mind-map/pages/MindMapPage.jsx");
  await audit(markup, (dom) => addRuntimeRepoBranch(dom, "#mm-repos"));
});

test("modal shells have valid WCAG 2 A/AA dialog semantics", async () => {
  await audit(
    await renderModule("/src/components/overlays/AppOverlays.jsx"),
    addRuntimeModal,
  );
});

test("info icons expose a keyboard focus ring", () => {
  const css = readFileSync(
    new URL(
      "../src/styles/compat/00-foundation.css",
      import.meta.url,
    ),
    "utf8",
  );
  assert.match(css, /\.fi:focus-visible\s*{[^}]*outline:/s);
});
