/**
 * Background jobs: the durable job watcher and the job log (was
 * compat/runtime/controllers/03-features-and-usage.js). useSharedGlobals.js
 * registers watchJob / renderJobLog / usageLogLines on window for the bridge.
 */
import { api } from "./api.js";
import { fmtTok, fmtUsd } from "./format.js";

/** Token-usage lines appended to a job log ([] when the job used no tokens). */
export function usageLogLines(u) {
  if (!u || !u.total_tokens) return [];
  const out = ["", "── LLM tokens ──"];
  Object.entries(u.by_model || {})
    .sort((a, b) => b[1].total_tokens - a[1].total_tokens)
    .forEach(([m, d]) => {
      out.push(
        `${m}${d.estimated ? " (~est)" : ""}: ${fmtTok(d.total_tokens)} tok  (${fmtTok(d.prompt_tokens)} in / ${fmtTok(d.completion_tokens)} out)  ${fmtUsd(d.cost_usd)}`,
      );
    });
  out.push(`TOTAL: ${fmtTok(u.total_tokens)} tok · ${fmtUsd(u.cost_usd)}`);
  return out;
}

/** Lines of a job's progress log: "  40%  stage", the error, then token usage. */
export function jobLogLines(job, usageLines = usageLogLines) {
  const lines = (job.logs || []).map(
    (x) => `${x.progress == null ? "   " : String(x.progress).padStart(3) + "%"}  ${x.stage || ""}`,
  );
  if (job.error) lines.push(`ERR  ${job.error}`);
  lines.push(...usageLines(job.usage));
  return lines;
}

/**
 * Write a job's log into the element matching `target` (shown only when there
 * is something to show) and keep it scrolled to the end.
 */
export function renderJobLog(target, job) {
  const el = document.querySelector(target);
  if (!el) return;
  const lines = jobLogLines(job);
  el.style.display = lines.length ? "block" : "none";
  el.textContent = lines.join("\n");
  el.scrollTop = el.scrollHeight;
}

/** Two minutes without progress while "running" = the worker is presumed dead. */
export const STALL_MS = 120000;

/**
 * Follow a background job. Server-sent events give immediate updates; a slow
 * safety poll always runs alongside, so a stream that goes quiet (proxy
 * buffering, busy event loop) can't leave the UI stuck "in progress". Calls
 * onTick(job) on every update until the job leaves "running"; if updated_at
 * stops advancing for STALL_MS, delivers a synthetic "failed / stalled" tick.
 * Returns a stop function.
 *
 * `deps` exists for tests: { api, EventSource, setTimeout, clearTimeout, now }.
 */
export function watchJob(jobId, onTick, intervalMs, deps = {}) {
  const get = deps.api || ((p) => api(p));
  const ES = "EventSource" in deps ? deps.EventSource : typeof EventSource !== "undefined" ? EventSource : null;
  const later = deps.setTimeout || ((fn, ms) => setTimeout(fn, ms));
  const cancel = deps.clearTimeout || ((t) => clearTimeout(t));
  const now = deps.now || (() => Date.now());
  let stop = false,
    settled = false,
    es = null,
    pollTimer = null;
  let lastUpdatedAt = null,
    lastAdvanceMs = now();
  const finish = () => {
    settled = true;
    if (es) {
      es.close();
      es = null;
    }
    if (pollTimer) {
      cancel(pollTimer);
      pollTimer = null;
    }
  };
  const deliver = (j) => {
    if (stop || settled) return;
    // Any change in updated_at counts as progress.
    const beat = j && j.updated_at != null ? j.updated_at : null;
    if (beat !== null && beat !== lastUpdatedAt) {
      lastUpdatedAt = beat;
      lastAdvanceMs = now();
    }
    if (j && j.status === "running" && now() - lastAdvanceMs > STALL_MS) {
      onTick({ ...j, status: "failed", stage: "stalled", error: j.error || "Worker appears unresponsive — please retry." });
      finish();
      return;
    }
    onTick(j);
    if (j.status !== "running") finish();
  };
  const poll = async () => {
    if (stop || settled) return;
    try {
      deliver(await get("/api/jobs/" + jobId));
    } catch {
      /* the next poll retries */
    }
    if (!stop && !settled) pollTimer = later(poll, intervalMs || 3000);
  };
  try {
    es = new ES(`/api/jobs/${jobId}/stream`);
    es.addEventListener("update", (e) => deliver(JSON.parse(e.data)));
    es.addEventListener("done", (e) => deliver(JSON.parse(e.data)));
    es.onerror = () => {
      // The stream dropped: the safety poll carries on.
      if (es) {
        es.close();
        es = null;
      }
    };
  } catch {
    /* no EventSource: poll only */
  }
  pollTimer = later(poll, intervalMs || 3000);
  return () => {
    stop = true;
    finish();
  };
}
