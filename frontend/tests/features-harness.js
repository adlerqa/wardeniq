// Shared harness for the React Features screen tests (features-panel,
// feature-upload-file-remove, cpu-warning-estimate). Not a test file itself.
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
export const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");

const entry = fileURLToPath(new URL("../src/features/features/pages/FeaturesPage.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "neutral",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"],
  loader: { ".css": "empty" },
  logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

export class FakeDataTransfer {
  constructor() {
    this._files = [];
    this.items = { add: (f) => this._files.push(f) };
  }
  get files() {
    return this._files;
  }
}

export const FEATS = [
  { id: "f1", name: "Login <b>x</b>", version: 2, case_count: 1, key: "WQ-1", project_id: "pA" },
  { id: "f2", name: "Signup", case_count: 0, project_id: "pA" },
];

/** routes: { "METHOD path": (opts) => [status, body] } overrides the defaults. */
export function harness(t, routes = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const calls = { toast: [], open: [], feature: [], backbar: 0, status: 0, prompt: [], cc: [], sheet: [], projects: 0, job: null };
  const state = { promptAnswer: null, estimate: { low: 0.01, high: 0.05, note: "rough" } };
  let current = "pA";
  Object.assign(window, {
    getCurrentProject: () => current,
    getCurrentFeatureId: () => null,
    setCurrentFeature: (f) => calls.feature.push(f),
    openFeature: async (f) => calls.open.push(f),
    updateBackbar: () => calls.backbar++,
    refreshStatus: () => calls.status++,
    goToProjects: () => calls.projects++,
    importSheetForFeature: (a, b) => calls.sheet.push([a, b]),
    toast: (m, o) => calls.toast.push([m, o === true ? "err" : "ok"]),
    uiPrompt: async (...a) => {
      calls.prompt.push(a);
      return state.promptAnswer;
    },
    openCaseConfirmation: (o) => calls.cc.push(o),
    watchJob: (id, cb) => (calls.job = { id, cb }),
    usageLogLines: () => [],
  });
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    const method = opts.method || "GET";
    let body;
    if (opts.body instanceof window.FormData || (opts.body && typeof opts.body.entries === "function"))
      body = [...opts.body.entries()].map(([k, v]) => [k, typeof v === "string" ? v : `FILE:${v.name}`]);
    else if (opts.body) body = JSON.parse(opts.body);
    requests.push([method, path, body]);
    const key = Object.keys(routes).find((k) => k === `${method} ${path}`);
    const [status, data] = key
      ? routes[key](opts)
      : path.startsWith("/api/features?") && method === "GET"
        ? [200, { features: state.empty ? [] : FEATS }]
        : path === "/api/features" && method === "POST"
          ? [200, { feature_id: "fN", job_id: "jN", doc_count: 2, chunks: 7 }]
          : path === "/api/usage/estimate"
            ? [200, state.estimate]
            : path.match(/^\/api\/projects\/[^/]+$/)
              ? [200, { jira_project_key: state.noJira ? "" : " WQ " }]
              : path.endsWith("/jira-issues")
                ? [200, { issues: [{ key: "WQ-7", summary: "Epic" }] }]
                : path.match(/^\/api\/features\/[^/?]+$/) && method === "GET"
                  ? [200, { name: "Signup <i>", version: 3, test_cases: [{}, {}] }]
                  : path.match(/^\/api\/features\/[^/?]+$/) && method === "DELETE"
                    ? [200, { removed_orphan_cases: 4, preserved_shared_cases: 1 }]
                    : [200, {}];
    return { status, ok: status < 300, text: async () => JSON.stringify(data), json: async () => data };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, clearTimeout,
    setTimeout: (fn, ms) => setTimeout(fn, ms === 400 ? 0 : ms),
    DataTransfer: FakeDataTransfer, FormData: window.FormData,
  });
  const root = createRoot(container);
  t.after(async () => {
    try {
      await act(async () => root.unmount());
    } catch {
      /* already unmounted */
    }
    container.remove();
  });
  const $ = (s) => container.querySelector(s);
  const flush = (fn) =>
    act(async () => {
      await fn?.();
      for (let i = 0; i < 8; i++) await settle();
    });
  const setValue = (el, v, ev = "input") =>
    flush(() => {
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v);
      el.dispatchEvent(new window.Event(ev, { bubbles: true }));
    });
  /** Give the file input a FileList-like array and fire change. */
  const setFiles = (el, files) =>
    flush(() => {
      Object.defineProperty(el, "files", { value: files, writable: true, configurable: true });
      el.dispatchEvent(new window.Event("change", { bubbles: true }));
    });
  return {
    $, calls, requests, state, flush, setValue, setFiles, container,
    setProject: (p) => (current = p),
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await this.mount();
      await flush(() => window.syncFeatureProjects([{ id: "pA", name: "Tour QA", repo_count: 0, feature_count: 1 }], "pA"));
      await flush(() => window.loadFeatures());
    },
    click: (el) => flush(() => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))),
  };
}

/** A real (jsdom) File, so FormData keeps its name. */
export const makeFile = (name, size = 100) => new window.File(["x".repeat(size)], name);
