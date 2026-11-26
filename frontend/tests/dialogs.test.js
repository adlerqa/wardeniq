import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

async function mount(t, file) {
  const bundled = await build({
    entryPoints: [fileURLToPath(new URL(`../src/components/overlays/modals/${file}`, import.meta.url))],
    bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
    external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
  });
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, { module, exports: module.exports, require, window, document, console, setTimeout, clearTimeout });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(module.exports.default)));
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  const flush = (fn) => act(async () => { await fn?.(); for (let i = 0; i < 5; i++) await settle(); });
  return { $: (s) => container.querySelector(s), flush };
}
const key = (k, el = document) => el.dispatchEvent(new window.KeyboardEvent("keydown", { key: k, bubbles: true }));

test("confirm dialog: text, danger button, and every way to close", async (t) => {
  const h = await mount(t, "ConfirmationModal.jsx");
  let r;
  await h.flush(() => { window.confirmModal({ title: "Delete <x>", body: "a\nb", confirmText: "Delete", danger: true }).then((v) => { r = v; }); });
  assert.ok(h.$("#confirm-modal").classList.contains("show"));
  assert.deepEqual([h.$("#confirm-title").textContent, h.$("#confirm-body").textContent, h.$("#confirm-ok").textContent, h.$("#confirm-ok").className],
    ["Delete <x>", "a\nb", "Delete", "danger"]);
  await h.flush(() => h.$("#confirm-ok").click());
  assert.equal(r, true);
  assert.equal(h.$("#confirm-modal").classList.contains("show"), false);
  for (const [how, expected] of [["cancel", false], ["backdrop", false], ["inside", undefined], ["Escape", false], ["Enter", true]]) {
    r = undefined;
    await h.flush(() => { window.confirmModal().then((v) => { r = v; }); });
    assert.equal(h.$("#confirm-title").textContent, "Please confirm");
    assert.equal(h.$("#confirm-ok").className, "go");
    if (how === "cancel") await h.flush(() => h.$("#confirm-cancel").click());
    else if (how === "backdrop") await h.flush(() => h.$("#confirm-modal").click());
    else if (how === "inside") await h.flush(() => h.$("#confirm-body").click());
    else await h.flush(() => key(how));
    assert.equal(r, expected, how);
    if (how === "inside") await h.flush(() => key("Escape"));
  }
});

test("prompt dialog: trims on OK / Enter, null on Cancel / Escape", async (t) => {
  const h = await mount(t, "ProjectAccessModal.jsx");
  const open = async (...a) => { let r = "pending"; await h.flush(() => { window.uiPrompt(...a).then((v) => { r = v; }); }); return () => r; };
  let r = await open("Rename", "", "old");
  assert.deepEqual([h.$("#pm-title").textContent, h.$("#pm-label").textContent, h.$("#pm-input").value], ["Rename", "Value", "old"]);
  await h.flush(() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(h.$("#pm-input"), "  new  ");
    h.$("#pm-input").dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await h.flush(() => h.$("#pm-ok").click());
  assert.equal(r(), "new");
  r = await open("T", "Name");
  assert.equal(h.$("#pm-input").value, "");
  await h.flush(() => h.$("#pm-cancel").click());
  assert.equal(r(), null);
  r = await open("T", "Name", "v");
  await h.flush(() => key("Enter", h.$("#pm-input")));
  assert.equal(r(), "v");
  r = await open("T", "Name", "v");
  await h.flush(() => key("Escape", h.$("#pm-input")));
  assert.equal(r(), null);
});

test("HTML dialog: body stays readable after OK; access scope toggle and search", async (t) => {
  const h = await mount(t, "HtmlModal.jsx");
  let r;
  await h.flush(() => {
    window.uiModalHTML("Access", '<input type="radio" name="ma-scope" value="all" checked><input type="radio" name="ma-scope" value="some">' +
      '<input id="ma-search" hidden><div id="ma-list" hidden><label data-name="alpha">A</label><label data-name="beta">B</label></div>').then((v) => { r = v; });
  });
  assert.equal(h.$("#hm-ok").textContent, "Save");
  const some = h.$('input[value="some"]');
  some.checked = true;
  some.dispatchEvent(new window.Event("change"));
  assert.deepEqual([h.$("#ma-list").hidden, h.$("#ma-search").hidden], [false, false]);
  h.$("#ma-search").value = "al";
  h.$("#ma-search").dispatchEvent(new window.Event("input"));
  assert.deepEqual([...h.$("#ma-list").children].map((l) => l.style.display), ["", "none"]);
  await h.flush(() => h.$("#hm-ok").click());
  assert.equal(r, true);
  assert.equal(h.$('input[value="some"]').checked, true);
  await h.flush(() => { window.uiModalHTML("T", "<p>x</p>", "Go").then((v) => { r = v; }); });
  assert.equal(h.$("#hm-ok").textContent, "Go");
  assert.equal(h.$("#hm-body").innerHTML, "<p>x</p>");
  await h.flush(() => h.$("#hm-x").click());
  assert.equal(r, false);
});
