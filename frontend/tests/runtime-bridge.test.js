import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../src/compat/runtime/RuntimeBridge.jsx", import.meta.url),
  "utf8",
);
const loaderSource = source
  .replace(/^import \{ useEffect \} from "react";\s*/m, "")
  .replace(
    /const controllerModules = import\.meta\.glob\([\s\S]*?\n\);\n/,
    "const controllerModules = __controllerModules;\n",
  )
  .split("/**\n * Compatibility bridge")[0]
  .concat("\nglobalThis.testLoadRuntime = loadRuntime;");

function harness(controllerModules = {}) {
  const scripts = [];
  const window = { __WARDENIQ_RUNTIME_READY__: false };
  const document = {
    createElement() {
      return { dataset: {}, textContent: "" };
    },
    body: {
      appendChild(script) {
        scripts.push(script);
      },
    },
  };
  const context = vm.createContext({
    __controllerModules: controllerModules,
    document,
    window,
  });
  vm.runInContext(loaderSource, context);

  return { loadRuntime: context.testLoadRuntime, scripts, window };
}

test("loads controllers in filename order into one classic script", async () => {
  const h = harness({
    "./controllers/10-users.js": async () => "users",
    "./controllers/02-projects.js": async () => "projects",
  });

  await h.loadRuntime();

  assert.equal(h.scripts.length, 1);
  assert.equal(h.scripts[0].dataset.wardeniqRuntime, "compat");
  assert.match(h.scripts[0].textContent, /^projects\nusers\n\/\/# sourceURL=/);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
});

test("shares an in-flight load and does not inject the runtime twice", async () => {
  let resolveController;
  let loadCount = 0;
  const h = harness({
    "./controllers/00-core.js": () => {
      loadCount++;
      return new Promise((resolve) => {
        resolveController = resolve;
      });
    },
  });

  const firstLoad = h.loadRuntime();
  const secondLoad = h.loadRuntime();
  assert.strictEqual(firstLoad, secondLoad);
  assert.equal(loadCount, 1);

  resolveController("core");
  await Promise.all([firstLoad, secondLoad]);
  await h.loadRuntime();

  assert.equal(h.scripts.length, 1);
});

test("retries after a controller import fails", async () => {
  let loadCount = 0;
  const h = harness({
    "./controllers/00-core.js": () => {
      loadCount++;
      return loadCount === 1
        ? Promise.reject(new Error("temporary import failure"))
        : Promise.resolve("core");
    },
  });

  await assert.rejects(h.loadRuntime(), /temporary import failure/);
  await h.loadRuntime();

  assert.equal(loadCount, 2);
  assert.equal(h.scripts.length, 1);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, true);
});

test("reports a missing controller set instead of marking the runtime ready", async () => {
  const h = harness();

  await assert.rejects(
    h.loadRuntime(),
    /No compatibility runtime controllers found/,
  );

  assert.equal(h.scripts.length, 0);
  assert.equal(h.window.__WARDENIQ_RUNTIME_READY__, false);
});
