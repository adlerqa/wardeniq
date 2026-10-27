// ---- test cycles + code analysis ----
// Lookback (days) bounds — kept in sync with the declared min/max on
// #cyc-days (CodeAnalysisPage.jsx) and with AnalyzeIn's server-side
// Field(ge=1, le=180) constraint. A bare type="button" click handler with no
// wrapping <form> never triggers native reportValidity()/checkValidity(), so
// the input's min/max attributes are cosmetic on their own — the button's
// disabled state has to be driven explicitly from the current value.
const CYC_DAYS_MIN = 1;
const CYC_DAYS_MAX = 180;
let _cycAnalyzeRunning = false;

function _cycDaysInRange() {
  const n = parseInt($("#cyc-days") ? $("#cyc-days").value : "", 10);
  return Number.isFinite(n) && n >= CYC_DAYS_MIN && n <= CYC_DAYS_MAX;
}
function _syncAnalyzeButtonState() {
  const btn = $("#cyc-analyze");
  if (!btn) return;
  const inRange = _cycDaysInRange();
  btn.disabled = _cycAnalyzeRunning || !inRange;
  // Explain *why* it's disabled via the native hover tooltip rather than an
  // always-on inline line next to the Lookback field — a persistent line
  // there broke the controls row's alignment. The title attribute still
  // works while the button is disabled (hover, not click, drives it).
  btn.title = !inRange
    ? `Lookback must be between ${CYC_DAYS_MIN} and ${CYC_DAYS_MAX} days`
    : _cycAnalyzeRunning
      ? "Analysis in progress…"
      : "";
}
if ($("#cyc-days")) $("#cyc-days").oninput = _syncAnalyzeButtonState;
_syncAnalyzeButtonState();

async function initCycles() {
  await loadProjects();
  await loadCycleRepos();
  loadUnmappedPRs();
  loadLatestAnalysis();
  _syncAnalyzeButtonState();
}
$("#cyc-proj").onchange = () => {
  currentProject = $("#cyc-proj").value;
  loadCycleRepos();
  loadUnmappedPRs();
  loadLatestAnalysis();
};
if ($("#cyc-refresh"))
  $("#cyc-refresh").onclick = () => {
    loadCycleRepos();
    loadUnmappedPRs();
    loadLatestAnalysis();
  };
// ---- Test Cycles view (independent of change-impact analysis) ----
async function initTestCycles() {
  await loadProjects();
  if ($("#tcy-proj")) $("#tcy-proj").value = currentProject;
  loadCycles();
  loadCycleTemplates();
}
if ($("#tcy-proj"))
  $("#tcy-proj").onchange = () => {
    currentProject = $("#tcy-proj").value;
    loadCycles();
    loadCycleTemplates();
  };
if ($("#tcy-refresh"))
  $("#tcy-refresh").onclick = () => {
    loadCycles();
    loadCycleTemplates();
  };
async function createEmptyCycle() {
  const pid = ($("#tcy-proj") && $("#tcy-proj").value) || currentProject;
  if (!pid) {
    toast("Select a project first", true);
    return;
  }
  // Previously silently fell back to `Cycle ${date}` when this field was left
  // blank, so a cycle always got created even with no real name -- and a
  // second blank click on the same day collided on that identical fallback,
  // surfacing a confusing "already exists" error instead of the real problem
  // (no name was given). Require a name up front instead.
  const name = ($("#tcy-name") && $("#tcy-name").value.trim()) || "";
  if (!name) {
    toast("Enter a cycle name", true);
    return;
  }
  try {
    const r = await api("/api/test-cycles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: pid, name, case_ids: [] }),
    });
    if ($("#tcy-name")) $("#tcy-name").value = "";
    toast("Cycle created — add the test cases you want to retest");
    loadCycles();
    if (r && r.id) openCycle(r.id);
  } catch (e) {
    toast(e.message || "Could not create cycle", true);
  }
}
window.createEmptyCycle = createEmptyCycle;
if ($("#tcy-new")) $("#tcy-new").onclick = createEmptyCycle;
async function loadCycleRepos() {
  const pid = $("#cyc-proj").value || currentProject;
  if (!pid) return;
  try {
    const r = await api(`/api/projects/${pid}/repos?repo_type=app`); // app repos only (test repos excluded)
    $("#cyc-repos").innerHTML = repoBranchRows(r.repos, "cyc-repo");
    fillBranchDropdowns("cyc-repo", r.repos);
    if ($("#pr-repo"))
      $("#pr-repo").innerHTML = r.repos
        .map((rp) => `<option value="${rp.id}">${esc(rp.full_name)}</option>`)
        .join("");
  } catch (e) {}
}
async function loadUnmappedPRs() {
  const pid = $("#cyc-proj").value || currentProject;
  if (!pid || !$("#unmapped-prs")) return;
  try {
    const [u, f] = await Promise.all([
      api(`/api/projects/${pid}/unmapped-prs`),
      api(`/api/features?project_id=${pid}`),
    ]);
    const feats = f.features || f.items || [];
    if (!u.prs.length) {
      $("#unmapped-prs").innerHTML =
        `<span class="muted">no unmapped PRs 🎉</span>`;
      return;
    }
    const opts = feats
      .map((ft) => `<option value="${ft.id}">${esc(ft.name)}</option>`)
      .join("");
    $("#unmapped-prs").innerHTML = u.prs
      .map(
        (
          p,
        ) => `<div class="stepitem" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer"><b>#${p.number}</b></a> ${esc(p.title || "")} <span class="muted">· ${esc(p.repo || "")}</span>
      <select class="asg-feat" data-pr="${p.id}" style="width:auto;flex:0 0 220px">${opts}</select>
      <button class="go asg-btn" data-pr="${p.id}" style="flex:0 0 auto;padding:5px 12px">Assign & cover</button></div>`,
      )
      .join("");
    document.querySelectorAll(".asg-btn").forEach(
      (b) =>
        (b.onclick = async () => {
          const pr = b.dataset.pr;
          const sel = document.querySelector(`.asg-feat[data-pr="${pr}"]`);
          const fid = sel && sel.value;
          if (!fid) {
            toast("Pick a feature", true);
            return;
          }
          b.disabled = true;
          b.textContent = "Assigning…";
          try {
            await api(`/api/prs/${pr}/assign`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ feature_id: fid }),
            });
            toast(
              "Assigned ✓ — coverage is computing in the background (check the feature's coverage shortly)",
            );
            loadUnmappedPRs();
          } catch (e) {
            toast("Assign failed: " + e.message, true);
            b.disabled = false;
            b.textContent = "Assign & cover";
          }
        }),
    );
  } catch (e) {
    $("#unmapped-prs").innerHTML =
      `<span class="muted">${esc(e.message)}</span>`;
  }
}
$("#cyc-analyze").onclick = async () => {
  // Defensive re-check: the click handler is the last line of defense even
  // though the button is kept disabled while out of range (belt-and-
  // suspenders against a stale/race-y disabled state or a programmatic
  // click) — analysis must never launch outside the declared bounds.
  if (!_cycDaysInRange()) {
    toast(`Lookback must be between ${CYC_DAYS_MIN} and ${CYC_DAYS_MAX} days`, true);
    _syncAnalyzeButtonState();
    return;
  }
  const ids = [...document.querySelectorAll(".cyc-repo-chk")]
    .filter((c) => c.checked)
    .map((c) => c.value);
  if (!ids.length) {
    toast("Select at least one repo", true);
    return;
  }
  const days = parseInt($("#cyc-days").value) || 14;
  const pid = $("#cyc-proj").value || currentProject;
  const branches = collectBranches("cyc-repo");
  $("#cyc-impacted").innerHTML = "";
  $("#cyc-create").style.display = "none";
  $("#cyc-status").textContent =
    `Starting change impact review for ${ids.length} repo${ids.length === 1 ? "" : "s"}…`;
  _cycAnalyzeRunning = true;
  _syncAnalyzeButtonState();
  try {
    const r = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: pid, repo_ids: ids, branches, days }),
    });
    watchAnalyze(r.job_id);
  } catch (e) {
    $("#cyc-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
    _cycAnalyzeRunning = false;
    _syncAnalyzeButtonState();
  }
};

