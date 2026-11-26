import assert from "node:assert/strict";
import test from "node:test";

import { createBootPoller, smtpStatusWithRetry, loginMethod } from "../src/features/auth/lib/login.js";

// The sign-in screen's boot-status banner (features/auth/lib/login.js).
function harness(api) {
  const state = { shown: true, hidden: true, text: "" };
  const timers = [];
  const poller = createBootPoller({
    api,
    isShown: () => state.shown,
    show: (text) => Object.assign(state, { hidden: false, text }),
    hide: () => Object.assign(state, { hidden: true, text: "" }),
    setTimeout: (fn, delay) => timers.push({ fn, delay }),
  });
  return { state, timers, poller };
}

test("shows safe boot failure and recovery guidance as text", async () => {
  const h = harness(async () => ({ ready: false, detail: "Vector Search unavailable",
    recovery: "Run scripts/reset-admin-password.sh <operator>" }));
  await h.poller.start();
  assert.equal(h.state.hidden, false);
  assert.equal(h.state.text, "Vector Search unavailable Run scripts/reset-admin-password.sh <operator>");
  assert.equal(h.timers[0].delay, 3000);
});

test("healthy sign-in leaves the boot banner hidden and stops polling", async () => {
  const h = harness(async () => ({ ready: true, detail: "" }));
  await h.poller.start();
  assert.equal(h.state.hidden, true);
  assert.equal(h.state.text, "");
  assert.equal(h.timers.length, 0);
});

test("a startup warning disappears once boot completes", async () => {
  let ready = false;
  const h = harness(async () => ({ ready, detail: "Connecting" }));
  await h.poller.start();
  ready = true;
  await h.timers.shift().fn();
  assert.equal(h.state.hidden, true);
  assert.equal(h.timers.length, 0);
});

test("leaving the login screen stops polling", async () => {
  let calls = 0;
  const h = harness(async () => { calls++; return { ready: false, detail: "Starting" }; });
  await h.poller.start();
  h.state.shown = false;
  await h.timers.shift().fn();
  assert.equal(calls, 1);
  assert.equal(h.timers.length, 0);
});

test("a transient request error preserves the diagnosis and retries", async () => {
  const h = harness(async () => { throw new Error("offline"); });
  h.state.text = "Useful diagnosis";
  await h.poller.start();
  assert.equal(h.state.text, "Useful diagnosis");
  assert.equal(h.timers.length, 1);
});

test("an old login request cannot overwrite the current login state", async () => {
  let resolve;
  const h = harness(() => new Promise((done) => { resolve = done; }));
  const pending = h.poller.start();
  h.poller.stop();
  resolve({ ready: false, detail: "Stale" });
  await pending;
  assert.equal(h.state.text, "");
  assert.equal(h.timers.length, 0);
});

test("smtp status: one retry, then null; null means password sign-in", async () => {
  let n = 0;
  const waits = [];
  const flaky = async () => { if (n++ === 0) throw new Error("blip"); return { smtp_setup: true }; };
  assert.deepEqual(await smtpStatusWithRetry(flaky, async (ms) => waits.push(ms)), { smtp_setup: true });
  assert.deepEqual(waits, [250]);
  const down = async () => { throw new Error("down"); };
  assert.equal(await smtpStatusWithRetry(down, async () => {}), null);
  assert.equal(loginMethod(null), "password");
  assert.equal(loginMethod({ smtp_setup: false }), "password");
  assert.equal(loginMethod({ smtp_setup: true }), "otp");
});
