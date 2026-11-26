import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";
import { toastSettings } from "../src/lib/toast.js";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const bundled = await build({
  entryPoints: [fileURLToPath(new URL("../src/components/overlays/modals/ToastHost.jsx", import.meta.url))],
  bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
});
const require = createRequire(import.meta.url);

async function mount(t) {
  const timeouts = [];
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console,
    setTimeout: (fn, delay) => { timeouts.push({ fn, delay }); return timeouts.length; },
    clearTimeout: () => {},
  });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(module.exports.default)));
  t.after(async () => {
    await act(async () => root.unmount());
    container.remove();
  });
  const show = async (...args) => {
    await act(async () => window.toast(...args));
    return [...container.querySelectorAll("#toast .toastmsg")].at(-1);
  };
  return { show, timeouts, container, settings: toastSettings };
}

test("warning toast renders the correct class, title, icon, message and duration", async (t) => {
  const h = await mount(t);
  const message = "Invitation email failed";
  const el = await h.show(message, { type: "warn" });
  const expected = Math.min(9000, 5200 + message.length * 35);
  assert.equal(el.className, "toastmsg warn");
  assert.equal(el.querySelector(".t-ico").textContent, "⚠");
  assert.equal(el.querySelector(".t-title").textContent, "Warning");
  assert.equal(el.querySelector(".t-msg").textContent, message);
  assert.equal(h.timeouts.at(-1).delay, expected);
  assert.match(el.querySelector(".t-timer").getAttribute("style"), new RegExp(`${expected}ms`));
});

test("legacy error and success calls, custom types, titles and durations", async (t) => {
  const h = await mount(t);
  const err = await h.show("Something failed", true);
  assert.equal(err.className, "toastmsg err");
  assert.equal(err.querySelector(".t-ico").textContent, "!");
  assert.equal(err.querySelector(".t-title").textContent, "Something went wrong");
  const ok = await h.show("User created");
  assert.equal(ok.className, "toastmsg ok");
  assert.equal(ok.querySelector(".t-title").textContent, "Success");
  const info = await h.show("Custom notification", { type: "info", title: "Custom title", duration: 6000 });
  assert.equal(info.className, "toastmsg info");
  assert.equal(info.querySelector(".t-ico").textContent, "i");
  assert.equal(info.querySelector(".t-title").textContent, "Custom title");
  assert.equal(h.timeouts.at(-1).delay, 6000);
  assert.equal(h.settings("x", { isErr: true }).type, "err");
  assert.equal(h.settings(null).msg, "");
  assert.equal(h.container.querySelectorAll("#toast .toastmsg").length, 3);
});

test("a toast leaves after its time, × dismisses, hover keeps it", async (t) => {
  const h = await mount(t);
  const a = await h.show("a");
  await act(async () => h.timeouts[0].fn());
  assert.equal(a.className, "toastmsg ok leaving");
  await act(async () => h.timeouts.at(-1).fn());
  assert.equal(h.container.querySelectorAll(".toastmsg").length, 0);
  const b = await h.show("b");
  await act(async () => b.dispatchEvent(new window.MouseEvent("mouseenter")));
  assert.equal(b.querySelector(".t-timer").style.animationPlayState, "paused");
  await act(async () => b.querySelector(".t-close").click());
  assert.equal(b.className, "toastmsg ok leaving");
});
