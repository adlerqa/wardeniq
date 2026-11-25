// ---- features ----
// The feature list and the "New feature" page are React
// (src/features/features, #257): they register window.loadFeatures /
// showFeatureList / showFeatureCreate / syncFeatureProjects /
// showFeatureWorkspacePage. The workspace (openFeature and below) is still here.
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
// Shows a live loader inside the feature detail while a generation job runs, so the
// user isn't left staring at the old/carried cases wondering if anything happened.
const GEN_WATCHING = new Set();
function watchFeatureGen(jobId, fid) {
  const banner = $("#d-genbanner");
  if (!banner || !jobId) return;
  if (GEN_WATCHING.has(jobId)) return; // avoid stacking watchers for the same job
  GEN_WATCHING.add(jobId);
  // Render the branded analyze loader once (so its animation doesn't reset each poll),
  // then update just the caption line below it as progress streams in.
  banner.innerHTML = `${brandLoader("analyze", { compact: true, messages: ["Generating test cases…", "AI drafting scenarios…", "Normalizing & de-duping…", "Finalizing suite…"] })}<div class="gen-sub" id="d-gencap" style="text-align:center;margin:2px 0 6px">this can take a minute; results will refresh automatically.</div>`;
  watchJob(jobId, (j) => {
    const res = j.result || {};
    if (j.status === "running") {
      const cap = $("#d-gencap");
      if (cap)
        cap.textContent = `${esc(j.stage || "Generating test cases…")} · ${res.cases_new || 0} new · ${res.cases_reused || 0} reused so far`;
    } else if (j.status === "failed") {
      GEN_WATCHING.delete(jobId);
      banner.innerHTML = `<div class="gen-banner err"><span>Generation failed: ${esc(j.error || "unknown error")}</span></div>`;
    } else {
      GEN_WATCHING.delete(jobId);
      banner.innerHTML = "";
      loadFeatures();
      refreshStatus();
      if (fid) openFeature(fid); // refresh the detail so the new cases appear
    }
  });
}
// If a feature has a generation/ingest job still running (e.g. after a refresh or
// navigating away and back), attach the live loader so it never looks "stuck at 0".
async function attachRunningGenWatcher(fid) {
  try {
    const r = await api("/api/jobs?status=running&limit=50");
    const job = (r.jobs || []).find(
      (j) => j.feature_id === fid && ["generate", "ingest"].includes(j.type),
    );
    if (job) watchFeatureGen(job.id, fid);
  } catch (e) {}
}
function featureSummaryText(f) {
  const summary = String(f.summary || "")
    .replace(/\s+/g, " ")
    .trim();
  if (summary && !/^(###|Document:|PRD|HLD|LLD)\b/i.test(summary))
    return summary;
  const text = String(f.text || "")
    .replace(/\s+/g, " ")
    .trim();
  const stripped = text
    .replace(
      /###\s*(document|uploaded documents?|pasted requirement|requirements?)\s*:?.*?(?=\n|$)/gi,
      "",
    )
    .replace(/\b[A-Za-z0-9_-]+\.pdf\b/gi, "")
    .replace(/\b(PRD|HLD|LLD)\s*[—-]\s*[^.?!\n]{0,180}/gi, "")
    .replace(/\b(PRD|HLD|LLD)\b\s*:?/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  const sentence = (stripped.match(/[^.!?]{40,260}[.!?]/) || [])[0];
  if (sentence) return sentence.trim();
  if (stripped.length > 80) return stripped.slice(0, 240).trim() + "…";
  return `${f.name} is ready for review with generated test coverage across functional, API, end-to-end, and reliability scenarios.`;
}
window.showAndScrollToTestCases = () => {
  document
    .querySelectorAll("#d-cases details.case-group")
    .forEach((details) => {
      details.open = true;
    });
  const el = $("#d-cases");
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
};
function renderMatchKey(f) {
  const box = $("#d-match-key");
  if (!box) return;
  const cur = (f && f.match_key) || "";
  box.innerHTML =
    `<span title="PRs whose title/body contain [TAG] auto-map to this feature">PR match tag: </span>` +
    `<input id="d-match-key-input" class="needs-editor" style="width:130px" placeholder="e.g. HOLDS" value="${esc(cur)}"/> ` +
    `<button class="ghost needs-editor" type="button" onclick="saveFeatureMatchKey()">Save</button> ` +
    `<span id="d-match-key-status" class="muted"></span>`;
}
window.saveFeatureMatchKey = async () => {
  if (!currentFeature) return;
  const v = (
    ($("#d-match-key-input") && $("#d-match-key-input").value) ||
    ""
  ).trim();
  try {
    const r = await api(`/api/features/${currentFeature}/match-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_key: v }),
    });
    if (currentFeatureData) currentFeatureData.match_key = r.match_key;
    if ($("#d-match-key-status"))
      $("#d-match-key-status").textContent = r.match_key
        ? `saved · PRs tagged [${esc(r.match_key)}] map here`
        : "cleared";
    toast(
      "PR match tag " +
        (r.match_key ? "set to [" + r.match_key + "]" : "cleared"),
    );
  } catch (e) {
    if ($("#d-match-key-status"))
      $("#d-match-key-status").textContent = e.message || "failed";
    toast(e.message || "failed", true);
  }
};
window.openFeature = async (fid) => {
  try {
    const f = await api("/api/features/" + fid);
    currentFeature = fid;
    currentFeatureData = f;
    currentFeatureCases = f.test_cases || [];
    if ($("#d-genbanner")) $("#d-genbanner").innerHTML = "";
    showFeatureWorkspacePage(); // hides the React list / create pages
    $("#detail-card").hidden = false;
    $("#d-name").textContent = f.name;
    renderMatchKey(f);
    const featureMeta = `Version ${f.version || 1}${f.key ? ` · ${esc(f.key)}` : ""} · ${f.test_cases.length} test case${f.test_cases.length === 1 ? "" : "s"}`;
    $("#d-meta").innerHTML = "";
    $("#d-export").onclick = () => bulkExportSelected("pdf");
    if ($("#d-export-csv"))
      $("#d-export-csv").onclick = () => bulkExportSelected("csv");
    $("#d-jira").style.display = f.key ? "" : "none";
    $("#d-jira").onclick = () => syncJira(fid);
    // version switcher
    const vers = f.versions || [];
    $("#d-version").innerHTML = vers
      .map(
        (v) =>
          `<option value="${v.id}" ${v.id === fid ? "selected" : ""}>v${v.version} · ${v.case_count} cases</option>`,
      )
      .join("");
    $("#d-version-chip").textContent =
      `Version ${f.version || 1} · ${f.test_cases.length} cases`;
    $("#d-version").onchange = (e) => openFeature(e.target.value);
    // version diff summary
    const vd = f.version_diff || {};
    if (vd.mode === "version" || (vd.retired && vd.retired.length)) {
      const ret = vd.retired || [];
      $("#d-verinfo").innerHTML =
        `<div class="explain" style="background:rgba(19,112,171,.08);border:1px solid rgba(19,112,171,.25);border-radius:8px;padding:10px 12px;margin:10px 0;font-size:12.5px">
      <b>Version ${vd.version} diff:</b> ${vd.kept || 0} cases carried over${ret.length ? `, ${ret.length} retired` : ""}, new cases added by generation.
      ${ret.length ? `<details style="margin-top:6px"><summary class="muted">retired cases</summary>${ret.map((r) => `<div class="muted" style="margin-top:4px">• ${esc(r.title || r.id)} — ${esc(r.reason || "")}</div>`).join("")}</details>` : ""}</div>`;
    } else if (vd.mode === "replace") {
      $("#d-verinfo").innerHTML =
        `<div class="muted" style="margin:8px 0">This version was regenerated; ${vd.retired_orphans || 0} obsolete cases removed.</div>`;
    } else {
      $("#d-verinfo").innerHTML = "";
    }
    const bt = {};
    f.test_cases.forEach((c) => {
      const _k = c.category || c.type;
      (bt[_k] = bt[_k] || []).push(c);
    });
    const groups = [
      [
        "api",
        "API",
        "Endpoint happy paths, validation, authorization, and failure handling",
      ],
      [
        "ui",
        "UI validations",
        "Visible fields, controls, and client-side validation",
      ],
      [
        "functional",
        "Business / functional",
        "Business rules and requirement behavior",
      ],
      [
        "e2e",
        "End-to-end",
        "Complete user journeys across UI, API, and persisted state",
      ],
      [
        "nfr",
        "Edge & reliability",
        "Concurrency, resilience, limits, latency, and degraded dependencies",
      ],
      [
        "integration",
        "Integration",
        "Cross-feature scenarios: cases inherited / linked from other features",
      ],
    ];
    // "UI validations" now has its own slider at feature creation (alongside
    // Functional / End-to-end / API / Edge & reliability — see FOCUS_TYPES),
    // so the distribution summary shows it as its own category again. Integration
    // is untouched: it's inherited/linked from other features, not generated by
    // this slider set, so it has no corresponding configuration option.
    const summaryGroups = [
      ["api", "API"],
      ["ui", "UI validations"],
      ["functional", "Business / functional"],
      ["e2e", "End-to-end"],
      ["nfr", "Edge & reliability"],
      ["integration", "Integration"],
    ];
    const overviewStats = summaryGroups
      .map(([t, label]) => {
        const cases = bt[t] || [];
        return `<div class="feature-stat"><b>${cases.length}</b><span>${label}</span></div>`;
      })
      .join("");
    const summaryText = featureSummaryText(f);
    $("#d-overview").innerHTML = `<div class="feature-hero">
    <div class="muted">${esc(featureMeta)}</div>
    <div class="feature-summary">${esc(summaryText)}</div>
    <div class="feature-stats">${overviewStats}</div>

    <div class="feature-action-grid">

  <button
    type="button"
    class="feature-action feature-action-cases"
    onclick="showAndScrollToTestCases()"
  >
   

    <div class="feature-action-content">
      <b>Test cases</b>
      <span>
        Review, filter, execute, and edit ${f.test_cases.length} cases.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>${f.test_cases.length} cases</span>
      <span>Open library</span>
    </div>
  </button>


  <button
    type="button"
    class="feature-action feature-action-validator"
    onclick="navigateTo('validator')"
  >
  

    <div class="feature-action-content">
      <b>Validator</b>
      <span>
        Check requirement clarity and identify missing decisions.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>Requirements</span>
      <span>Review</span>
    </div>
  </button>


  <button
    type="button"
    class="feature-action feature-action-plan"
    onclick="navigateTo('testplan')"
  >
   

    <div class="feature-action-content">
      <b>Test plan</b>
      <span>
        Build the QA strategy and generate an exportable test plan.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>QA strategy</span>
      <span>Generate</span>
    </div>
  </button>


  <button
    type="button"
    class="feature-action feature-action-gap"
    onclick="navigateTo('gap')"
  >
  

    <div class="feature-action-content">
      <b>Gap Analysis</b>
      <span>
        Inspect code and automation coverage with exact commit links.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>Coverage</span>
      <span>Analyze</span>
    </div>
  </button>

</div>



  </div>`;
    const h = groups
      .map(([t, label, help], index) => {
        const cases = bt[t] || [];
        return `<details class="case-group">
      <summary title="${esc(help)}"><span>${label} (${cases.length})</span></summary>
      <div class="case-group-body">${cases.length ? caseListHeader("feature") + cases.map(caseCard).join("") : `<div class="case-group-empty">No ${label.toLowerCase()} were generated from the current evidence.</div>`}</div>
    </details>`;
      })
      .join("");
    $("#d-cases").innerHTML = h;
    updateCaseSelection();
    loadCoverage(fid);
    window.scrollTo({ top: 0, behavior: "smooth" });
    renderBreadcrumbs();
    updateBackbar();
    attachRunningGenWatcher(fid); // show the live loader if generation is still running
  } catch (e) {
    $("#d-cases").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
};
async function openFeatureTestCases(fid, pid) {
  navigateTo("cases");
  // The Test Cases screen is React (src/features/test-cases, #257).
  if (window.openTestCasesFor)
    await window.openTestCasesFor(fid, pid || currentProject || "");
}
function activeCaseRoot() {
  if (!$("#view-features").hidden && !$("#detail-card").hidden)
    return $("#detail-card");
  if (!$("#view-cases").hidden) return $("#view-cases");
  return document;
}
function activeCaseCheckboxes() {
  return [...activeCaseRoot().querySelectorAll(".case-select[data-case-id]")];
}
function selectedCaseIds() {
  return activeCaseCheckboxes()
    .filter((x) => x.checked)
    .map((x) => x.dataset.caseId);
}
function setVisibleCaseSelection(checked) {
  activeCaseCheckboxes().forEach((x) => (x.checked = checked));
  updateCaseSelection();
}
function updateCaseSelection() {
  const root = activeCaseRoot();
  const boxes = activeCaseCheckboxes();
  const selected = boxes.filter((x) => x.checked);
  document
    .querySelectorAll(".case-bulk-toolbar")
    .forEach((bar) => bar.classList.remove("show"));
  const scope = root.id === "detail-card" ? "feature" : "cases";
  document.querySelectorAll(`[data-bulk-scope="${scope}"]`).forEach((bar) => {
    if (selected.length) bar.classList.add("show");
  });
  document
    .querySelectorAll(`[data-bulk-count="${scope}"]`)
    .forEach((x) => (x.textContent = `${selected.length} selected`));
  document
    .querySelectorAll(`[data-bulk-count="${scope}-floating"]`)
    .forEach((x) => (x.textContent = selected.length));
  root.querySelectorAll(".case-select-all").forEach((x) => {
    x.checked = boxes.length > 0 && selected.length === boxes.length;
    x.indeterminate = selected.length > 0 && selected.length < boxes.length;
  });
  document
    .querySelectorAll(`[data-bulk-scope="${scope}-floating"]`)
    .forEach((bar) => bar.classList.toggle("show", selected.length > 0));
}
document.addEventListener("change", (e) => {
  if (e.target.matches(".case-select-all"))
    setVisibleCaseSelection(e.target.checked);
  if (e.target.matches(".case-select[data-case-id]")) updateCaseSelection();
});
function selectedExportIds() {
  const rowIds = selectedCaseIds();
  if (rowIds.length) return rowIds;
  return [...document.querySelectorAll(".export-case-check")]
    .filter((x) => x.checked)
    .map((x) => x.value);
}
function refreshExportCount() {
  const n = selectedExportIds().length;
  $("#export-count").textContent = `${n} selected`;
  $("#export-pdf").disabled = !n;
  $("#export-csv").disabled = !n;
}
function openExportModal() {
  if (!currentFeature || !currentFeatureData) return;
  const cases = currentFeatureCases || [];
  $("#export-sub").textContent =
    `${currentFeatureData.name} · Version ${currentFeatureData.version || 1} · ${cases.length} test case${cases.length === 1 ? "" : "s"}`;
  $("#export-select-all").checked = true;
  $("#export-list").innerHTML =
    cases
      .map(
        (c) => `<label class="export-row">
    <input class="export-case-check" type="checkbox" value="${esc(c.id)}" checked/>
    <span class="badge">${esc(c.display_id || "")}</span>
    <span><span class="title">${esc(caseTitle(c))}</span><div class="meta">${esc(typeLabel(c.type))} · ${c.steps?.length || 0} step${(c.steps?.length || 0) === 1 ? "" : "s"}</div></span>
    <span class="meta">${prioBadge(c.priority)}</span>
  </label>`,
      )
      .join("") ||
    `<div class="muted" style="padding:14px">No test cases available.</div>`;
  document.querySelectorAll(".export-case-check").forEach(
    (x) =>
      (x.onchange = () => {
        const all = [...document.querySelectorAll(".export-case-check")];
        $("#export-select-all").checked =
          all.length && all.every((c) => c.checked);
        refreshExportCount();
      }),
  );
  refreshExportCount();
  $("#export-modal").classList.add("show");
}
async function downloadFeatureExport(format, explicitIds = null) {
  const ids = explicitIds === null ? selectedExportIds() : explicitIds;
  const featureId = !$("#view-cases").hidden
    ? $("#tc-feat")?.value
    : currentFeature;
  if (!featureId) {
    toast("Choose one feature before exporting selected test cases", true);
    return;
  }
  const ext = format === "pdf" ? "pdf" : "csv";
  const mime = format === "pdf" ? "application/pdf" : "text/csv";
  const request = ids.length
    ? {
        url: `/api/features/${featureId}/export/${format}-selected`,
        init: {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ testCaseIds: ids }),
        },
      }
    : {
        url: `/api/features/${featureId}/export/${format}`,
        init: { method: "GET" },
      };
  const res = await fetch(request.url, request.init);
  if (!res.ok) {
    let detail = "Export failed";
    try {
      detail = (await res.json()).detail || detail;
    } catch (e) {}
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(new Blob([blob], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(currentFeatureData?.name || "feature").replace(/[^a-z0-9]+/gi, "_").toLowerCase()}_test_cases.${ext}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
async function downloadGapExport(kind, fmt) {
  if (!currentFeature) {
    toast("Open a feature first", true);
    return;
  }
  const mime = fmt === "pdf" ? "application/pdf" : "text/csv";
  const res = await fetch(
    `/api/features/${currentFeature}/gap/${kind}/export/${fmt}`,
    { method: "GET" },
  );
  if (!res.ok) {
    let detail = "Export failed";
    try {
      detail = (await res.json()).detail || detail;
    } catch (e) {}
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(new Blob([blob], { type: mime }));
  const a = document.createElement("a");
  const base = (currentFeatureData?.name || "feature")
    .replace(/[^a-z0-9]+/gi, "_")
    .toLowerCase();
  const label = kind === "pr-coverage" ? "pr_coverage" : "automation_coverage";
  a.href = url;
  a.download = `${base}_${label}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
async function bulkExportSelected(format = "pdf") {
  const ids = selectedCaseIds();
  try {
    await downloadFeatureExport(format, ids);
    toast(
      ids.length
        ? "Selected test cases exported"
        : "All feature test cases exported",
    );
  } catch (e) {
    toast(e.message, true);
  }
}
async function bulkSetCaseResult(status) {
  const ids = selectedCaseIds();
  if (!ids.length) {
    toast("Select test cases first", true);
    return;
  }
  try {
    await Promise.all(
      ids.map((id) =>
        api(`/api/test-cases/${id}/execution`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        }),
      ),
    );
    ids.forEach((id) => {
      const item = document.querySelector(`[data-case-item="${id}"]`);
      const select = item?.querySelector(".result-select");
      if (select) {
        select.value = status;
        select.className = `result-select needs-editor ${status}`;
        [...select.options].forEach(
          (o) => (o.defaultSelected = o.value === status),
        );
      }
    });
    toast(
      `${ids.length} test case${ids.length === 1 ? "" : "s"} marked ${RESULT_LABELS[status].toLowerCase()}`,
    );
  } catch (e) {
    toast(e.message, true);
  }
}
async function bulkDeleteSelected() {
  const ids = selectedCaseIds();
  if (!ids.length) {
    toast("Select test cases first", true);
    return;
  }
  if (
    !(await uiConfirm(
      `Delete ${ids.length} selected test case${ids.length === 1 ? "" : "s"}? Shared test cases are only removed from the current feature when a feature is in context.`,
      "Delete Test Cases",
      "Delete",
      true,
    ))
  )
    return;
  const scopedFeature = !$("#view-cases").hidden
    ? $("#tc-feat")?.value || ""
    : currentFeature;
  try {
    for (const id of ids) {
      if (scopedFeature)
        await api(`/api/features/${scopedFeature}/test-cases/${id}`, {
          method: "DELETE",
        });
      else await api(`/api/test-cases/${id}`, { method: "DELETE" });
    }
    toast(
      `${ids.length} selected test case${ids.length === 1 ? "" : "s"} removed`,
    );
    if (!$("#view-cases").hidden) loadCases();
    if (currentFeature) openFeature(currentFeature);
  } catch (e) {
    toast(e.message, true);
  }
}
if ($("#export-close"))
  $("#export-close").onclick = () =>
    $("#export-modal").classList.remove("show");
if ($("#export-select-all"))
  $("#export-select-all").onchange = (e) => {
    document
      .querySelectorAll(".export-case-check")
      .forEach((x) => (x.checked = e.target.checked));
    refreshExportCount();
  };
if ($("#export-pdf"))
  $("#export-pdf").onclick = async () => {
    try {
      await downloadFeatureExport("pdf");
    } catch (e) {
      toast(e.message, true);
    }
  };
if ($("#export-csv"))
  $("#export-csv").onclick = async () => {
    try {
      await downloadFeatureExport("csv");
    } catch (e) {
      toast(e.message, true);
    }
  };
document.querySelectorAll(".feature-workspace-back").forEach((button) => {
  button.onclick = () => navigateTo("features");
});
document.querySelectorAll(".feature-workspace-cases").forEach((button) => {
  button.onclick = () => {
    if (currentFeature) openFeatureTestCases(currentFeature, currentProject);
  };
});
const TYPE_LABELS = {
  functional: "Business / functional",
  e2e: "End-to-end",
  api: "API",
  ui: "UI validation",
  nfr: "Edge & reliability",
  integration: "Integration",
};
const typeLabel = (t) => TYPE_LABELS[t] || t;
const caseTitle = (c) =>
  cleanRequirementText(c?.title || "Untitled test case") ||
  "Untitled test case";
function caseListHeader(scope) {
  return `<div class="case-list-head">
    <input type="checkbox" class="case-select case-select-all" data-bulk-scope="${scope}" title="Select all visible test cases" aria-label="Select all visible test cases" onclick="event.stopPropagation()"/>
    <span></span>
    <span>Test case</span>
    <span>Result</span>
    <span>Priority</span>
    <span>Action</span>
  </div>`;
}
function caseCard(c) {
  const orig = c.association && c.association.origin;
  const context = orig ? `${orig.replaceAll("_", " ")} · ` : "";
  const inherited = [
    "reused",
    "carried",
    "carried_repaired",
    "inherited",
    "adapted",
  ].includes(orig);
  const title = caseTitle(c);
  // "Imported from sheet" takes priority over the generic inherited badge, so a case
  // that came from an uploaded sheet is never mislabelled as inherited from a feature.
  // Fall back to the origin when the backend `imported` flag isn't present yet.
  const isImported = c.imported || orig === "imported";
  const originBadge = isImported
    ? `<span class="badge reused" style="margin-left:7px" title="Came from an uploaded sheet">Imported from sheet</span>`
    : inherited
      ? `<span class="badge reused" style="margin-left:7px">Inherited / reused</span>`
      : "";
  return `<div class="testcase-item" data-case-item="${c.id}">
    <div class="testcase-row" onclick="viewCase('${c.id}',this)">
      <input class="case-select" data-case-id="${esc(c.id)}" type="checkbox" aria-label="Select ${esc(title)}" onclick="event.stopPropagation()"/>
      <span class="testcase-chevron">›</span>
      <div><div class="testcase-title">${c.display_id ? `<span class="badge" style="margin-right:7px">${esc(c.display_id)}</span>` : ""}${esc(title)}${originBadge}</div><div class="testcase-sub">${esc(context + typeLabel(c.type))} · ${c.steps.length} step${c.steps.length === 1 ? "" : "s"}</div></div>
      ${resultSelect(c)}
      <span class="testcase-priority">${prioBadge(c.priority)}</span>
      <button class="testcase-delete needs-editor" title="Delete testcase" onclick="event.stopPropagation();requestDeleteCase('${c.id}')"><span>Delete</span></button>
    </div>
    <div class="testcase-detail" data-case-detail="${c.id}"></div>
  </div>`;
}
async function loadCoverage(fid) {
  $("#d-coverage").innerHTML = "";
  try {
    const r = await api(`/api/features/${fid}/coverage`);
    const s = r.summary;
    if (!s) return;
    const thr = s.ready_threshold != null ? s.ready_threshold : 80;
    const banner = s.ready
      ? `<div style="margin-top:10px;color:#34d399;font-weight:600;font-size:13px">✓ Minimum code-coverage target reached (${s.code_pct}% ≥ ${thr}%) — ready for manual QA.</div>`
      : `<div style="margin-top:10px;color:#f6a623;font-size:12.5px">Not ready for manual QA — code coverage ${s.code_pct}% is below the ${thr}% target for this feature.</div>`;
    const strategy = `<div style="margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px;color:var(--muted,#94a3b8)">
      <span>QA-readiness target:</span>
      <input id="fc-threshold" class="needs-editor" type="number" min="0" max="100" value="${thr}" style="width:64px" />
      <span>% code coverage</span>
      <button class="ghost needs-editor" type="button" onclick="saveReadyThreshold('${fid}')">Save</button>
      <span id="fc-threshold-status" class="muted"></span>
    </div>`;
    $("#d-coverage").innerHTML =
      `<div style="margin-top:14px;border:1px solid var(--line,#1e293b);border-radius:12px;padding:14px 16px;background:var(--panel,#0d1728)">
      <div style="font-size:13px;font-weight:600">Coverage <span style="font-weight:400;color:var(--muted,#94a3b8)">— aggregated across all PRs linked to this feature</span></div>
      <div style="font-size:12px;color:var(--muted,#94a3b8);margin:2px 0 10px">A test case counts as covered once ANY linked PR implements it (no single repo need cover everything).</div>
      <div class="dash-gauge"><div class="top"><span>Code coverage (cases implemented by PRs)</span><b>${s.code_pct}%</b></div><div class="track"><div class="fill code" style="width:${s.code_pct}%"></div></div></div>
      <div class="dash-gauge"><div class="top"><span>Automation Test Coverage (dev-written tests)</span><b>${s.automation_pct}%</b></div><div class="track"><div class="fill auto" style="width:${s.automation_pct}%"></div></div></div>
      <div class="dash-cov-note">${s.covered_cases} covered${s.partial_cases ? ` · ${s.partial_cases} partial (not counted)` : ""} · ${s.automated_cases} automated of ${s.total_cases} cases</div>
      ${banner}
      ${strategy}
    </div>`;
  } catch (e) {
    /* non-fatal: coverage card just stays empty */
  }
}
window.saveReadyThreshold = async (fid) => {
  const el = $("#fc-threshold");
  const v = parseInt((el && el.value) || "80", 10);
  try {
    const r = await api(`/api/features/${fid}/ready-threshold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold: isNaN(v) ? 80 : v }),
    });
    toast(`QA-readiness target set to ${r.ready_threshold}% code coverage`);
    loadCoverage(fid);
  } catch (e) {
    if ($("#fc-threshold-status"))
      $("#fc-threshold-status").textContent = e.message || "failed";
    toast(e.message || "Could not save target", true);
  }
};
$("#d-close").onclick = () => showFeatureList();

// Post a feature's coverage to its Jira issue (#d-jira; moved here from 09 when
// the Mind Map moved to React, #257).
window.syncJira = async (fid) => {
  try {
    const r = await api(`/api/features/${fid}/jira-sync`, { method: "POST" });
    toast("Posted coverage to Jira " + r.issue);
  } catch (e) {
    toast(e.message, true);
  }
};

// Project list → Features screen glue (moved from 02-projects.js when the
// Projects screen moved to React, #257).
window.openProjectFeatures = async (pid) => {
  currentProject = pid;
  currentFeature = null;
  navigateTo("features");
  await loadFeatures();
  showFeatureList();
};
