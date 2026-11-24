import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

// issue #111: the Switch database flow must (a) never present a failed verification as
// an ordinary success, (b) let the user knowingly start a best-effort copy while
// wardenIQ is busy, and (c) show warnings that accompany a best-effort success.
// Renders the real DatabaseSettingsCard (features/configuration, was runDbSwitch() in
// 06-configuration.js) against scripted api / watchJob / confirmModal stubs.

const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(
  new URL("../src/features/configuration/components/DatabaseSettingsCard.jsx", import.meta.url),
);
const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "neutral",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"],
  logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

// `apiScript`: array of results / errors consumed one per POST /api/db-migrate.
// `job`: what watchJob() reports to the callback (null = never calls back).
// `confirms`: answers to the confirm dialogs, in order; the first one answers the
// "Switch database?" question asked by the button.
function harness({ apiScript, job = null, confirms = [] }) {
  const apiCalls = [];
  const confirmCalls = [];
  const answers = [true, ...confirms];
  Object.assign(window, {
    watchJob: (id, cb) => {
      if (job) cb(job);
    },
    confirmModal: async (o) => {
      confirmCalls.push(o);
      return answers.length ? answers.shift() : false;
    },
    toast: () => {},
  });
  async function fakeFetch(path, opts) {
    apiCalls.push({ path, body: JSON.parse(opts.body) });
    const next = apiScript.shift();
    if (next instanceof Error)
      return { status: 409, ok: false, text: async () => JSON.stringify({ detail: next.message }) };
    return { status: 200, ok: true, text: async () => JSON.stringify(next) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout,
  });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const db = { status: "ready", data: { boot: { ready: true } }, error: "", shown: true };
  const $ = (sel) => container.querySelector(sel);
  return {
    $,
    apiCalls,
    // The "Switch database?" question is not part of what these tests check.
    confirmCalls: { get length() { return confirmCalls.length - 1; }, at: (i) => confirmCalls[i + 1] },
    status: () => $("#cfg-db-status").innerHTML,
    async run(uri = "mongodb://target.example.test/") {
      await act(async () => root.render(React.createElement(module.exports.default, { db, loadDbStatus() {} })));
      const input = $("#cfg-db-uri");
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      await act(async () => {
        setter.call(input, uri);
        input.dispatchEvent(new window.Event("input", { bubbles: true }));
      });
      await act(async () => {
        $("#cfg-db-switch-go").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        for (let i = 0; i < 10; i++) await settle();
      });
    },
    async unmount() {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}

test("a failed verification is shown as a failure, never as the success message", async () => {
  const error =
    "The copy did not pass verification, so wardenIQ was NOT switched to the new database: " +
    "'test_cases': 120 documents were copied but the target has 118.";
  const h = harness({ apiScript: [{ job_id: "j1" }], job: { status: "failed", error } });
  await h.run();
  assert.match(h.status(), /Couldn't switch:/);
  assert.match(h.status(), /NOT switched/);
  assert.match(h.status(), /120 documents were copied but the target has 118/);
  assert.doesNotMatch(h.status(), /Your data has been copied/);
  assert.doesNotMatch(h.status(), /docker compose up/);
  assert.equal(h.$("#cfg-db-switch-go").disabled, false); // user can retry
  assert.equal(h.$("#cfg-db-uri").value, "mongodb://target.example.test/"); // input kept
});

test("a verified success shows the normal message and clears the input", async () => {
  const h = harness({
    apiScript: [{ job_id: "j1" }],
    job: { status: "succeeded", result: { apply_cmd: "docker compose up -d", warnings: [] } },
  });
  await h.run();
  assert.match(h.status(), /Your data has been copied to the new database/);
  assert.match(h.status(), /docker compose up -d/);
  assert.doesNotMatch(h.status(), /class="warn"/);
  assert.equal(h.$("#cfg-db-uri").value, "");
});

test("warnings that accompany a best-effort success are displayed, escaped", async () => {
  const h = harness({
    apiScript: [{ job_id: "j1" }],
    job: { status: "succeeded", result: { warnings: ["'jobs': 4 copied but the source now has 5 <b>x</b>"] } },
  });
  await h.run();
  assert.match(h.status(), /Your data has been copied/);
  assert.match(h.status(), /<div class="warn">[^<]*source now has 5 &lt;b&gt;x&lt;\/b&gt;<\/div>/);
  assert.doesNotMatch(h.status(), /<b>x<\/b>/); // the injected markup is neutralised
});

test("the success message tells the user how to verify the new database after the restart", async () => {
  const hint = "After restarting, sign in as an admin and open /api/db-status: boot.ready should be true <b>x</b>";
  const h = harness({
    apiScript: [{ job_id: "j1" }],
    job: { status: "succeeded", result: { apply_cmd: "docker compose up -d", post_restart_check: hint } },
  });
  await h.run();
  assert.match(h.status(), /Your data has been copied/);
  assert.match(h.status(), /<div class="muted">After restarting, sign in as an admin and open \/api\/db-status/);
  assert.doesNotMatch(h.status(), /<b>x<\/b>/); // escaped, not injected
});

test("no post-restart hint is rendered when the job result has none", async () => {
  const h = harness({
    apiScript: [{ job_id: "j1" }],
    job: { status: "succeeded", result: { apply_cmd: "docker compose up -d" } },
  });
  await h.run();
  assert.doesNotMatch(h.status(), /class="muted"/);
});

test("the request carries override_busy only when the user accepted it", async () => {
  const a = harness({ apiScript: [{ job_id: "j1" }] });
  await a.run();
  assert.deepEqual(a.apiCalls[0].body, {
    target_uri: "mongodb://target.example.test/", overwrite: false, override_busy: false,
  });
  await a.unmount();
  // Accepting both questions (replace the data, start while busy) sets both flags.
  const b = harness({
    apiScript: [
      new Error("The target database already contains data. Re-run with 'overwrite'."),
      new Error("wardenIQ is currently busy (Generate tests). Wait for it to finish, or start anyway."),
      { job_id: "j2" },
    ],
    confirms: [true, true],
  });
  await b.run();
  assert.equal(b.apiCalls[2].body.override_busy, true);
  assert.equal(b.apiCalls[2].body.overwrite, true);
});

test("a busy refusal offers 'start anyway' and retries with override_busy when accepted", async () => {
  const busy = new Error("wardenIQ is currently busy (Generate tests). Wait for it to finish, or start anyway.");
  const h = harness({
    apiScript: [busy, { job_id: "j9" }], confirms: [true],
    job: { status: "succeeded", result: {} },
  });
  await h.run();
  assert.equal(h.confirmCalls.length, 1);
  assert.match(h.confirmCalls.at(0).body, /best-effort snapshot/);
  assert.equal(h.apiCalls.length, 2);
  assert.equal(h.apiCalls[0].body.override_busy, false);
  assert.equal(h.apiCalls[1].body.override_busy, true);
  assert.match(h.status(), /Your data has been copied/);
});

test("a sync-running refusal is also overridable", async () => {
  const busy = new Error("A GitHub/GitLab sync is currently running. Wait for it to finish, or start anyway");
  const h = harness({ apiScript: [busy, { job_id: "j9" }], confirms: [true], job: { status: "succeeded", result: {} } });
  await h.run();
  assert.equal(h.apiCalls[1].body.override_busy, true);
});

test("declining the busy prompt cancels without a second request", async () => {
  const busy = new Error("wardenIQ is currently busy (Generate tests). Wait for it to finish.");
  const h = harness({ apiScript: [busy], confirms: [false] });
  await h.run();
  assert.equal(h.apiCalls.length, 1);
  assert.match(h.status(), /Cancelled/);
  assert.equal(h.$("#cfg-db-switch-go").disabled, false);
});

test("'migration already in progress' is NOT overridable: error shown, no prompt", async () => {
  const h = harness({ apiScript: [new Error("A database migration is already in progress. Wait for it to finish.")] });
  await h.run();
  assert.equal(h.confirmCalls.length, 0);
  assert.equal(h.apiCalls.length, 1);
  assert.match(h.status(), /already in progress/);
  assert.match(h.status(), /class="err"/);
});

test("the existing 'replace existing data' prompt still works and keeps override_busy", async () => {
  // Busy accepted first, then the target turns out to have data.
  const h = harness({
    apiScript: [
      new Error("wardenIQ is currently busy (Generate tests). Wait for it to finish, or start anyway."),
      new Error("The target database already contains data. Re-run with 'overwrite'."),
      { job_id: "j3" },
    ],
    confirms: [true, true], job: { status: "succeeded", result: {} },
  });
  await h.run();
  assert.equal(h.apiCalls[2].body.overwrite, true);
  assert.equal(h.apiCalls[2].body.override_busy, true);
  assert.match(h.status(), /Your data has been copied/);
});

test("an empty connection string asks for one without a request or a question", async () => {
  const h = harness({ apiScript: [] });
  await h.run("   ");
  assert.equal(h.apiCalls.length, 0);
  assert.equal(h.confirmCalls.length, -1); // not even the "Switch database?" question
  assert.equal(h.status(), '<span class="warn">Enter a database connection string.</span>');
});

test("while the copy runs the button reads Starting… and progress is shown", async () => {
  const h = harness({ apiScript: [{ job_id: "j1" }], job: { status: "running", progress: 40 } });
  await h.run();
  assert.equal(h.$("#cfg-db-switch-go").textContent, "Starting…");
  assert.ok(h.$("#cfg-db-switch-go").disabled);
  assert.equal(h.status(), "Transferring your data… 40%");
  assert.match(h.$("#cfg-db-status").className, /is-saving/);
});
