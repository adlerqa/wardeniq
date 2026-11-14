import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import vm from "node:vm";

// needsConfig() decides whether boot bounces the admin to Configuration. Run it
// with a stubbed api() so the redirect only happens when the model is unreachable.
const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../src/compat/runtime/controllers/16-boot.js"),
  "utf8",
);
const start = src.indexOf("async function needsConfig");
const end = src.indexOf("async function startApp");
assert.ok(start > 0 && end > start, "needsConfig should exist in 16-boot.js");

function harness(api, me) {
  const context = vm.createContext({ api, ME: me });
  vm.runInContext(src.slice(start, end), context);
  return () => context.needsConfig();
}

test("a configured instance never probes or redirects", async () => {
  const calls = [];
  const run = harness(async (p) => { calls.push(p); return { configured: true }; },
    { role: "admin" });
  assert.equal(await run(), false);
  assert.deepEqual(calls, ["/api/settings"]);
});

test("unsaved settings with working defaults do not redirect", async () => {
  const calls = [];
  const run = harness(async (p) => {
    calls.push(p);
    return p === "/api/settings"
      ? { configured: false }
      : { llm: { health: { ok: true } } };
  }, { role: "admin" });
  assert.equal(await run(), false);
  assert.deepEqual(calls, ["/api/settings", "/api/status"]);
});

test("unsaved settings and an unreachable model still redirect", async () => {
  const calls = [];
  const run = harness(async (p) => {
    calls.push(p);
    if (p === "/api/settings") return { configured: false };
    throw new Error("LLM unreachable");
  }, { role: "admin" });
  assert.equal(await run(), true);
  assert.deepEqual(calls, ["/api/settings", "/api/status"]);
});

test("a reachable Ollama that does not have the model yet still redirects", async () => {
  // health() reports ok:false when /api/tags lists no matching model, without
  // any generation call.
  const calls = [];
  const run = harness(async (p) => {
    calls.push(p);
    if (p === "/api/settings") return { configured: false };
    return { llm: { health: { ok: false, provider: "ollama", models: ["other:1b"] } } };
  }, { role: "admin" });
  assert.equal(await run(), true);
  assert.deepEqual(calls, ["/api/settings", "/api/status"]);
});

test("non-admins and settings fetch failures never redirect", async () => {
  const viewer = harness(async () => { throw new Error("should not be called"); }, null);
  assert.equal(await viewer(), false);
  const failed = harness(async (p) => {
    if (p === "/api/settings") throw new Error("settings fetch failed");
    return { ok: true };
  }, { role: "admin" });
  assert.equal(await failed(), false);
});
