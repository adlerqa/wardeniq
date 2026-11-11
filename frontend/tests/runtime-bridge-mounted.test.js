import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { JSDOM } from "jsdom";
import postcss from "postcss";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import tailwindcss from "tailwindcss";
import { transformWithEsbuild } from "vite";
import tailwindConfig from "../tailwind.config.js";

const bridgeUrl = new URL(
  "../src/compat/runtime/RuntimeBridge.jsx",
  import.meta.url,
);
const { code } = await transformWithEsbuild(
  readFileSync(bridgeUrl, "utf8"),
  bridgeUrl.pathname,
  { loader: "jsx", jsx: "automatic", format: "cjs" },
);
const require = createRequire(import.meta.url);

test("Tailwind compiles the recovery panel's stacking utility above the login screen", async () => {
  const frontendDirectory = fileURLToPath(new URL("../", import.meta.url));
  const content = tailwindConfig.content.map((pattern) =>
    pattern.startsWith("!")
      ? `!${resolve(frontendDirectory, pattern.slice(1))}`
      : resolve(frontendDirectory, pattern),
  );
  const { css } = await postcss([
    tailwindcss({ ...tailwindConfig, content }),
  ]).process("@tailwind utilities;", { from: undefined });

  assert.match(css, /\.z-\\\[10000\\\]\s*\{\s*z-index: 10000/);
});

function harness(t, { failures = 0, ready = false } = {}) {
  const dom = new JSDOM('<div id="root"></div>', {
    url: "http://localhost/",
  });
  const { window } = dom;
  const { document } = window;
  window.__WARDENIQ_RUNTIME_READY__ = ready;
  const globals = {
    window,
    document,
    IS_REACT_ACT_ENVIRONMENT: true,
  };
  const descriptors = new Map(
    Object.keys(globals).map((name) => [
      name, Object.getOwnPropertyDescriptor(globalThis, name),
    ]),
  );
  for (const [name, value] of Object.entries(globals)) {
    Object.defineProperty(globalThis, name, {
      value, writable: true, configurable: true,
    });
  }

  const failure = new Error("temporary runtime insertion failure");
  const logs = [];
  let attempts = 0;
  const appendChild = document.body.appendChild;
  document.body.appendChild = function (node) {
    if (node.dataset?.wardeniqRuntime === "compat") {
      attempts++;
      assert.equal(window.__WARDENIQ_RUNTIME_READY__, false);
      if (attempts <= failures) throw failure;
    }
    return appendChild.call(this, node);
  };
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module,
    exports: module.exports,
    require(path) {
      if (path.startsWith("./controllers/") && path.endsWith("?raw")) {
        return readFileSync(new URL(path.slice(0, -4), bridgeUrl), "utf8");
      }
      return require(path);
    },
    window,
    document,
    console: {
      ...console,
      error: (...args) => logs.push(args),
    },
  });

  const container = document.getElementById("root");
  const root = createRoot(container);
  const Bridge = module.exports.default;
  let unmounted = false;
  async function unmount() {
    if (unmounted) return;
    await act(async () => root.unmount());
    unmounted = true;
  }
  t.after(async () => {
    try {
      await unmount();
    } finally {
      document.body.appendChild = appendChild;
      dom.window.close();
      for (const [name, descriptor] of descriptors) {
        if (descriptor) Object.defineProperty(globalThis, name, descriptor);
        else delete globalThis[name];
      }
    }
  });

  return {
    window, document, container, logs, failure, unmount,
    get attempts() { return attempts; },
    get scripts() {
      return document.querySelectorAll('script[data-wardeniq-runtime="compat"]');
    },
    get alert() { return container.querySelector('[role="alert"]'); },
    get button() { return container.querySelector("button"); },
    async mount({ strict = false } = {}) {
      await act(async () => {
        const element = React.createElement(Bridge);
        root.render(
          strict ? React.createElement(React.StrictMode, null, element) : element,
        );
      });
    },
    mountAndUnmountBeforeSettling() {
      act(() => root.render(React.createElement(Bridge)));
      act(() => root.unmount());
      unmounted = true;
    },
    clickRetry() {
      this.button.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    },
  };
}

test("the mounted bridge recovers through Retry without remounting", async (t) => {
  const h = harness(t, { failures: 1 });
  await h.mount();

  assert.equal(h.attempts, 1);
  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, false);
  assert.match(h.alert.textContent, /WardenIQ could not initialize/);
  assert.ok(!h.alert.textContent.includes(h.failure.message));
  assert.equal(h.button.textContent, "Retry");
  assert.equal(h.button.type, "button");
  assert.equal(h.button.disabled, false);
  assert.equal(h.logs.length, 1);
  assert.deepEqual(h.logs[0], [
    "Failed to load the WardenIQ compatibility runtime.", h.failure,
  ]);
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  assert.equal(h.attempts, 1);

  act(() => {
    h.clickRetry();
    h.clickRetry();
  });
  assert.equal(h.button.disabled, true);
  assert.equal(h.button.textContent, "Retrying...");
  assert.equal(h.alert.getAttribute("aria-busy"), "true");
  assert.equal(h.attempts, 1);
  await act(async () => {});

  assert.equal(h.attempts, 2);
  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
  assert.equal(h.alert, null);
});

test("another mounted retry failure keeps the action available until success", async (t) => {
  const h = harness(t, { failures: 2 });
  await h.mount();
  await act(async () => h.clickRetry());

  assert.equal(h.attempts, 2);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, false);
  assert.equal(h.scripts.length, 0);
  assert.equal(h.button.disabled, false);
  assert.equal(h.alert.getAttribute("aria-busy"), "false");
  assert.equal(h.logs.length, 2);

  await act(async () => h.clickRetry());

  assert.equal(h.attempts, 3);
  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
  assert.equal(h.alert, null);
});

test("a successful mount initializes once without an error panel", async (t) => {
  const h = harness(t);
  await h.mount();

  assert.equal(h.attempts, 1);
  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
  assert.equal(h.alert, null);
  assert.deepEqual(h.logs, []);
});

test("an already-ready mounted bridge does not inject again", async (t) => {
  const h = harness(t, { ready: true });
  await h.mount();

  assert.equal(h.attempts, 0);
  assert.equal(h.scripts.length, 0);
  assert.equal(h.alert, null);
  assert.deepEqual(h.logs, []);
});

test("StrictMode replay shares initialization and retains UI-driven recovery", async (t) => {
  const h = harness(t, { failures: 1 });
  await h.mount({ strict: true });

  assert.equal(h.attempts, 1);
  assert.equal(h.logs.length, 1);
  assert.equal(h.button.disabled, false);
  await act(async () => h.clickRetry());

  assert.equal(h.attempts, 2);
  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
  assert.equal(h.alert, null);
});

test("unmounting before failure settles ignores the stale effect result", async (t) => {
  const h = harness(t, { failures: 1 });
  h.mountAndUnmountBeforeSettling();
  await act(async () => {});

  assert.equal(h.attempts, 1);
  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, false);
  assert.equal(h.container.childNodes.length, 0);
  assert.deepEqual(h.logs, []);
});

test("unmounting does not tear down a successfully initialized runtime", async (t) => {
  const h = harness(t);
  await h.mount();
  await h.unmount();

  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
  assert.equal(h.container.childNodes.length, 0);
});