function formatCycleStage(stage) {
  const s = (stage || "").toLowerCase();
  if (!s) return "Preparing change impact review…";
  if (
    s.startsWith("fetching github commits") ||
    s.startsWith("fetching gitlab commits")
  )
    return "Reading recent commits from the selected repositories…";
  if (s.startsWith("grounded matching"))
    return "Matching changed code to impacted test cases…";
  if (s.startsWith("llm impact analysis"))
    return "Reviewing the remaining cases for likely impact…";
  return stage;
}

function cycleImpactStatusBadge(status) {
  const s = (status || "").toLowerCase();
  if (s === "matched" || s === "covered")
    return `<span class="badge mm-covered">Direct match</span>`;
  if (s === "review_needed" || s === "partial")
    return `<span class="badge mm-partial">Needs review</span>`;
  return `<span class="badge mm-uncovered">Unverified</span>`;
}

function cycleImpactConfidenceBadges(confidence, tier, signalType) {
  const badges = [];
  if (confidence != null)
    badges.push(
      `<span class="badge">${Math.round(confidence * 100)}% confidence</span>`,
    );
  if (tier) badges.push(`<span class="badge">Tier ${tier}</span>`);
  if (signalType === "ai")
    badges.push(`<span class="pill">Model reviewed</span>`);
  return badges.join("");
}

function cycleImpactTypeBadge(type) {
  const normalized = type || "functional";
  return `<span class="badge ${esc(normalized)}">${esc(typeLabel(normalized))}</span>`;
}

function cycleImpactRiskBadge(risk) {
  const s = (risk || "medium").toString().trim().toLowerCase();
  const k = ["high", "critical", "p1"].includes(s)
    ? "high"
    : ["low", "p3"].includes(s)
      ? "low"
      : "medium";
  const C = {
    high: ["rgba(239,68,68,0.25)", "rgba(239,68,68,0.12)", "#fca5a5"],
    medium: ["rgba(59,130,246,0.25)", "rgba(59,130,246,0.12)", "#93c5fd"],
    low: ["rgba(34,197,94,0.25)", "rgba(34,197,94,0.12)", "#86efac"],
  }[k];
  const label = { high: "High", medium: "Medium", low: "Low" }[k];
  return `<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;border:1px solid ${C[0]};background:${C[1]};color:${C[2]}">${label} risk</span>`;
}

function cycleImpactNarrative(c) {
  if (c.signal_type === "endpoint")
    return c.signal
      ? `A changed API endpoint directly maps to this testcase, so it should be part of the next regression pass.`
      : `A changed API endpoint directly maps to this testcase.`;
  if (c.signal_type === "symbol")
    return c.signal
      ? `A changed implementation signal overlaps with this testcase closely enough to treat it as directly impacted.`
      : `A changed implementation signal overlaps with this testcase closely enough to treat it as directly impacted.`;
  if (c.signal_type === "ai")
    return c.reason
      ? c.reason
      : `The broader change set looks related to this testcase, so it is included for a quick manual review.`;
  return (
    c.reason ||
    "This testcase appears related to the recent implementation changes."
  );
}

function cycleImpactSignalRow(c) {
  if (!c.signal) return "";
  const label =
    c.signal_type === "endpoint"
      ? "Matched endpoint"
      : c.signal_type === "symbol"
        ? "Matched code signal"
        : "Reference";
  return `<div class="cycle-impact-signal"><span class="pill">${label}</span><code>${esc(c.signal)}</code></div>`;
}

