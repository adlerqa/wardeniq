// ---- repo + branch pickers (shared by Test Cycles; moved here from 09 when the
// Mind Map screen moved to React, #257) ----
function repoBranchRows(repos, cls) {
  return (
    repos
      .map(
        (
          rp,
        ) => `<div style="display:flex;gap:8px;align-items:center;font-size:12.5px">
    <label style="display:flex;gap:6px;align-items:center;margin:0;flex:1"><input type="checkbox" class="${cls}-chk" value="${rp.id}"${repoAnalysisDefaultChecked(rp.kind) ? " checked" : ""} style="width:auto"/> ${esc(rp.full_name)} <span class="pill ${repoKindClass(rp.kind)}">${esc(repoKindLabel(rp.kind))}</span></label>
    <select class="${cls}-branch" data-rid="${rp.id}" title="branch to analyze" style="flex:0 0 220px;font-size:12px;padding:5px 8px"><option value="">${esc(rp.default_branch || "default")} (default)</option></select>
  </div>`,
      )
      .join("") ||
    `<span class="muted">no repos yet — connect one under Projects & Repos</span>`
  );
}
// populate each repo's branch <select> from the repo's configured provider
async function fillBranchDropdowns(cls, repos) {
  for (const rp of repos || []) {
    try {
      const r = await api(`/api/repos/${rp.id}/branches`);
      const sel = document.querySelector(`.${cls}-branch[data-rid="${rp.id}"]`);
      if (!sel || !(r.branches || []).length) continue;
      const def = r.default || rp.default_branch || "";
      sel.innerHTML =
        `<option value="">${esc(def || "default")} (default)</option>` +
        r.branches
          .filter((b) => b !== def)
          .map((b) => `<option value="${esc(b)}">${esc(b)}</option>`)
          .join("");
    } catch (e) {
      /* leave the default-only option if branches can't be fetched */
    }
  }
}
function collectBranches(cls) {
  const m = {};
  document.querySelectorAll(`.${cls}-branch`).forEach((i) => {
    if (i.value.trim()) m[i.dataset.rid] = i.value.trim();
  });
  return m;
}
// Pick ANY repo the GitHub PAT can access, add it to the project, then it's analyzable here.
async function openGitRepoPicker(pid, reload) {
  if (!pid) {
    toast("Pick a project first", true);
    return;
  }
  let repos = [];
  try {
    // Use the PROJECT's PAT (same source the Connect-repo picker uses), not the global token.
    for (let page = 1; page <= 4; page++) {
      const r = await api(
        `/api/projects/${pid}/github/accessible-repos?page=${page}`,
      );
      const batch = r.repos || [];
      repos = repos.concat(batch);
      if (batch.length < 30) break;
    }
  } catch (e) {
    toast(
      `Couldn't list repos for this project (${e.message}). Check the project's GitHub PAT under Projects & Repos.`,
      true,
    );
    return;
  }
  // drop repos already connected to this project so they don't show up twice
  try {
    const pr = await api(`/api/projects/${pid}/repos`);
    const existing = new Set(
      (pr.repos || []).map((r) => (r.full_name || "").toLowerCase()),
    );
    repos = repos.filter(
      (r) => !existing.has((r.full_name || "").toLowerCase()),
    );
  } catch (e) {}
  if (!repos.length) {
    toast(
      "No new repos to add — all your accessible repos are already in this project",
      true,
    );
    return;
  }
  const ov = document.createElement("div");
  ov.style.cssText =
    "position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML = `<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:680px;width:92%;max-height:82vh;display:flex;flex-direction:column;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:4px">Add a repo from GitHub</div>
    <div class="muted" style="font-size:12px;margin-bottom:10px">Any repository your GitHub token can access. Selected repos are added to the project and become available to analyze here.</div>
    <input id="gitrepo-q" placeholder="Filter repositories…" style="margin-bottom:10px"/>
    <div id="gitrepo-list" style="overflow:auto;flex:1;border:1px solid var(--line);border-radius:8px;padding:8px"></div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" id="gitrepo-cancel">Cancel</button><button class="go" id="gitrepo-add">Add selected</button></div></div>`;
  document.body.appendChild(ov);
  const render = (q) => {
    const ql = (q || "").toLowerCase();
    document.getElementById("gitrepo-list").innerHTML =
      repos
        .filter((r) => !ql || (r.full_name || "").toLowerCase().includes(ql))
        .slice(0, 300)
        .map(
          (r) =>
            `<label style="display:flex;gap:8px;align-items:center;padding:6px 4px;font-size:12.5px;border-bottom:1px solid rgba(255,255,255,.04)"><input type="checkbox" class="gitrepo-chk" value="${esc(r.full_name)}" data-def="${esc(r.default_branch || "main")}" style="width:auto"/><span style="flex:1">${esc(r.full_name)}</span>${r.private ? `<span class="pill">private</span>` : ""}${r.language ? `<span class="badge">${esc(r.language)}</span>` : ""}</label>`,
        )
        .join("") || `<div class="muted" style="padding:8px">No matches.</div>`;
  };
  render("");
  document.getElementById("gitrepo-q").oninput = (e) => render(e.target.value);
  const close = () => ov.remove();
  ov.onclick = (e) => {
    if (e.target === ov) close();
  };
  document.getElementById("gitrepo-cancel").onclick = close;
  document.getElementById("gitrepo-add").onclick = async () => {
    const picks = [...ov.querySelectorAll(".gitrepo-chk")].filter(
      (x) => x.checked,
    );
    if (!picks.length) {
      toast("Select at least one repo", true);
      return;
    }
    let ok = 0,
      fail = 0;
    for (const p of picks) {
      try {
        await api(`/api/projects/${pid}/repos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            repo_full_name: p.value,
            default_branch: p.dataset.def || "main",
            repo_type: "app",
          }),
        });
        ok++;
      } catch (e) {
        fail++;
      }
    }
    close();
    toast(
      `${ok} repo(s) added${fail ? ` · ${fail} skipped (already added or inaccessible)` : ""}`,
    );
    if (reload) reload();
  };
}
if ($("#cyc-add-git"))
  $("#cyc-add-git").onclick = () =>
    openGitRepoPicker($("#cyc-proj").value || currentProject, loadCycleRepos);

// ---- code analysis (change impact) ----
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
// The Test Cycles screen (cycle list, templates, cycle detail) moved to React:
// src/features/test-cycles/ (#257). It registers window.loadCycles /
// window.openCycle, which createCycleFromSelection below still calls.
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
