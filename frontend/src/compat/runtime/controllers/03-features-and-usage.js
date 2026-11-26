// ---- shared job helpers ----
// The Features screen (list, "New feature", workspace) and the Usage screen
// are React (#257). What stays here is shared by several screens until
// 00-core.js moves: number formats, the job log, and the job watcher.
function fmtTok(n) {
  return Number(n || 0).toLocaleString();
}
function fmtUsd(c) {
  return c == null ? "—" : "$" + Number(c).toFixed(Number(c) < 1 ? 4 : 2);
}

function usageLogLines(u) {
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
function renderJobLog(target, j) {
  const el = $(target);
  if (!el) return;
  const logs = (j.logs || []).map(
    (x) =>
      `${x.progress == null ? "   " : String(x.progress).padStart(3) + "%"}  ${x.stage || ""}`,
  );
  if (j.error) logs.push(`ERR  ${j.error}`);
  logs.push(...usageLogLines(j.usage));
  el.style.display = logs.length ? "block" : "none";
  el.textContent = logs.join("\n");
  el.scrollTop = el.scrollHeight;
}
// The LLM Usage & Cost screen is React (src/features/usage, #257); it
// registers window.loadUsage. fmtTok / fmtUsd / usageLogLines above stay for
// the job logs and the cost estimate.
// Generic durable job watcher. SSE gives immediate stage/log updates; polling is
// retained as a fallback for proxies that buffer or block event streams.
function watchJob(jobId, onTick, intervalMs) {
  let stop = false,
    settled = false,
    es = null,
    pollTimer = null;
  // Client-side stall detector — if the server's updated_at never advances
  // while status stays "running", the worker thread is likely dead (backend
  // sweeper will confirm it shortly). Deliver a synthetic "failed" tick so the
  // loader in the caller is replaced instead of spinning forever.
  let lastUpdatedAt = null,
    lastAdvanceMs = Date.now();
  const STALL_MS = 120000; // 2 min without progress = give up; slightly longer than backend sweep default
  const finish = () => {
    settled = true;
    if (es) {
      es.close();
      es = null;
    }
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  };
  const deliver = (j) => {
    if (stop || settled) return;
    // Track heartbeat: any change in updated_at (or stage/progress) is progress.
    const beat = j && j.updated_at != null ? j.updated_at : null;
    if (beat !== null && beat !== lastUpdatedAt) {
      lastUpdatedAt = beat;
      lastAdvanceMs = Date.now();
    }
    if (j && j.status === "running" && Date.now() - lastAdvanceMs > STALL_MS) {
      const synth = Object.assign({}, j, {
        status: "failed",
        stage: "stalled",
        error: j.error || "Worker appears unresponsive — please retry.",
      });
      onTick(synth);
      finish();
      return;
    }
    onTick(j);
    if (j.status !== "running") finish();
  };
  // Safety poll ALWAYS runs alongside SSE (slow cadence). SSE gives instant updates,
  // but if the stream goes quiet on a long job (proxy buffering, busy event loop)
  // without firing onerror, the poll still catches the terminal state so the UI never
  // gets stuck "in progress" after the job has finished.
  const poll = async () => {
    if (stop || settled) return;
    try {
      deliver(await api("/api/jobs/" + jobId));
    } catch (e) {}
    if (!stop && !settled) pollTimer = setTimeout(poll, intervalMs || 3000);
  };
  try {
    es = new EventSource(`/api/jobs/${jobId}/stream`);
    es.addEventListener("update", (e) => deliver(JSON.parse(e.data)));
    es.addEventListener("done", (e) => deliver(JSON.parse(e.data)));
    es.onerror = () => {
      if (es) {
        es.close();
        es = null;
      }
    }; // SSE dropped — the safety poll carries on
  } catch (e) {}
  pollTimer = setTimeout(poll, intervalMs || 3000); // always-on safety net
  return () => {
    stop = true;
    finish();
  };
}

// Project list → Features screen glue (moved from 02-projects.js when the
// Projects screen moved to React, #257).
window.openProjectFeatures = async (pid) => {
  currentProject = pid;
  currentFeature = null;
  navigateTo("features");
  await loadFeatures();
  showFeatureList();
};