function cycleImpactEvidence(ev) {
  if (!(ev || []).length) {
    return `<div class="cycle-impact-empty">No direct code evidence was saved for this item. It was surfaced from the broader impact review.</div>`;
  }
  return `<div class="cycle-impact-evidence">
    <div class="cycle-impact-evidence-label">Code evidence</div>
    ${(ev || [])
      .map((e) => {
        const fileLine = `${esc(e.file || "")}${e.line ? `:${e.line}` : ""}`;
        const commit = (e.sha || "").slice(0, 7);
        const row = `<span class="cycle-impact-evidence-file">${fileLine}</span><span class="cycle-impact-evidence-meta">${commit ? `<span class="pill">${esc(commit)}</span>` : ""}${e.repo ? `<span class="badge">${esc(e.repo)}</span>` : ""}</span>`;
        return e.url
          ? `<a class="cycle-impact-evidence-row" href="${e.url}" target="_blank" rel="noopener">${row}</a>`
          : `<div class="cycle-impact-evidence-row">${row}</div>`;
      })
      .join("")}
  </div>`;
}

function watchAnalyze(jobId) {
  if (!jobId) return;
  watchJob(jobId, (j) => {
    const a = j.result || {};
    $("#cyc-status").innerHTML =
      j.status === "running"
        ? `⏳ ${esc(formatCycleStage(j.stage))}${a.commit_count ? ` (${a.commit_count} commits, ${(a.changed_files || []).length} files)` : ""}`
        : j.status === "failed"
          ? `<span class="err">Analysis failed: ${esc(j.error || "")}</span>`
          : `Review complete · ${a.commit_count || 0} commits · ${(a.changed_files || []).length} files changed${a.note ? ` · ${esc(a.note)}` : ""}`;
    if (j.status === "running") return;
    _cycAnalyzeRunning = false;
    _syncAnalyzeButtonState();
    renderImpacted(a);
  });
}
function renderImpacted(a) {
  ANALYSIS_IMPACTED = a.impacted || [];
  if (!ANALYSIS_IMPACTED.length) {
    $("#cyc-impacted").innerHTML =
      `<div class="mindmap-summary-card"><div class="mindmap-summary-head"><h2>No impacted test cases</h2><div class="mindmap-chip-row"><span class="badge">0 impacted</span></div></div><div class="sub">No recent changes in the selected repositories mapped to the current test suite for this lookback window.</div></div>`;
    $("#cyc-create").style.display = "none";
    return;
  }
  const grounded = a.grounded || 0,
    ai = a.ai || 0,
    commits = a.commits || [];
  const summary = `<div class="mindmap-summary-card"><div class="mindmap-summary-head"><h2>Impact review</h2><div class="mindmap-chip-row"><span class="badge mm-covered">${grounded} direct evidence</span><span class="badge mm-partial">${ai} needs review</span><span class="badge">${ANALYSIS_IMPACTED.length} impacted cases</span></div></div><div class="sub">These testcases are the strongest candidates for regression based on the selected code changes. Open any row to inspect the matching signal and exact evidence.</div></div>`;
  const items =
    `<div class="cycles-select-bar" style="align-items:center;gap:12px;flex-wrap:wrap">
    <label class="case-select-label" style="margin:0"><input type="checkbox" id="imp-select-all" onchange="toggleImpactSelection(this.checked)" style="width:auto"/> Select all impacted cases</label>
    <span class="cycles-select-count" id="imp-selected-count">0 selected</span>
    <button class="go" id="imp-create-top" style="margin-left:auto;padding:6px 14px" onclick="createCycleFromSelection()">Create cycle from selected</button>
  </div>` +
    ANALYSIS_IMPACTED.map((c, i) => {
      const evidenceCount = (c.evidence || []).length;
      const sourceLabel =
        c.signal_type === "ai"
          ? "Model-reviewed suggestion"
          : "Direct code evidence";
      return `<details class="cycle-impact-item">
      <summary>
        <span class="cycle-impact-check" onclick="event.preventDefault();event.stopPropagation()"><input type="checkbox" class="imp-chk" data-i="${i}" onchange="updateImpactSelectionUI()" onclick="event.stopPropagation()" style="width:auto"/></span>
        <span class="cycle-impact-toggle" aria-hidden="true"></span>
        <div class="cycle-impact-main">
          <div class="cycle-impact-title">${c.display_id ? `<code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px;color:#94a3b8;margin-right:6px">${esc(c.display_id)}</code>` : ""}${esc(c.title)}</div>
          <div class="cycle-impact-sub"><span>${esc(typeLabel(c.type))}</span><span>·</span><span>${esc(sourceLabel)}</span><span>·</span><span>${evidenceCount} evidence point${evidenceCount === 1 ? "" : "s"}</span></div>
        </div>
        <div class="cycle-impact-badges">${cycleImpactStatusBadge(c.status)}${cycleImpactTypeBadge(c.type)}${cycleImpactRiskBadge(c.risk)}</div>
      </summary>
      <div class="cycle-impact-body">
        <div class="cycle-impact-summary">${esc(cycleImpactNarrative(c))}</div>
        ${stepsHtml(c.steps)}
        ${cycleImpactSignalRow(c)}
        ${cycleImpactEvidence(c.evidence)}
      </div>
    </details>`;
    }).join("");
  let html =
    summary +
    `<div class="mindmap-feature-card"><div class="mindmap-feature-head"><div><div class="mindmap-feature-title"><strong>Impacted test cases</strong></div><div class="mindmap-feature-meta">Select the cases you want to carry into a release regression cycle.</div></div><div class="mindmap-chip-row"><span class="pill">${ANALYSIS_IMPACTED.length} case${ANALYSIS_IMPACTED.length === 1 ? "" : "s"}</span></div></div><div class="mindmap-case-list">${items}</div></div>`;
  if (commits.length) {
    html +=
      `<div class="card mindmap-diagnostics cycles-commit-list"><details><summary>${commits.length} commits reviewed as evidence</summary><div class="sub">` +
      commits
        .map(
          (cm) =>
            `<div class="stepitem">${cm.repo ? `<span class="pill">${esc(cm.repo)}</span> ` : ""}<a href="${esc(cm.url)}" target="_blank" rel="noopener noreferrer">${esc(cm.sha)}</a> <span class="muted">${esc(cm.message)}</span></div>`,
        )
        .join("") +
      `</div></details></div>`;
  }
  $("#cyc-impacted").innerHTML = html;
  $("#cyc-create").style.display = "";
  updateImpactSelectionUI();
}
window.toggleImpactSelection = (checked) => {
  document.querySelectorAll(".imp-chk").forEach((c) => {
    c.checked = !!checked;
  });
  updateImpactSelectionUI();
};
window.updateImpactSelectionUI = () => {
  const boxes = [...document.querySelectorAll(".imp-chk")];
  const selected = boxes.filter((c) => c.checked).length;
  const all = boxes.length > 0 && selected === boxes.length;
  if ($("#imp-select-all")) $("#imp-select-all").checked = all;
  if ($("#imp-selected-count"))
    $("#imp-selected-count").textContent = `${selected} selected`;
  if ($("#cyc-make")) {
    $("#cyc-make").disabled = selected === 0;
    $("#cyc-make").textContent =
      selected > 0 ? `Create cycle (${selected})` : "Create cycle";
  }
};
function clearImpacted(msg) {
  ANALYSIS_IMPACTED = [];
  if ($("#cyc-impacted")) $("#cyc-impacted").innerHTML = "";
  if ($("#cyc-status"))
    $("#cyc-status").innerHTML = msg ? `<span class="muted">${msg}</span>` : "";
  if ($("#cyc-create")) $("#cyc-create").style.display = "none";
}
async function loadLatestAnalysis() {
  const pid = $("#cyc-proj").value || currentProject;
  if (!pid || !$("#cyc-impacted")) return;
  clearImpacted(""); // reset so a project with no saved analysis doesn't show the previous one
  try {
    const run = await api(`/api/projects/${pid}/commit-analysis/latest`);
    const results = run.results || [];
    if (!results.length) {
      clearImpacted(
        "No saved impact analysis for this project yet — click Analyze changes.",
      );
      return;
    }
    const grounded = results.filter(
      (r) => r.signal_type && r.signal_type !== "ai",
    ).length;
    const ai = results.filter((r) => r.signal_type === "ai").length;
    $("#cyc-status").innerHTML =
      `<span class="muted">↻ Restored the latest saved impact review · ${results.length} impacted case(s)</span>`;
    renderImpacted({
      impacted: results,
      grounded,
      ai,
      commits: run.commits || [],
    });
  } catch (e) {
    clearImpacted("");
  }
}
async function createCycleFromSelection() {
  const ids = [...document.querySelectorAll(".imp-chk")]
    .filter((c) => c.checked)
    .map((c) => ANALYSIS_IMPACTED[+c.dataset.i].case_id);
  if (!ids.length) {
    toast("Select at least one case", true);
    return;
  }
  // Same "name is required" guard as createEmptyCycle() above -- this flow
  // had its own separate `Cycle ${date}` fallback for a blank name.
  const name = ($("#cyc-name") && $("#cyc-name").value.trim()) || "";
  if (!name) {
    toast("Enter a cycle name", true);
    return;
  }
  const pid = $("#cyc-proj").value || currentProject;
  const repoIds = [...document.querySelectorAll(".cyc-repo-chk")]
    .filter((c) => c.checked)
    .map((c) => c.value);
  try {
    await api("/api/test-cycles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: pid,
        name,
        case_ids: ids,
        source: {
          repo_ids: repoIds,
          days: parseInt($("#cyc-days").value) || 14,
        },
      }),
    });
    if ($("#cyc-name")) $("#cyc-name").value = "";
    toast(
      `Cycle created with ${ids.length} case(s) — see it under Test Cycles`,
    );
    loadCycles();
  } catch (e) {
    toast(e.message, true);
  }
}
window.createCycleFromSelection = createCycleFromSelection;
if ($("#cyc-make")) $("#cyc-make").onclick = createCycleFromSelection;
async function loadCycleTemplates() {
  const pid = ($("#tcy-proj") && $("#tcy-proj").value) || currentProject;
  if (!pid || !$("#cyc-templates")) return;
  try {
    const r = await api(`/api/projects/${pid}/cycle-templates`);
    $("#cyc-templates").innerHTML =
      (r.templates || [])
        .map(
          (
            t,
          ) => `<div class="feat" style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <div><div class="n">${esc(t.name)}</div><div class="m">${t.case_count} case(s)${t.description ? ` · ${esc(t.description)}` : ""}</div></div>
      <div style="display:flex;gap:6px"><button class="go" style="padding:5px 12px" onclick="newCycleFromTemplate('${t.id}')">New cycle</button><button class="danger" style="padding:5px 12px" onclick="deleteCycleTemplate('${t.id}')">Delete</button></div>
    </div>`,
        )
        .join("") ||
      `<span class="muted">no templates yet — open a cycle and click “Save as template”</span>`;
  } catch (e) {}
}
window.saveCycleAsTemplate = async (cid) => {
  const name = await uiPrompt(
    "Save cycle as template",
    "Template name",
    (window.CYCLE_DETAIL_DATA || {}).name || "",
  );
  if (name == null) return;
  const n = name.trim();
  if (!n) {
    toast("Name required", true);
    return;
  }
  try {
    await api(`/api/test-cycles/${cid}/save-template`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: n }),
    });
    toast("Template saved");
    loadCycleTemplates();
  } catch (e) {
    toast(e.message, true);
  }
};
window.newCycleFromTemplate = async (tid) => {
  const name = await uiPrompt(
    "New cycle from template",
    "Cycle name",
    `Cycle ${new Date().toLocaleDateString()}`,
  );
  if (name == null) return;
  const n = name.trim();
  if (!n) {
    toast("Name required", true);
    return;
  }
  try {
    const r = await api(`/api/cycle-templates/${tid}/create-cycle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: n }),
    });
    toast("Cycle created from template");
    loadCycles();
    if (r && r.id) openCycle(r.id);
  } catch (e) {
    toast(e.message, true);
  }
};
window.deleteCycleTemplate = async (tid) => {
  if (
    !(await uiConfirm(
      "Delete this template? Existing cycles are not affected.",
      "Delete template",
      "Delete",
      true,
    ))
  )
    return;
  try {
    await api(`/api/cycle-templates/${tid}`, { method: "DELETE" });
    toast("Template deleted");
    loadCycleTemplates();
  } catch (e) {
    toast(e.message, true);
  }
};
async function loadCycles() {
  const pid = ($("#tcy-proj") && $("#tcy-proj").value) || currentProject;
  if (!pid) return;
  skIn("#cyc-list", skeleton.rows(5, "Loading test cycles"));
  try {
    const r = await api(`/api/projects/${pid}/test-cycles`);
    $("#cyc-list").innerHTML =
      r.cycles
        .map((c) => {
          const cc = c.counts || {};
          const done =
              (cc.passed || 0) +
              (cc.failed || 0) +
              (cc.skipped || 0) +
              (cc.blocked || 0),
            pct = c.total ? Math.round((done / c.total) * 100) : 0;
          return `<div class="feat" onclick="openCycle('${c.id}')"><div class="n">${esc(c.name)} <span class="badge">${esc(c.status || "draft")}</span></div>
        <div class="progress" style="margin:7px 0 4px"><div class="pbar" style="width:${pct}%"></div></div>
        <div class="m">${done}/${c.total} executed · ${cc.passed || 0} passed · ${cc.failed || 0} failed · ${cc.skipped || 0} skipped · ${cc.blocked || 0} blocked · ${esc(c.environment || "environment not set")}</div></div>`;
        })
        .join("") || `<span class="muted">no cycles yet</span>`;
  } catch (e) {
    if ($("#cyc-list"))
      $("#cyc-list").innerHTML =
        `<div class="err">Couldn't load test cycles. ${esc(e.message)}</div>`;
  }
}
window.CYCLE_DETAIL_DATA = null;
window.CYCLE_EDIT_ITEM = null;
window.CYCLE_EDIT_DRAFT = null;
const cycleStatusOptions = (st) =>
  ["pending", "passed", "failed", "skipped", "blocked"]
    .map((s) => `<option ${s === st ? "selected" : ""}>${s}</option>`)
    .join("");
