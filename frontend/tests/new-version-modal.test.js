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

const entry = fileURLToPath(new URL("../src/components/overlays/modals/ValidatorModal.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry], bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], loader: { ".css": "empty" }, logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

test("new version: opens blank, needs a source, posts the form, then opens the new version", async (t) => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { toast: [], win: [] };
  Object.assign(window, {
    toast: (m) => calls.toast.push(m),
    openFeature: async (f) => calls.win.push(["openFeature", f]),
    watchFeatureGen: (j, f) => calls.win.push(["watch", j, f]),
    loadFeatures: () => calls.win.push(["loadFeatures"]),
  });
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    requests.push([opts.method, path, [...opts.body.entries()]]);
    return { status: 200, ok: true, text: async () => JSON.stringify({ version: 4, feature_id: "f4", job_id: "j4", diff: { kept: 3, retired: [1] } }) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout, clearTimeout, FormData: window.FormData,
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
      for (let i = 0; i < 5; i++) await settle();
    });
  const setValue = (el, v) =>
    flush(() => {
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v);
      el.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
  await flush(() => window.openNewVersionModal("f1", "Payments — current v3 · 4 cases"));
  assert.equal($("#vmodal").classList.contains("show"), true);
  assert.equal($("#vm-feat").textContent, "Payments — current v3 · 4 cases");
  await flush(() => $("#vm-go").dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  assert.equal($("#vm-msg").innerHTML, '<span class="err">Upload a doc, paste text, or add a Confluence/Figma link.</span>');
  await setValue($("#vm-text"), "new req");
  await setValue($("#vm-confluence"), "https://c/1 https://c/2");
  await flush(() => $("#vm-replace").click());
  await flush(() => $("#vm-go").dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  assert.deepEqual(requests[0][2], [["text", "new req"], ["replace", "true"], ["confluence_url", "https://c/1"], ["confluence_url", "https://c/2"]]);
  assert.equal($("#vm-msg").innerHTML, '<span class="ok">v4 created — 3 kept, 1 retired. Generating new cases…</span>');
  assert.deepEqual(calls.toast, ["Version 4 created"]);
  await flush(() => new Promise((r) => setTimeout(r, 1250)));
  assert.equal($("#vmodal").classList.contains("show"), false);
  assert.deepEqual(calls.win, [["openFeature", "f4"], ["loadFeatures"], ["watch", "j4", "f4"]]);
  await flush(() => window.openNewVersionModal("f1", "x"));
  assert.equal($("#vm-text").value, "");
  await flush(() => $("#vm-cancel").dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
  assert.equal($("#vmodal").classList.contains("show"), false);
});
