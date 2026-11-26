import assert from "node:assert/strict";
import test from "node:test";

import { STALL_MS, jobLogLines, renderJobLog, usageLogLines, watchJob } from "../src/lib/jobs.js";
import { fmtTok, fmtUsd } from "../src/lib/format.js";

// A scripted EventSource, timer queue and clock for watchJob.
function harness({ noStream = false } = {}) {
  const ticks = [], gets = [], replies = [], timers = [], streams = [];
  let clock = 0;
  class ES {
    constructor(url) {
      if (noStream) throw new Error("no EventSource");
      Object.assign(this, { url, h: {}, closed: false });
      streams.push(this);
    }
    addEventListener(k, f) { this.h[k] = f; }
    close() { this.closed = true; }
  }
  const deps = {
    EventSource: ES,
    api: async (p) => { gets.push(p); const r = replies.shift(); if (r instanceof Error) throw r; return r; },
    setTimeout: (fn, ms) => timers.push({ fn, ms }) ,
    clearTimeout: (id) => { timers[id - 1].cleared = true; },
    now: () => clock,
  };
  return {
    ticks, gets, replies, timers, streams, deps,
    advance: (ms) => { clock += ms; },
    send: (kind, job) => streams[0].h[kind]({ data: JSON.stringify(job) }),
    fire: async () => { const t = timers.find((x) => !x.cleared && !x.done); t.done = true; await t.fn(); return t.ms; },
    pending: () => timers.filter((x) => !x.cleared && !x.done).length,
    watch: (id, ms) => watchJob(id, (j) => ticks.push(j), ms, deps),
  };
}

test("stream updates reach the caller until the job finishes, then everything stops", async () => {
  const h = harness();
  h.watch("j1");
  assert.equal(h.streams[0].url, "/api/jobs/j1/stream");
  h.send("update", { status: "running", stage: "a", updated_at: 1 });
  h.send("done", { status: "done" });
  h.send("update", { status: "running" });
  assert.deepEqual(h.ticks.map((t) => t.status), ["running", "done"]);
  assert.equal(h.streams[0].closed, true);
  assert.equal(h.pending(), 0);
});

test("the safety poll runs alongside, retries after errors and sees the end", async () => {
  const h = harness();
  h.watch("j2", 500);
  h.streams[0].onerror();
  assert.equal(h.streams[0].closed, true);
  h.replies.push(new Error("offline"), { status: "failed", error: "boom" });
  assert.equal(await h.fire(), 500);
  assert.deepEqual(h.ticks, []);
  await h.fire();
  assert.deepEqual(h.gets, ["/api/jobs/j2", "/api/jobs/j2"]);
  assert.deepEqual(h.ticks, [{ status: "failed", error: "boom" }]);
  assert.equal(h.pending(), 0);
});

test("no progress for two minutes while running is reported as a stalled failure", async () => {
  const h = harness({ noStream: true });
  h.watch("j3");
  h.replies.push({ status: "running", updated_at: 5 }, { status: "running", updated_at: 5 });
  assert.equal(await h.fire(), 3000);
  h.advance(STALL_MS + 1);
  await h.fire();
  assert.deepEqual(h.ticks.at(-1), {
    status: "failed", updated_at: 5, stage: "stalled", error: "Worker appears unresponsive — please retry.",
  });
  assert.equal(h.pending(), 0);
});

test("stop() ends the stream and the poll", async () => {
  const h = harness();
  const stop = h.watch("j4");
  stop();
  assert.equal(h.streams[0].closed, true);
  assert.equal(h.pending(), 0);
});

test("job log text: progress, error, token usage", () => {
  const usage = {
    total_tokens: 1234, cost_usd: 0.5,
    by_model: {
      small: { total_tokens: 10, prompt_tokens: 4, completion_tokens: 6, cost_usd: 0.01, estimated: true },
      big: { total_tokens: 1224, prompt_tokens: 1000, completion_tokens: 224, cost_usd: null },
    },
  };
  assert.deepEqual(usageLogLines(usage), [
    "", "── LLM tokens ──",
    `big: ${fmtTok(1224)} tok  (${fmtTok(1000)} in / 224 out)  —`,
    "small (~est): 10 tok  (4 in / 6 out)  $0.0100",
    `TOTAL: ${fmtTok(1234)} tok · $0.5000`,
  ]);
  assert.deepEqual(usageLogLines({ total_tokens: 0 }), []);
  assert.equal(fmtUsd(12.345), "$12.35");
  assert.deepEqual(jobLogLines({ logs: [{ progress: 40, stage: "Generating" }, { stage: "x" }], error: "boom" }),
    [" 40%  Generating", "     x", "ERR  boom"]);
  const el = { style: {}, textContent: "", scrollTop: 0, scrollHeight: 90 };
  globalThis.document = { querySelector: (s) => (s === "#log" ? el : null) };
  renderJobLog("#log", { logs: [{ progress: 100, stage: "done" }] });
  assert.deepEqual(el, { style: { display: "block" }, textContent: "100%  done", scrollTop: 90, scrollHeight: 90 });
  renderJobLog("#log", {});
  assert.equal(el.style.display, "none");
  renderJobLog("#missing", {});
  delete globalThis.document;
});