const cycleStatusPill = (st) =>
  `<span class="cycle-status-pill ${esc(st || "pending")}">${esc(st || "pending")}</span>`;
function cycleNeedsInlineEditor(item, itemId) {
  return (
    window.CYCLE_EDIT_ITEM === itemId ||
    ((item.execution_status === "failed" ||
      item.execution_status === "blocked") &&
      !!(item.actual_result || item.notes || item.defect_link))
  );
}
function renderCycleDetail(c) {
  window.CYCLE_DETAIL_DATA = c;
  $("#cyc-detail-card").style.display = "block";
  $("#cyc-d-name").innerHTML =
    `${esc(c.name)} <span class="badge">${esc(c.status || "draft")}</span>`;
  const cc = c.counts || {},
    done =
      (cc.passed || 0) +
      (cc.failed || 0) +
      (cc.skipped || 0) +
      (cc.blocked || 0),
    pct = c.total ? Math.round((done / c.total) * 100) : 0;
  const cycToday = new Date().toISOString().slice(0, 10);
  const cycStart = c.scheduled_start_at
    ? String(c.scheduled_start_at).slice(0, 10)
    : "";
  const cycEnd = c.scheduled_end_at
    ? String(c.scheduled_end_at).slice(0, 10)
    : "";
  const items = (c.items || [])
    .map((it) => {
      const itemId = it.id;
      const editing = window.CYCLE_EDIT_ITEM === itemId;
      const draft = editing ? window.CYCLE_EDIT_DRAFT || {} : {};
      const status = editing
        ? draft.status || it.execution_status || "pending"
        : it.execution_status || "pending";
      const actual = editing
        ? (draft.actual_result ?? it.actual_result ?? "")
        : it.actual_result || "";
      const notes = editing ? (draft.notes ?? it.notes ?? "") : it.notes || "";
      const defect = editing
        ? (draft.defect_link ?? it.defect_link ?? "")
        : it.defect_link || "";
      const showEditor = editing || cycleNeedsInlineEditor(it, itemId);
      const noteSummary =
        !showEditor && (actual || notes || defect)
          ? `<div class="cycle-exec-notes"><div>${esc(actual || notes)}</div>${defect ? `<div style="margin-top:4px"><a href="${esc(defect)}" target="_blank" rel="noopener">Open defect link</a></div>` : ""}</div>`
          : "";
      const steps = stepsHtml(it.steps);
      const editor = showEditor
        ? `<div class="cycle-exec-editor">
      <div class="cycle-exec-editor-grid">
        <div class="full"><label>Execution result</label><textarea oninput="updateCycleDraftField('actual_result',this.value)">${esc(actual)}</textarea></div>
        <div class="full"><label>Notes</label><textarea oninput="updateCycleDraftField('notes',this.value)">${esc(notes)}</textarea></div>
        <div class="full"><label>Defect link</label><input value="${esc(defect)}" placeholder="https://…" oninput="updateCycleDraftField('defect_link',this.value)"/></div>
      </div>
      <div class="cycle-exec-actions"><button class="ghost" onclick="cancelCycleItemEdit()">Cancel</button><button class="go" onclick="saveCycleItemStatus('${c.id}','${itemId}')">Save status</button></div>
    </div>`
        : "";
      return `<div class="cycle-exec-item status-${esc(status)}">
      <div class="cycle-exec-head">
        <div class="cycle-exec-order">${it.display_order || ""}</div>
        <div>
          <div class="cycle-exec-title">${it.display_id ? `<code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px;color:#94a3b8;margin-right:6px">${esc(it.display_id)}</code>` : ""}${esc(it.title)}</div>
          <div class="cycle-exec-sub"><span class="badge ${esc(it.category)}">${esc(it.category || "")}</span>${it.priority ? prioBadge(it.priority) : ""}${cycleStatusPill(status)}${it.case_id ? `<button class="ghost" style="padding:1px 9px;font-size:10.5px" onclick="event.stopPropagation();editCase('${it.case_id}')">Edit case</button>` : ""}</div>
          ${steps}
        </div>
        <div class="cycle-exec-priority muted">${it.priority ? prioLabel(it.priority) : ""}</div>
        <div class="cycle-exec-status"><select onchange="startCycleItemStatusEdit('${c.id}','${itemId}',this.value)" style="width:100%">${cycleStatusOptions(status)}</select></div>
      </div>
      ${noteSummary}
      ${editor}
    </div>`;
    })
    .join("");
  $("#cyc-d-items").innerHTML =
    `<div class="muted" style="margin:8px 0">${esc(c.description || "")} ${c.environment ? `· env <b>${esc(c.environment)}</b>` : ""} ${c.build_version ? `· build <b>${esc(c.build_version)}</b>` : ""}</div>
    <div class="progress"><div class="pbar" style="width:${pct}%"></div></div>
    <div class="cycle-detail-summary">
      <div class="cycle-detail-kpi"><b>${c.total || 0}</b><span>Total cases</span></div>
      <div class="cycle-detail-kpi"><b>${cc.passed || 0}</b><span>Passed</span></div>
      <div class="cycle-detail-kpi"><b>${cc.failed || 0}</b><span>Failed</span></div>
      <div class="cycle-detail-kpi"><b>${cc.blocked || 0}</b><span>Blocked</span></div>
      <div class="cycle-detail-kpi"><b>${pct}%</b><span>Progress</span></div>
    </div>
    <div class="cycle-detail-actions"><a class="export-btn" href="/api/test-cycles/${c.id}/export/csv">Export CSV</a><a class="export-btn" href="/api/test-cycles/${c.id}/export/pdf">Export PDF</a><button class="ghost" onclick="showCycleReport('${c.id}')">View summary</button><button class="ghost" onclick="editCycleDescription('${c.id}')">Edit description</button><button class="ghost" onclick="saveCycleAsTemplate('${c.id}')">Save as template</button></div>
    <div class="cycle-detail-actions" style="margin-top:10px;align-items:center;flex-wrap:wrap;gap:12px">
      <label class="muted" style="font-size:12px;display:flex;align-items:center;gap:6px">Start <input type="date" id="cyc-start" value="${cycStart}" min="${cycToday}" onchange="scheduleCycle('${c.id}','scheduled_start_at',this.value)" style="width:auto;padding:4px 8px"/></label>
      <label class="muted" style="font-size:12px;display:flex;align-items:center;gap:6px">End <input type="date" id="cyc-end" value="${cycEnd}" min="${cycStart || cycToday}" onchange="scheduleCycle('${c.id}','scheduled_end_at',this.value)" style="width:auto;padding:4px 8px"/></label>
      ${cycleDateStatus(cycStart, cycEnd)}
      <button class="go" style="padding:5px 12px;margin-left:auto" onclick="openAddCaseChooser('${c.id}')">+ Add test cases</button>
    </div>
    <div class="cycle-exec-list">${items}</div>`;
  $("#cyc-detail-card").scrollIntoView({ behavior: "smooth" });
}
window.openCycle = async (id) => {
  try {
    const c = await api("/api/test-cycles/" + id);
    window._cycle = id;
    window.CYCLE_EDIT_ITEM = null;
    window.CYCLE_EDIT_DRAFT = null;
    renderCycleDetail(c);
  } catch (e) {
    toast(e.message, true);
  }
};
window.openCreateCaseInCycle = async (cid) => {
  const pid = (window.CYCLE_DETAIL_DATA || {}).project_id || currentProject;
  let feats = [];
  try {
    const r = await api(`/api/features?project_id=${encodeURIComponent(pid)}`);
    feats = r.features || [];
  } catch (e) {
    toast(e.message, true);
    return;
  }
  if (!feats.length) {
    toast(
      "Create a feature first — every test case must belong to a feature",
      true,
    );
    return;
  }
  const proceed = (fid) => {
    editing = {
      id: null,
      feature_id: fid,
      cycle_id: cid,
      shared_with_features: 0,
      steps: [{ action: "", expected: "" }],
    };
    $("#m-heading").textContent = "Create test case (adds to this cycle)";
    $("#m-title").value = "";
    $("#m-type").value = "functional";
    $("#m-prio").value = "Medium";
    $("#m-pre").value = "";
    $("#m-tags").value = "from-test-cycle";
    $("#m-warn").textContent =
      "Gets a new project ID, is linked to the selected feature, tagged “from-test-cycle”, and added to this cycle.";
    $("#m-del").style.display = "none";
    renderSteps();
    $("#m-msg").textContent = "";
    $("#modal").classList.add("show");
  };
  if (feats.length === 1) {
    proceed(feats[0].id);
    return;
  }
  const ov = document.createElement("div");
  ov.style.cssText =
    "position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML = `<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:460px;width:90%;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:6px">New test case → which feature?</div>
    <div class="muted" style="font-size:12px;margin-bottom:10px">Every test case belongs to a feature. It'll also be added to this cycle and tagged <code>from-test-cycle</code>.</div>
    <select id="ncf-feat" style="width:100%">${feats.map((f) => `<option value="${f.id}">${esc(f.name)}</option>`).join("")}</select>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" id="ncf-cancel">Cancel</button><button class="go" id="ncf-go">Continue</button></div></div>`;
  document.body.appendChild(ov);
  ov.onclick = (e) => {
    if (e.target === ov) ov.remove();
  };
  document.getElementById("ncf-cancel").onclick = () => ov.remove();
  document.getElementById("ncf-go").onclick = () => {
    const fid = document.getElementById("ncf-feat").value;
    ov.remove();
    proceed(fid);
  };
};
function cycleDateStatus(start, end) {
  const t = new Date().toISOString().slice(0, 10);
  if (start && t < start)
    return `<span class="badge mm-partial">Scheduled</span>`;
  if (end && t > end) return `<span class="badge">Ended</span>`;
  if (start || end) return `<span class="badge mm-covered">Active</span>`;
  return "";
}
window.scheduleCycle = async (cid, field, value) => {
  const c0 = window.CYCLE_DETAIL_DATA || {};
  const start =
    field === "scheduled_start_at"
      ? value
      : c0.scheduled_start_at
        ? String(c0.scheduled_start_at).slice(0, 10)
        : "";
  const end =
    field === "scheduled_end_at"
      ? value
      : c0.scheduled_end_at
        ? String(c0.scheduled_end_at).slice(0, 10)
        : "";
  if (start && end && end < start) {
    toast("End date can't be before the start date", true);
    renderCycleDetail(c0);
    return;
  }
  try {
    const c = await api("/api/test-cycles/" + cid, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field]: value || "" }),
    });
    renderCycleDetail(c);
    toast(value ? "Schedule updated" : "Schedule cleared");
  } catch (e) {
    toast(e.message, true);
  }
};
window.editCycleDescription = async (cid) => {
  const cur = (window.CYCLE_DETAIL_DATA || {}).description || "";
  const d = await uiPrompt("Edit cycle description", "Description", cur);
  if (d == null) return;
  try {
    const c = await api("/api/test-cycles/" + cid, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: d }),
    });
    renderCycleDetail(c);
    toast("Description updated");
  } catch (e) {
    toast(e.message, true);
  }
};
window.openAddCaseChooser = (cid) => {
  const ov = document.createElement("div");
  ov.style.cssText =
    "position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML = `<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:420px;width:88%;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:12px">Add test cases</div>
    <button class="go" id="acc-existing" style="width:100%;margin-bottom:8px;padding:9px">From existing project cases</button>
    <button class="ghost" id="acc-new" style="width:100%;padding:9px">Create a new test case</button>
    <div style="text-align:right;margin-top:12px"><button class="ghost" id="acc-cancel">Cancel</button></div></div>`;
  document.body.appendChild(ov);
  const close = () => ov.remove();
  ov.onclick = (e) => {
    if (e.target === ov) close();
  };
  document.getElementById("acc-cancel").onclick = close;
  document.getElementById("acc-existing").onclick = () => {
    close();
    openAddCasesToCycle(cid);
  };
  document.getElementById("acc-new").onclick = () => {
    close();
    openCreateCaseInCycle(cid);
  };
};
window.openAddCasesToCycle = async (cid) => {
  const pid = (window.CYCLE_DETAIL_DATA || {}).project_id || currentProject;
  if (!pid) {
    toast("No project", true);
    return;
  }
  let items = [];
  try {
    const r = await api(
      `/api/test-cases?project_id=${encodeURIComponent(pid)}&limit=500`,
    );
    items = r.items || [];
  } catch (e) {
    toast(e.message, true);
    return;
  }
  const existing = new Set(
    ((window.CYCLE_DETAIL_DATA || {}).items || []).map((i) => i.case_id),
  );
  const avail = items.filter((c) => !existing.has(c.id));
  if (!avail.length) {
    toast("All project test cases are already in this cycle");
    return;
  }
  const ov = document.createElement("div");
  ov.style.cssText =
    "position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML = `<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:660px;width:92%;max-height:80vh;display:flex;flex-direction:column;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:4px">Add existing test cases</div>
    <div class="muted" style="font-size:12px;margin-bottom:10px">Pick cases from this project to add to the cycle.</div>
    <input id="addcase-q" placeholder="Filter by title or ID…" style="margin-bottom:10px"/>
    <div id="addcase-list" style="overflow:auto;flex:1;border:1px solid var(--line);border-radius:8px;padding:8px"></div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" id="addcase-cancel">Cancel</button><button class="go" id="addcase-add">Add selected</button></div></div>`;
  document.body.appendChild(ov);
  const renderList = (q) => {
    const ql = (q || "").toLowerCase();
    document.getElementById("addcase-list").innerHTML =
      avail
        .filter(
          (c) =>
            !ql ||
            (c.title || "").toLowerCase().includes(ql) ||
            (c.display_id || "").toLowerCase().includes(ql),
        )
        .map(
          (c) =>
            `<label style="display:flex;gap:8px;align-items:center;padding:6px 4px;font-size:12.5px;border-bottom:1px solid rgba(255,255,255,.04)"><input type="checkbox" class="addcase-chk" value="${c.id}" style="width:auto"/>${c.display_id ? `<code style="font-size:10px;color:#94a3b8">${esc(c.display_id)}</code>` : ""}<span style="flex:1">${esc(c.title)}</span><span class="badge ${esc(c.type)}">${esc(typeLabel(c.type))}</span></label>`,
        )
        .join("") ||
      `<div class="muted" style="padding:8px">No matching cases.</div>`;
  };
  renderList("");
  document.getElementById("addcase-q").oninput = (e) =>
    renderList(e.target.value);
  const close = () => ov.remove();
  document.getElementById("addcase-cancel").onclick = close;
  ov.onclick = (e) => {
    if (e.target === ov) close();
  };
  document.getElementById("addcase-add").onclick = async () => {
    const ids = [...ov.querySelectorAll(".addcase-chk")]
      .filter((x) => x.checked)
      .map((x) => x.value);
    if (!ids.length) {
      toast("Select at least one case", true);
      return;
    }
    try {
      await api(`/api/test-cycles/${cid}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_ids: ids }),
      });
      close();
      openCycle(cid);
      loadCycles();
      toast(`${ids.length} case(s) added`);
    } catch (e) {
      toast(e.message, true);
    }
  };
};
window.startCycleItemStatusEdit = async (cid, itemId, status) => {
  const cycle = window.CYCLE_DETAIL_DATA;
  const item = (cycle?.items || []).find((x) => x.id === itemId);
  if (!item) {
    toast("Cycle item not found", true);
    return;
  }
  if (status === "failed" || status === "blocked") {
    window.CYCLE_EDIT_ITEM = itemId;
    window.CYCLE_EDIT_DRAFT = {
      status,
      actual_result: item.actual_result || "",
      notes: item.notes || "",
      defect_link: item.defect_link || "",
    };
    renderCycleDetail(cycle);
    return;
  }
  await api(`/api/test-cycles/${cid}/items`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      item_id: itemId,
      status,
      actual_result: item.actual_result || "",
      notes: item.notes || "",
      defect_link: item.defect_link || "",
    }),
  });
  const updated = await api(`/api/test-cycles/${cid}`);
  window.CYCLE_EDIT_ITEM = null;
  window.CYCLE_EDIT_DRAFT = null;
  renderCycleDetail(updated);
  loadCycles();
  toast("status updated");
};
window.updateCycleDraftField = (field, value) => {
  if (!window.CYCLE_EDIT_DRAFT) window.CYCLE_EDIT_DRAFT = {};
  window.CYCLE_EDIT_DRAFT[field] = value;
};
window.cancelCycleItemEdit = () => {
  window.CYCLE_EDIT_ITEM = null;
  window.CYCLE_EDIT_DRAFT = null;
  if (window.CYCLE_DETAIL_DATA) renderCycleDetail(window.CYCLE_DETAIL_DATA);
};
window.saveCycleItemStatus = async (cid, itemId) => {
  const draft = window.CYCLE_EDIT_DRAFT || {};
  const status = draft.status || "failed";
  await api(`/api/test-cycles/${cid}/items`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      item_id: itemId,
      status,
      actual_result: draft.actual_result || "",
      notes: draft.notes || "",
      defect_link: draft.defect_link || "",
    }),
  });
  const updated = await api(`/api/test-cycles/${cid}`);
  window.CYCLE_EDIT_ITEM = null;
  window.CYCLE_EDIT_DRAFT = null;
  renderCycleDetail(updated);
  loadCycles();
  toast("status updated");
};
window.showCycleReport = async (id) => {
  const r = await api(`/api/test-cycles/${id}/report`),
    s = r.summary || {};
  openInfoDialog({
    title: "Cycle summary",
    copy: "A quick progress snapshot for this saved test cycle.",
    summary: `<div class="cycle-detail-summary" style="margin-top:12px">
      <div class="cycle-detail-kpi"><b>${s.completion_rate || 0}%</b><span>Completion</span></div>
      <div class="cycle-detail-kpi"><b>${s.pass_rate || 0}%</b><span>Pass rate</span></div>
      <div class="cycle-detail-kpi"><b>${s.passed || 0}</b><span>Passed</span></div>
      <div class="cycle-detail-kpi"><b>${s.failed || 0}</b><span>Failed</span></div>
      <div class="cycle-detail-kpi"><b>${s.blocked || 0}</b><span>Blocked</span></div>
    </div>`,
  });
};
$("#cyc-d-close").onclick = () => {
  $("#cyc-detail-card").style.display = "none";
};
$("#cyc-d-rename").onclick = async () => {
  if (!window._cycle) return;
  const cur = (window.CYCLE_DETAIL_DATA || {}).name || "";
  const name = await uiPrompt("Rename test cycle", "Cycle name", cur);
  if (name == null) {
    return;
  }
  const trimmed = name.trim();
  if (!trimmed || trimmed === cur) return;
  try {
    const c = await api("/api/test-cycles/" + window._cycle, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: trimmed }),
    });
    renderCycleDetail(c);
    loadCycles();
    toast("Cycle renamed");
  } catch (e) {
    toast(e.message, true);
  }
};
$("#cyc-d-del").onclick = () => {
  if (!window._cycle || !window.CYCLE_DETAIL_DATA) return;
  const cycle = window.CYCLE_DETAIL_DATA;
  const counts = cycle.counts || {};
  openCaseConfirmation({
    title: "Delete test cycle",
    copy: `Delete “${cycle.name}”? This removes its saved execution state and cannot be undone.`,
    summary: `<b>${esc(cycle.name)}</b><div class="muted" style="margin-top:6px">${cycle.total || 0} cases · ${counts.passed || 0} passed · ${counts.failed || 0} failed · ${counts.blocked || 0} blocked</div>`,
    confirmLabel: "Delete cycle",
    danger: true,
    onConfirm: async () => {
      await api("/api/test-cycles/" + window._cycle, { method: "DELETE" });
      $("#cyc-detail-card").style.display = "none";
      window.CYCLE_DETAIL_DATA = null;
      window.CYCLE_EDIT_ITEM = null;
      window.CYCLE_EDIT_DRAFT = null;
      loadCycles();
      toast("Cycle deleted");
    },
  });
};

