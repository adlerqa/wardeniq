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

const entry = fileURLToPath(new URL("../src/components/overlays/modals/CaseConfirmationModal.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry], bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

async function mount(t) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, { module, exports: module.exports, require, window, document, console, setTimeout });
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
      for (let i = 0; i < 5; i++) await settle();
    });
  const click = (el) => flush(() => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  const state = () => ({
    show: $("#case-confirm").classList.contains("show"),
    title: $("#cc-title").textContent,
    copy: $("#cc-copy").textContent,
    summary: [$("#cc-summary").innerHTML, $("#cc-summary").style.display],
    error: $("#cc-error").textContent,
    confirm: [$("#cc-confirm").textContent, $("#cc-confirm").className],
    cancel: $("#cc-cancel").style.display,
    secondary: [$("#cc-secondary").style.display, $("#cc-secondary").textContent],
  });
  return { $, flush, click, state };
}

test("registers the dialogs; danger dialog with summary and a secondary action", async (t) => {
  const h = await mount(t);
  for (const k of ["openCaseConfirmation", "openInfoDialog", "uiConfirm"]) assert.equal(typeof window[k], "function", k);
  const log = [];
  await h.flush(() =>
    window.openCaseConfirmation({
      title: "Delete <x>",
      copy: "Copy",
      summary: "<b>Name</b>",
      confirmLabel: "Delete it",
      danger: true,
      onConfirm: async () => log.push("confirm"),
      secondaryLabel: "Everywhere",
      onSecondary: async () => {
        log.push("secondary");
        throw new Error("sec failed");
      },
    }),
  );
  assert.deepEqual(h.state(), {
    show: true,
    title: "Delete <x>",
    copy: "Copy",
    summary: ["<b>Name</b>", ""],
    error: "",
    confirm: ["Delete it", "danger"],
    cancel: "",
    secondary: ["", "Everywhere"],
  });
  await h.click(h.$("#cc-secondary"));
  assert.equal(h.state().error, "sec failed");
  assert.equal(h.state().show, true);
  await h.click(h.$("#cc-confirm"));
  assert.deepEqual(log, ["secondary", "confirm"]);
  assert.equal(h.state().show, false);
});

test("a failing confirm keeps the dialog open; cancel closes; no summary hides the box", async (t) => {
  const h = await mount(t);
  await h.flush(() =>
    window.openCaseConfirmation({ title: "T", copy: "C", summary: "", confirmLabel: "OK", onConfirm: async () => { throw new Error("nope"); } }),
  );
  assert.deepEqual([h.state().summary[1], h.state().secondary[0], h.state().confirm[1]], ["none", "none", "go"]);
  await h.click(h.$("#cc-confirm"));
  assert.equal(h.state().error, "nope");
  await h.click(h.$("#cc-cancel"));
  assert.equal(h.state().show, false);
});

test("info dialog and uiConfirm", async (t) => {
  const h = await mount(t);
  await h.flush(() => window.openInfoDialog({ title: "Info", copy: "c", summary: "<i>s</i>" }));
  assert.deepEqual([h.state().confirm, h.state().cancel, h.state().secondary[0]], [["Close", "go"], "none", "none"]);
  await h.click(h.$("#cc-confirm"));
  assert.equal(h.state().show, false);
  let p;
  await h.flush(() => {
    p = window.uiConfirm("Sure?");
  });
  assert.deepEqual([h.state().title, h.state().copy, h.state().confirm, h.state().cancel], ["Confirm Action", "Sure?", ["Confirm", "go"], ""]);
  await h.click(h.$("#cc-confirm"));
  assert.equal(await p, true);
  await h.flush(() => {
    p = window.uiConfirm("Remove?", "Delete Repository", "Remove", true);
  });
  assert.deepEqual(h.state().confirm, ["Remove", "danger"]);
  await h.click(h.$("#cc-cancel"));
  assert.equal(await p, false);
  assert.equal(h.state().show, false);
});
