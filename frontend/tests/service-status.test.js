import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
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

// A small screen: the hook's state rendered by the real chips.
const entry = `
import { useServiceStatus } from "./src/layouts/useServiceStatus.js";
import ServiceChips from "./src/layouts/ServiceChips.jsx";
export default function Probe() {
  const { status, banner } = useServiceStatus();
  return (
    <div>
      <div id="status" data-phase={status.phase}>{status.phase !== "idle" ? <ServiceChips status={status} /> : "idle"}</div>
      <div id="banner" data-kind={banner.visible ? banner.kind : ""}>{banner.visible ? banner.summary + "|" + (banner.raw || "") : ""}</div>
    </div>
  );
}`;
const bundled = await build({
  stdin: { contents: entry, resolveDir: new URL("..", import.meta.url).pathname, loader: "jsx" },
  bundle: true, write: false, format: "cjs", platform: "neutral", jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"], logLevel: "silent",
});

test("service status: first load, chips, boot banner, failures keep the chips", async (t) => {
  let reply;
  const warns = [];
  const fakeFetch = async () => (reply === "net" ? Promise.reject(new TypeError("down"))
    : { status: reply.st, ok: reply.st < 400, text: async () => JSON.stringify(reply.body) });
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, fetch: fakeFetch, setTimeout, clearTimeout,
    console: { ...console, warn: (...a) => warns.push(a.join(" ")), error: () => {} },
  });
  window.toast = () => {};
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(React.createElement(module.exports.default)));
  t.after(async () => { await act(async () => root.unmount()); container.remove(); });
  const $ = (s) => container.querySelector(s);
  const refresh = () => act(async () => { await window.refreshStatus(); });

  assert.equal($("#status").textContent, "idle");
  reply = "net";
  await refresh();
  assert.equal($("#status").textContent, "Status unavailable");
  assert.equal($("#banner").dataset.kind, "error");

  reply = { st: 200, body: {
    mongo_connected: true, counts: { features: 3, test_cases: 12 },
    embedding: { provider: "ollama", model: "nomic", dims: 768, health: { ok: true } },
    llm: { provider: "anthropic", model: "c", health: { ok: false, error: "quota" } },
    boot: { ready: false, stage: "error", detail: "pymongo timeout <x>" },
  } };
  await refresh();
  const stats = [...$("#status").querySelectorAll(".stat")];
  assert.deepEqual(stats.map((s) => [s.title, s.textContent, s.querySelector(".dot").className]), [
    ["MongoDB connection", "Mongo", "dot ok"],
    ["Embeddings: ollama · 768-d", "nomic", "dot ok"],
    ["LLM: quota", "c", "dot bad"],
  ]);
  assert.equal($(".stat-metric").textContent, "3 features12 cases");
  assert.match($("#banner").textContent, /^wardenIQ requires a MongoDB with Vector Search.*\|pymongo timeout <x>$/);
  assert.equal(warns.at(-1), "[wardenIQ] boot detail: pymongo timeout <x>");

  reply = { st: 500, body: { detail: "insecure APP_SECRET — set one" } };
  await refresh();
  assert.equal($("#status").dataset.phase, "ready");
  assert.equal($("#banner").textContent, "insecure APP_SECRET — set one|");

  reply = { st: 200, body: { boot: { ready: true } } };
  await refresh();
  assert.equal($("#banner").dataset.kind, "");
  assert.equal($(".stat-metric").textContent, "0 features0 cases");
});
