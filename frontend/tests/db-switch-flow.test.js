import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// issue #111: the Switch database flow must (a) never present a failed verification as
// an ordinary success, (b) let the user knowingly start a best-effort copy while
// wardenIQ is busy, and (c) show warnings that accompany a best-effort success.
// Exercises the real runDbSwitch() source (same harness style as the other tests here)
// against scripted api / watchJob / confirmModal stubs.

const coreSource = readFileSync(
  new URL("../src/compat/runtime/controllers/00-core.js", import.meta.url), "utf8",
);
const escSource = coreSource.slice(
  coreSource.indexOf("const esc = (s) =>"),
  coreSource.indexOf("const escAttr = esc;") + "const escAttr = esc;".length,
);
const cfg = readFileSync(
  new URL("../src/compat/runtime/controllers/06-configuration.js", import.meta.url), "utf8",
);
const switchSource = cfg.slice(
  cfg.indexOf("async function runDbSwitch"),
  cfg.indexOf('if ($("#cfg-db-switch-go"))'),
);

function makeNode() {
  const classes = new Set();
  return {
    value: "", textContent: "", innerHTML: "", disabled: false,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
    },
  };
}

// `apiScript`: array of results/throwers consumed one per api() call.
// `job`: what watchJob() reports to the callback (null = never calls back).
function harness({ apiScript, job = null, confirms = [] }) {
  const nodes = new Map();
  const $ = (sel) => {
    if (!nodes.has(sel)) nodes.set(sel, makeNode());
    return nodes.get(sel);
  };
  $("#cfg-db-uri").value = "mongodb://target.example.test/";
  const apiCalls = [];
  const confirmCalls = [];
  const context = vm.createContext({
    $,
    api: async (path, opts) => {
      apiCalls.push({ path, body: JSON.parse(opts.body) });
      const next = apiScript.shift();
      if (next instanceof Error) throw next;
      return next;
    },
    watchJob: (id, cb) => { if (job) cb(job); },
    confirmModal: async (o) => { confirmCalls.push(o); return confirms.length ? confirms.shift() : false; },
  });
  vm.runInContext(escSource, context);
  vm.runInContext(switchSource, context);
  return { $, context, apiCalls, confirmCalls, status: () => $("#cfg-db-status").innerHTML };
}

test("a failed verification is shown as a failure, never as the success message", async () => {
  const error =
    "The copy did not pass verification, so wardenIQ was NOT switched to the new database: " +
    "'test_cases': 120 documents were copied but the target has 118.";
  const h = harness({ apiScript: [{ job_id: "j1" }], job: { status: "failed", error } });
  await h.context.runDbSwitch(false);
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
  await h.context.runDbSwitch(false);
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
  await h.context.runDbSwitch(false, true);
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
  await h.context.runDbSwitch(false);
  assert.match(h.status(), /Your data has been copied/);
  assert.match(h.status(), /<div class="muted">After restarting, sign in as an admin and open \/api\/db-status/);
  assert.doesNotMatch(h.status(), /<b>x<\/b>/); // escaped, not injected
});

test("no post-restart hint is rendered when the job result has none", async () => {
  const h = harness({
    apiScript: [{ job_id: "j1" }],
    job: { status: "succeeded", result: { apply_cmd: "docker compose up -d" } },
  });
  await h.context.runDbSwitch(false);
  assert.doesNotMatch(h.status(), /class="muted"/);
});

test("the request carries override_busy only when the user accepted it", async () => {
  const a = harness({ apiScript: [{ job_id: "j1" }] });
  await a.context.runDbSwitch(false);
  assert.deepEqual(a.apiCalls[0].body, {
    target_uri: "mongodb://target.example.test/", overwrite: false, override_busy: false,
  });
  const b = harness({ apiScript: [{ job_id: "j2" }] });
  await b.context.runDbSwitch(true, true);
  assert.equal(b.apiCalls[0].body.override_busy, true);
  assert.equal(b.apiCalls[0].body.overwrite, true);
});

test("a busy refusal offers 'start anyway' and retries with override_busy when accepted", async () => {
  const busy = new Error("wardenIQ is currently busy (Generate tests). Wait for it to finish, or start anyway.");
  const h = harness({
    apiScript: [busy, { job_id: "j9" }], confirms: [true],
    job: { status: "succeeded", result: {} },
  });
  await h.context.runDbSwitch(false);
  assert.equal(h.confirmCalls.length, 1);
  assert.match(h.confirmCalls[0].body, /best-effort snapshot/);
  assert.equal(h.apiCalls.length, 2);
  assert.equal(h.apiCalls[0].body.override_busy, false);
  assert.equal(h.apiCalls[1].body.override_busy, true);
  assert.match(h.status(), /Your data has been copied/);
});

test("a sync-running refusal is also overridable", async () => {
  const busy = new Error("A GitHub/GitLab sync is currently running. Wait for it to finish, or start anyway");
  const h = harness({ apiScript: [busy, { job_id: "j9" }], confirms: [true], job: { status: "succeeded", result: {} } });
  await h.context.runDbSwitch(false);
  assert.equal(h.apiCalls[1].body.override_busy, true);
});

test("declining the busy prompt cancels without a second request", async () => {
  const busy = new Error("wardenIQ is currently busy (Generate tests). Wait for it to finish.");
  const h = harness({ apiScript: [busy], confirms: [false] });
  await h.context.runDbSwitch(false);
  assert.equal(h.apiCalls.length, 1);
  assert.match(h.status(), /Cancelled/);
  assert.equal(h.$("#cfg-db-switch-go").disabled, false);
});

test("'migration already in progress' is NOT overridable: error shown, no prompt", async () => {
  const h = harness({ apiScript: [new Error("A database migration is already in progress. Wait for it to finish.")] });
  await h.context.runDbSwitch(false);
  assert.equal(h.confirmCalls.length, 0);
  assert.equal(h.apiCalls.length, 1);
  assert.match(h.status(), /already in progress/);
  assert.match(h.status(), /class="err"/);
});

test("the existing 'replace existing data' prompt still works and keeps override_busy", async () => {
  const h = harness({
    apiScript: [new Error("The target database already contains data. Re-run with 'overwrite'."), { job_id: "j3" }],
    confirms: [true], job: { status: "succeeded", result: {} },
  });
  await h.context.runDbSwitch(false, true);
  assert.equal(h.apiCalls[1].body.overwrite, true);
  assert.equal(h.apiCalls[1].body.override_busy, true);
});
