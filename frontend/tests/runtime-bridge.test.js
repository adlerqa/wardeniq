import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../src/compat/runtime/RuntimeBridge.jsx", import.meta.url),
  "utf8",
);
const controllersDirectory = new URL(
  "../src/compat/runtime/controllers/",
  import.meta.url,
);
const controllerFiles = readdirSync(controllersDirectory)
  .filter((name) => name.endsWith(".js"))
  .sort();
const controllerSources = Object.fromEntries(
  controllerFiles.map((name) => [
    `./controllers/${name}?raw`,
    readFileSync(new URL(name, controllersDirectory), "utf8"),
  ]),
);
const loaderSource = source
  .replace(/^import \{[^}]+\} from "react";\s*/m, "")
  .replace(
    /^import (\w+) from "(\.\/controllers\/[^"]+\?raw)";$/gm,
    (_, binding, path) =>
      `const ${binding} = __controllerSources[${JSON.stringify(path)}];`,
  )
  .split("/**\n * Compatibility bridge")[0]
  .concat("\nglobalThis.testLoadRuntime = loadRuntime;");

function harness({ ready = false, beforeAppend = () => {} } = {}) {
  const scripts = [];
  const window = { __WARDENIQ_RUNTIME_READY__: ready };
  const document = {
    createElement() {
      return { dataset: {}, textContent: "" };
    },
    body: {
      appendChild(script) {
        beforeAppend(script, window);
        scripts.push(script);
      },
    },
  };
  const context = vm.createContext({
    __controllerSources: controllerSources,
    document,
    window,
  });
  vm.runInContext(loaderSource, context);

  return { loadRuntime: context.testLoadRuntime, scripts, window, document };
}

test("injects all eager controller sources in filename order into one classic script", async () => {
  const importedFiles = Array.from(
    source.matchAll(/^import \w+ from "\.\/controllers\/([^"]+)\?raw";$/gm),
    (match) => match[1],
  );
  assert.equal(importedFiles.length, 18);
  assert.deepEqual(importedFiles, controllerFiles);
  const h = harness();

  await h.loadRuntime();

  assert.equal(h.scripts.length, 1);
  assert.equal(h.scripts[0].dataset.wardeniqRuntime, "compat");
  assert.equal(h.scripts[0].type, undefined);
  assert.equal(
    h.scripts[0].textContent,
    `${Object.values(controllerSources).join("\n")}\n//# sourceURL=wardeniq-compat-runtime.js`,
  );
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
});

test("shares an in-flight load and does not inject the runtime twice", async () => {
  const h = harness({
    beforeAppend(script, window) {
      assert.equal(window.__WARDENIQ_RUNTIME_READY__, false);
    },
  });

  const firstLoad = h.loadRuntime();
  const secondLoad = h.loadRuntime();
  assert.strictEqual(firstLoad, secondLoad);
  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, false);

  await Promise.all([firstLoad, secondLoad]);
  await h.loadRuntime();

  assert.equal(h.scripts.length, 1);
});

test("does not inject when the window is already ready", async () => {
  const h = harness({ ready: true });

  await h.loadRuntime();

  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
});

test("rechecks readiness before a pending injection", async () => {
  const h = harness();
  const pendingLoad = h.loadRuntime();
  h.window.__WARDENIQ_RUNTIME_READY__ = true;

  await pendingLoad;

  assert.equal(h.scripts.length, 0);
});

test("reports a failed insertion to concurrent callers and allows a later retry", async () => {
  let appendCount = 0;
  const failure = new Error("temporary insertion failure");
  const h = harness({
    beforeAppend() {
      appendCount++;
      if (appendCount === 1) throw failure;
    },
  });

  const firstLoad = h.loadRuntime();
  const secondLoad = h.loadRuntime();
  assert.strictEqual(firstLoad, secondLoad);
  await Promise.all([
    assert.rejects(firstLoad, (error) => error === failure),
    assert.rejects(secondLoad, (error) => error === failure),
  ]);
  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, false);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(appendCount, 1);

  await h.loadRuntime();
  await h.loadRuntime();

  assert.equal(appendCount, 2);
  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
});

test("turns synchronous script creation failures into retryable rejections", async () => {
  const h = harness();
  const failure = new Error("script creation failure");
  const createElement = h.document.createElement;
  h.document.createElement = () => {
    throw failure;
  };
  await assert.rejects(h.loadRuntime(), (error) => error === failure);

  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, false);
  h.document.createElement = createElement;
  await h.loadRuntime();
  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
});
