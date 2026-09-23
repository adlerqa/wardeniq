// ---- mind map (deep code analysis) ----
async function initMindmap() {
  await loadProjects();
  await loadMindmapRepos();
  loadMindmap();
}
$("#mm-proj").onchange = () => {
  currentProject = $("#mm-proj").value;
  loadMindmapRepos();
  loadMindmap();
};
$("#mm-refresh").onclick = () => loadMindmap();
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
if ($("#mm-add-git"))
  $("#mm-add-git").onclick = () =>
    openGitRepoPicker($("#mm-proj").value || currentProject, loadMindmapRepos);
async function loadMindmapRepos() {
  const pid = $("#mm-proj").value || currentProject;
  if (!pid) return;
  try {
    const r = await api(`/api/projects/${pid}/repos?repo_type=app`); // app repos only (test repos excluded)
    $("#mm-repos").innerHTML = repoBranchRows(r.repos, "mm-repo");
    fillBranchDropdowns("mm-repo", r.repos);
  } catch (e) {}
}
$("#mm-analyze").onclick = async () => {
  const ids = [...document.querySelectorAll(".mm-repo-chk")]
    .filter((c) => c.checked)
    .map((c) => c.value);
  if (!ids.length) {
    toast("Select at least one repo", true);
    return;
  }
  const pid = $("#mm-proj").value || currentProject;
  const branches = collectBranches("mm-repo");
  $("#mm-status").textContent =
    `Starting implementation coverage review for ${ids.length} repo${ids.length === 1 ? "" : "s"}…`;
  $("#mm-analyze").disabled = true;
  setBusy("#mm-analyze", true);
  $("#mm-diag").innerHTML = "";
  skIn("#mm-map", skeleton.rows(5, "Analyzing code coverage"));
  try {
    const r = await api("/api/code-analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: pid, repo_ids: ids, branches }),
    });
    watchMindmap(r.job_id);
  } catch (e) {
    $("#mm-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
    $("#mm-analyze").disabled = false;
    setBusy("#mm-analyze", false);
  }
};
function formatMindmapStage(stage) {
  const s = (stage || "").toLowerCase();
  if (!s) return "Preparing implementation coverage review…";
  if (
    s.startsWith("fetching github code") ||
    s.startsWith("fetching gitlab code")
  )
    return "Downloading repository code…";
  if (s.startsWith("reusing index"))
    return "Reusing the existing code index for unchanged repositories…";
  if (s.startsWith("indexed "))
    return "Indexing implementation files and preparing coverage checks…";
  if (s.startsWith("reviewing — "))
    return `Reviewing coverage for ${stage.split("reviewing — ")[1] || "the selected feature"}…`;
  return stage;
}
function watchMindmap(jobId) {
  if (!jobId) return;
  watchJob(jobId, (j) => {
    const a = j.result || {};
    const progressBits = [
      a.code_chunks ? `${a.code_chunks} implementation chunks indexed` : null,
      a.features_mapped
        ? `${a.features_mapped} feature${a.features_mapped === 1 ? "" : "s"} reviewed`
        : null,
    ]
      .filter(Boolean)
      .join(" · ");
    $("#mm-status").innerHTML =
      j.status === "running"
        ? `⏳ ${esc(formatMindmapStage(j.stage))}${progressBits ? ` <span class="muted">· ${esc(progressBits)}</span>` : ""}`
        : j.status === "failed"
          ? `<span class="err">Analysis failed: ${esc(j.error || "")}</span>`
          : `Review complete · ${a.code_chunks || 0} implementation chunks indexed · ${a.features_mapped || 0} feature${(a.features_mapped || 0) === 1 ? "" : "s"} reviewed${a.tests_skipped ? ` · ${a.tests_skipped} test files excluded` : ""}${a.note ? ` · <span class="warn">${esc(a.note)}</span>` : ""}${(a.errors || []).length ? ` · <span class="err">${a.errors.length} repo issue(s)</span>` : ""}`;
    if (j.status !== "running") {
      $("#mm-analyze").disabled = false;
      setBusy("#mm-analyze", false);
      renderMindmapDiag(a.per_repo || []);
      loadMindmap();
    }
  });
}
function renderMindmapDiag(perRepo) {
  if (!perRepo.length) {
    $("#mm-diag").innerHTML = "";
    return;
  }
  $("#mm-diag").innerHTML =
    `<div class="card mindmap-diagnostics"><details><summary>Indexed code by repository</summary>
    <div class="sub" style="margin-top:8px">Production files indexed from each repo's selected branch (test/spec files excluded). If a file you expected is missing here, it's not on that branch — pick the right branch and re-run.</div>` +
    perRepo
      .map((r) =>
        r.error
          ? `<div class="stepitem"><b>${esc(r.repo)}</b> <span class="badge mm-uncovered">fetch error</span><div class="err">${esc(r.error)}</div></div>`
          : r.reused
            ? `<div class="stepitem"><b>${esc(r.repo)}</b> <span class="pill">${esc(r.branch || "default")}</span> <span class="badge mm-covered">index reused (unchanged)</span> <span class="muted">${r.impl_files} impl files</span></div>`
            : `<div class="stepitem"><b>${esc(r.repo)}</b> <span class="pill">${esc(r.branch || "default")}</span>
         <span class="muted">${r.files_in_repo} files in repo · <b style="color:var(--text)">${r.impl_files} impl indexed</b> · ${r.test_files} tests excluded</span>
         ${(r.extensions || []).length ? `<div class="muted" style="margin-top:3px">extensions: ${r.extensions.map((e) => `<code>${esc(e[0])}×${e[1]}</code>`).join(" ")}</div>` : ""}
         ${
           (r.impl_sample || []).length
             ? `<div class="muted" style="margin-top:3px">indexed files: ${r.impl_sample.map((s) => `<code>${esc(s)}</code>`).join(" ")}</div>`
             : (r.sample || []).length
               ? `<div class="muted" style="margin-top:3px">sample paths: ${r.sample
                   .slice(0, 8)
                   .map((s) => `<code>${esc(s)}</code>`)
                   .join(" ")}</div>`
               : ""
         }</div>`,
      )
      .join("") +
    `</details></div>`;
}
// #21: explain an empty/never-succeeded Mind Map result instead of just showing
// "not analyzed" — which branch was read, how many files survived test/spec
// exclusion per repo, and why (from the job's own diagnostics, which otherwise
// only existed for as long as the live watchJob() poll that started it was open).
function analysisEmptyReasonHtml(lastAnalysis) {
  if (!lastAnalysis) return "";
  const repoLines = (lastAnalysis.per_repo || [])
    .map((r) => {
      const branch = esc(r.branch || "default");
      if (r.error)
        return `<code>${esc(r.repo)}</code> (branch ${branch}) — fetch error: ${esc(r.error)}`;
      if (r.reused)
        return `<code>${esc(r.repo)}</code> (branch ${branch}): ${r.impl_files || 0} implementation file(s) indexed (reused, unchanged since last run)`;
      const total = r.files_in_repo ?? 0;
      const impl = r.impl_files ?? 0;
      return `<code>${esc(r.repo)}</code> (branch ${branch}): ${total} file(s) total, ${impl} remaining after excluding ${r.test_files || 0} test file(s) and ${r.non_impl_files || 0} non-implementation file(s)`;
    })
    .join("<br>");
  if (!lastAnalysis.note && !repoLines && !(lastAnalysis.errors || []).length) return "";
  const when = lastAnalysis.at
    ? new Date(lastAnalysis.at * 1000).toLocaleString()
    : "";
  return `<div class="card mindmap-empty-reason" style="margin-top:8px">
    <div class="sub">Last analysis${when ? ` (${esc(when)})` : ""} mapped ${lastAnalysis.features_mapped || 0} feature${(lastAnalysis.features_mapped || 0) === 1 ? "" : "s"}.</div>
    ${lastAnalysis.note ? `<div class="warn" style="margin-top:4px">${esc(lastAnalysis.note)}</div>` : ""}
    ${repoLines ? `<div class="muted" style="margin-top:6px;font-size:11.5px">${repoLines}</div>` : ""}
    ${(lastAnalysis.errors || []).length ? `<div class="err" style="margin-top:4px">${lastAnalysis.errors.map((e) => esc(e)).join("<br>")}</div>` : ""}
  </div>`;
}
async function loadMindmap() {
  const pid = $("#mm-proj").value || currentProject;
  // Guard: if we're called with no project (selector cleared while an Analyze
  // job was in flight, or nav returned before a project is picked), CLEAR the
  // loader first — otherwise the "Downloading repository code…" loader set by
  // the Analyze click stays on screen forever.
  const mmEl = $("#mm-map");
  if (!pid) {
    if (mmEl)
      mmEl.innerHTML = `<div class="card"><span class="muted">Pick a project to see its coverage map.</span></div>`;
    return;
  }
  skIn("#mm-map", skeleton.rows(5, "Loading coverage map"));
  try {
    const r = await api(`/api/projects/${pid}/mindmap`);
    MM_DATA = r;
    MM_FOCUS = null;
    renderMmGraph();
    if (!r.features.length) {
      $("#mm-map").innerHTML =
        `<div class="card"><span class="muted">No features in this project yet.</span></div>`;
      return;
    }
    const tot = { covered: 0, partial: 0, uncovered: 0 };
    r.features.forEach((f) => {
      tot.covered += f.counts.covered;
      tot.partial += f.counts.partial;
      tot.uncovered += f.counts.uncovered;
    });
    const grand = tot.covered + tot.partial + tot.uncovered;
    const head = `<div class="mindmap-summary-card"><div class="mindmap-summary-head"><h2>Project coverage map</h2>
      <div class="mindmap-chip-row">${mmChip("covered", tot.covered)} ${mmChip("partial", tot.partial)} ${mmChip("uncovered", tot.uncovered)}</div></div>
      ${grand ? mmBar(tot, grand) : `<div class="sub">Not analyzed yet — click <b>Analyze codebase</b> to read the code and map coverage.</div>`}</div>
      ${grand ? "" : analysisEmptyReasonHtml(r.last_analysis)}`;
    const cards = r.features
      .map((f) => {
        const c = f.counts;
        const t = c.covered + c.partial + c.uncovered;
        const cases = (f.cases || [])
          .slice()
          .sort((x, y) => mmRank(x.status) - mmRank(y.status))
          .map(
            (cs) =>
              `<div class="mindmap-case-item"><div class="mindmap-case-title">
          <span class="mm-case-left"><span class="mm-dot ${cs.status}"></span>${cs.display_id ? `<code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px;color:#94a3b8">${esc(cs.display_id)}</code>` : ""}<b>${esc(cs.title)}</b></span>
          <span class="mm-case-right"><span class="badge ${cs.type}">${esc(typeLabel(cs.type))}</span><span class="badge mm-${cs.status}">${cs.status}</span></span>
          </div><div class="mindmap-case-body">${esc(cs.rationale || "")}${(cs.files || []).length ? `<br><span style="color:var(--accent2)">Files reviewed:</span> ${cs.files.map((ff) => `<code>${esc(ff)}</code>`).join(" ")}` : ""}</div></div>`,
          )
          .join("");
        const open = c.uncovered > 0 || c.partial > 0 ? " open" : "";
        return `<details class="mindmap-feature-card"${open}><summary>
        <div class="mindmap-summary-main"><div class="mindmap-feature-title"><strong>${esc(f.feature)}</strong> <span class="pill">v${f.version}</span> ${f.analyzed ? "" : '<span class="badge">not analyzed</span>'}</div>
        ${f.repos && f.repos.length ? `<div class="mindmap-feature-meta">Reviewed against ${f.repos.map((rp) => `<span class="pill">${esc(rp)}</span>`).join(" ")}</div>` : ""}</div>
        <div class="mindmap-chip-row">${mmChip("covered", c.covered)} ${mmChip("partial", c.partial)} ${mmChip("uncovered", c.uncovered)}</div></summary>
        <div class="mindmap-feature-body">
        ${t ? mmBar(c, t) : `<div class="muted" style="margin:6px 0">${f.case_count || 0} test cases — run analysis to map them to code.</div>`}
        ${
          // #21: "found code, judged uncovered" reads very differently from
          // "nothing found" — every case here WAS reviewed against real
          // implementation files, they just didn't match anything.
          t && c.covered === 0 && c.partial === 0 && (f.reviewed_files || []).length
            ? `<div class="warn" style="margin:6px 0;font-size:12px">All ${t} reviewed case${t === 1 ? "" : "s"} came back uncovered. ${f.reviewed_files.length} implementation file${f.reviewed_files.length === 1 ? " was" : "s were"} read for this feature — this may be an accurate gap, or the implementing code may live in a repo/branch that isn't connected here.</div>`
            : ""
        }
        ${(f.reviewed_files || []).length ? `<details style="margin:6px 0 8px"><summary class="muted" style="cursor:pointer;font-size:11.5px">Files reviewed for this feature (${f.reviewed_files.length})</summary><div class="muted" style="margin-top:4px">${f.reviewed_files.map((ff) => `<code>${esc(ff)}</code>`).join(" ")}</div></details>` : ""}
        <div class="mindmap-case-list">${cases}</div></div></details>`;
      })
      .join("");
    $("#mm-map").innerHTML = head + cards;
  } catch (e) {
    $("#mm-map").innerHTML =
      `<div class="card err">Couldn't load the coverage map. ${esc(e.message)}</div>`;
  }
}
const mmRank = (s) => ({ covered: 0, partial: 1, uncovered: 2 })[s] ?? 3;
const mmChip = (s, n) => `<span class="badge mm-${s}">${n} ${s}</span>`;
function mmBar(c, t) {
  const p = (k) => Math.round(((c[k] || 0) / t) * 100);
  return `<div class="mm-bar" title="${c.covered} covered · ${c.partial} partial · ${c.uncovered} uncovered">
    <span class="mm-seg covered" style="width:${p("covered")}%"></span><span class="mm-seg partial" style="width:${p("partial")}%"></span><span class="mm-seg uncovered" style="width:${p("uncovered")}%"></span></div>`;
}

// ============ Implementation coverage MAP (zero-dependency SVG) ==============
// Structure: PROJECT → REPOSITORY → FEATURE → STATUS → test cases.
// Two layouts, auto-selected so the map NEVER crowds:
//   • radial  — small projects (few features). Ring radius is derived from the real
//     node widths, so boxes are mathematically incapable of overlapping.
//   • tree    — anything larger. A tidy horizontal tree whose row for every node comes
//     from its subtree's leaf count, so it stays clean at any number of repos,
//     features or cases (the canvas grows and the stage scrolls instead of blurring).
// Hand-rolled SVG + vanilla JS (no CDN/D3) so it works air-gapped.
let MM_DATA = null,
  MM_SEL = null,
  MM_FILTER = null,
  MM_K = 1,
  MM_MODE = "auto";
const MM_C = {
  covered: "#34d399",
  partial: "#fbbf24",
  uncovered: "#f87171",
  hub: "#60a5fa",
  repo: "#38bdf8",
  feat: "#a78bfa",
  file: "#7dd3fc",
};
const MM_ST = ["covered", "partial", "uncovered"];
const MM_RADIAL_MAX = 9; // beyond this, radial can't stay legible → tree
const MM_LEAF_CAP = 48; // cases drawn per expanded feature before "+N more"
const mmTrunc = (s, n) => {
  s = String(s || "");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
};
const mmTip = (h) => `data-tip="${String(h).replace(/"/g, "&quot;")}"`;
const mmPct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const mmPolar = (cx, cy, r, d) => [
  cx + r * Math.cos((d * Math.PI) / 180),
  cy + r * Math.sin((d * Math.PI) / 180),
];
function mmWrap(s, per, max) {
  const w = String(s || "").split(/\s+/),
    out = [];
  let cur = "";
  for (const x of w) {
    if (!cur) {
      cur = x;
      continue;
    }
    if ((cur + " " + x).length <= per) cur += " " + x;
    else {
      out.push(cur);
      cur = x;
      if (out.length === max) break;
    }
  }
  if (cur && out.length < max) out.push(cur);
  return out.length ? out.slice(0, max) : [""];
}
function mmLabel(f, feats) {
  const d = feats.filter((x) => x.name === f.name);
  return d.length < 2 ? f.name : `${f.name} (${d.indexOf(f) + 1}/${d.length})`;
}
function mmModel(data) {
  const feats = ((data && data.features) || []).map((f, i) => {
    const c = f.counts || {},
      total = MM_ST.reduce((s, k) => s + (c[k] || 0), 0);
    const files = new Set();
    (f.cases || []).forEach((cs) =>
      (cs.files || []).forEach((x) => files.add(x)),
    );
    (f.reviewed_files || []).forEach((x) => files.add(x));
    return {
      i,
      id: f.feature_id,
      name: f.feature,
      version: f.version,
      counts: c,
      total,
      cases: (f.cases || [])
        .slice()
        .sort((a, b) => mmRank(a.status) - mmRank(b.status)),
      repos: f.repos || [],
      files: [...files],
      case_count: f.case_count || 0,
    };
  });
  feats.forEach((f) => (f.label = mmLabel(f, feats)));
  const totals = { covered: 0, partial: 0, uncovered: 0 };
  feats.forEach((f) => MM_ST.forEach((k) => (totals[k] += f.counts[k] || 0)));
  // group features under the repo they were reviewed against (a feature spanning
  // several repos is listed under each, which is what "reviewed against" means)
  const groups = new Map();
  feats.forEach((f) => {
    (f.repos.length ? f.repos : ["(no repository)"]).forEach((r) => {
      if (!groups.has(r)) groups.set(r, []);
      groups.get(r).push(f);
    });
  });
  const ev = new Map();
  feats.forEach((f) =>
    f.cases.forEach((c) =>
      (c.files || []).forEach((fp) => {
        if (!ev.has(fp)) ev.set(fp, { cases: 0, feats: new Set() });
        const e = ev.get(fp);
        e.cases++;
        e.feats.add(f.i);
      }),
    ),
  );
  return {
    feats,
    totals,
    grand: MM_ST.reduce((s, k) => s + totals[k], 0),
    repos: [...groups.keys()],
    groups,
    evidence: [...ev.entries()]
      .map(([file, e]) => ({ file, cases: e.cases, feats: e.feats.size }))
      .sort((a, b) => b.cases - a.cases),
  };
}
const MM_DEFS = `<defs>
  <filter id="mmSh" x="-60%" y="-60%" width="220%" height="220%">
    <feDropShadow dx="0" dy="2" stdDeviation="3.5" flood-color="#000" flood-opacity=".5"/></filter>
  <linearGradient id="mmCard" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#1a2333"/><stop offset="100%" stop-color="#141b28"/></linearGradient>
  <radialGradient id="mmHubG" cx="50%" cy="38%">
    <stop offset="0%" stop-color="#1e3busted"/><stop offset="100%" stop-color="#101927"/></radialGradient>
</defs>`.replace("#1e3busted", "#1e3a5f");
function mmStage(inner, W, H, scroll) {
  return `<svg class="mm-svg${scroll ? " mm-svg-tall" : ""}" viewBox="0 0 ${W} ${H}"
    preserveAspectRatio="xMidYMin meet" style="${scroll ? `height:${H}px;` : ""}" role="img"
    aria-label="implementation coverage map">${MM_DEFS}
    <g id="mm-zoom" transform="translate(${W / 2},${H / 2}) scale(${MM_K}) translate(${-W / 2},${-H / 2})">${inner}</g></svg>`;
}
// shared node painters ------------------------------------------------------
function mmStatBar(x, y, w, f) {
  const t = f.total || 1,
    s = (k) => Math.max(0, ((f.counts[k] || 0) / t) * w);
  return `<g transform="translate(${x},${y})"><rect width="${w}" height="5" rx="2.5" fill="#0d1420"/>
    <rect width="${s("covered")}" height="5" rx="2.5" fill="${MM_C.covered}"/>
    <rect x="${s("covered")}" width="${s("partial")}" height="5" rx="2.5" fill="${MM_C.partial}"/>
    <rect x="${s("covered") + s("partial")}" width="${s("uncovered")}" height="5" rx="2.5" fill="${MM_C.uncovered}"/></g>`;
}
const mmFeatTip = (f) =>
  mmTip(
    `<b>${esc(f.label)}</b> · v${f.version}<br>${mmPct(f.counts.covered || 0, f.total || 1)}% implemented · ${f.total || f.case_count} cases` +
      (f.repos.length ? `<br>${esc(f.repos.join(", "))}` : "") +
      `<br><i>click to expand</i>`,
  );
const mmCaseTip = (c) =>
  mmTip(
    `<b>${esc(mmTrunc(c.title, 80))}</b><br><span class="mm-t-${c.status}">${c.status}</span> · ${esc(typeLabel(c.type || ""))}` +
      (c.rationale ? `<br>${esc(mmTrunc(c.rationale, 170))}` : "") +
      ((c.files || []).length
        ? `<br>evidence: ${c.files
            .slice(0, 2)
            .map((x) => `<code>${esc(mmTrunc(x, 32))}</code>`)
            .join(" ")}`
        : "<br><i>no implementing file found</i>"),
  );

// ---- dispatch -------------------------------------------------------------
function mmLayout(m) {
  return MM_MODE !== "auto"
    ? MM_MODE
    : m.feats.length <= MM_RADIAL_MAX && m.repos.length <= 1
      ? "radial"
      : "tree";
}
function mmMap(m) {
  if (!m.feats.length)
    return `<div class="mm-empty">No features in this project yet — add one, then run <b>Analyze codebase</b>.</div>`;
  return mmLayout(m) === "tree"
    ? mmTree(m)
    : MM_SEL != null
      ? mmRadialFocus(m)
      : mmRadial(m);
}
// ---- layout A: radial (small projects) -----------------------------------
function mmRadial(m) {
  const n = m.feats.length,
    BW = 180,
    BH = 58,
    sector = 360 / n;
  // radius that guarantees no overlap: needed circumference / 2π (+ breathing room)
  const R1 = Math.max(210, Math.ceil((n * (BW + 34)) / (2 * Math.PI)));
  const R2 = R1 + 165,
    W = Math.ceil((R2 + 150) * 2),
    H = W;
  const cx = W / 2,
    cy = H / 2;
  let rings = `<circle cx="${cx}" cy="${cy}" r="${R1}" class="mm-ring"/><circle cx="${cx}" cy="${cy}" r="${R2}" class="mm-ring"/>`;
  let links = "",
    nodes = "",
    clus = "";
  m.feats.forEach((f, idx) => {
    const ang = -90 + idx * sector,
      [fx, fy] = mmPolar(cx, cy, R1, ang);
    const lines = mmWrap(f.label, 21, 2),
      bh = 30 + lines.length * 14;
    links += `<path class="mm-edge" style="stroke-width:${Math.max(1.8, Math.min(8, (f.total || 1) / 11))}"
      d="M${cx},${cy} C${cx + (fx - cx) * 0.45},${cy + (fy - cy) * 0.45} ${cx + (fx - cx) * 0.7},${cy + (fy - cy) * 0.7} ${fx},${fy}"/>`;
    const act = MM_ST.filter((k) => (f.counts[k] || 0) > 0);
    act.forEach((k, j) => {
      const span = Math.min(sector * 0.7, 34 * act.length),
        a =
          ang -
          span / 2 +
          (act.length <= 1 ? span / 2 : (span * j) / (act.length - 1));
      const [bx, by] = mmPolar(cx, cy, R2, a),
        v = f.counts[k] || 0,
        r = 15 + Math.min(15, Math.sqrt(v) * 3);
      links += `<path class="mm-edge ${k}" style="stroke-width:${Math.max(1.6, Math.min(9, v / 5))}"
        d="M${fx},${fy} C${fx + (bx - fx) * 0.5},${fy + (by - fy) * 0.5} ${fx + (bx - fx) * 0.7},${fy + (by - fy) * 0.7} ${bx},${by}"/>`;
      clus += `<g class="mm-node mm-clu" data-mmbucket="${f.i}:${k}" ${mmTip(`<b>${v} ${k}</b> case${v === 1 ? "" : "s"}<br>in ${esc(mmTrunc(f.label, 38))}<br><i>click to open</i>`)}>
        <circle cx="${bx}" cy="${by}" r="${r}" fill="${MM_C[k]}" fill-opacity=".15" stroke="${MM_C[k]}" stroke-width="1.6"/>
        <text x="${bx}" y="${by + 1}" class="mm-clu-n" fill="${MM_C[k]}">${v}</text>
        <text x="${bx}" y="${by + r + 13}" class="mm-clu-l">${k}</text></g>`;
    });
    if (!act.length) {
      const [bx, by] = mmPolar(cx, cy, R2, ang);
      clus += `<g class="mm-node" ${mmTip(`${esc(f.label)}<br>${f.case_count} cases · not analyzed`)}>
        <circle cx="${bx}" cy="${by}" r="18" class="mm-clu-empty"/><text x="${bx}" y="${by + 3}" class="mm-clu-l">n/a</text></g>`;
    }
    nodes += `<g class="mm-node mm-feat" data-mmfeat="${f.i}" ${mmFeatTip(f)}>
      <rect x="${fx - BW / 2}" y="${fy - bh / 2}" width="${BW}" height="${bh}" rx="12" class="mm-card" filter="url(#mmSh)"/>
      ${lines.map((l, li) => `<text x="${fx}" y="${fy - bh / 2 + 19 + li * 14}" class="mm-card-t">${esc(l)}</text>`).join("")}
      ${mmStatBar(fx - 66, fy + bh / 2 - 15, 132, f)}
      <text x="${fx}" y="${fy + bh / 2 - 2}" class="mm-card-m">v${f.version} · ${f.total || f.case_count} cases · ${mmPct(f.counts.covered || 0, f.total || 1)}%</text></g>`;
  });
  return mmStage(rings + links + mmHub(m, cx, cy) + nodes + clus, W, H);
}
function mmHub(m, cx, cy) {
  const pct = mmPct(m.totals.covered, m.grand);
  return `<g class="mm-node" ${mmTip(`<b>${m.feats.length} features · ${m.grand} judged cases</b><br>${m.totals.covered} covered · ${m.totals.partial} partial · ${m.totals.uncovered} uncovered`)}>
    <circle cx="${cx}" cy="${cy}" r="76" fill="url(#mmHubG)" stroke="${MM_C.hub}" stroke-width="2" filter="url(#mmSh)"/>
    <text x="${cx}" y="${cy - 8}" class="mm-hub-n">${pct}%</text>
    <text x="${cx}" y="${cy + 11}" class="mm-hub-l">implemented</text>
    <text x="${cx}" y="${cy + 30}" class="mm-hub-s">${m.grand} cases · ${m.feats.length} features</text></g>`;
}
function mmRadialFocus(m) {
  const f = m.feats.find((x) => x.i === MM_SEL);
  if (!f) return mmRadial(m);
  const cs = MM_FILTER
    ? f.cases.filter((c) => c.status === MM_FILTER)
    : f.cases;
  const shown = cs.slice(0, MM_LEAF_CAP),
    n = shown.length || 1;
  // ring capacity from arc length so labels never collide
  const per = Math.max(8, Math.min(20, Math.floor(n / Math.ceil(n / 20)) || n));
  const ringCount = Math.ceil(n / per),
    R0 = 210,
    RS = 118;
  const Rmax = R0 + (ringCount - 1) * RS,
    W = Math.ceil((Rmax + 300) * 2),
    H = W;
  const cx = W / 2,
    cy = H / 2;
  let links = "",
    dots = "",
    labels = "";
  shown.forEach((c, j) => {
    const ring = Math.floor(j / per),
      inRing = Math.min(per, n - ring * per);
    const a = -90 + (360 * (j % per)) / inRing + (ring % 2 ? 180 / inRing : 0);
    const R = R0 + ring * RS,
      [dx, dy] = mmPolar(cx, cy, R, a);
    links += `<path class="mm-edge ${c.status}" style="stroke-width:2;opacity:.45"
      d="M${cx},${cy} C${cx + (dx - cx) * 0.5},${cy + (dy - cy) * 0.5} ${cx + (dx - cx) * 0.72},${cy + (dy - cy) * 0.72} ${dx},${dy}"/>`;
    dots += `<g class="mm-node" ${mmCaseTip(c)}><circle cx="${dx}" cy="${dy}" r="9" fill="${MM_C[c.status]}" class="mm-leaf"/></g>`;
    const right = dx >= cx;
    labels += `<text x="${dx + (right ? 14 : -14)}" y="${dy + 4}" class="mm-leaf-t" text-anchor="${right ? "start" : "end"}">${esc(mmTrunc(c.title, 30))}</text>`;
  });
  const ttl = mmWrap(f.label, 18, 2);
  const hub = `<g class="mm-node mm-hub-back" ${mmTip("back to all features")}>
    <circle cx="${cx}" cy="${cy}" r="94" fill="url(#mmHubG)" stroke="${MM_C.feat}" stroke-width="2" filter="url(#mmSh)"/>
    ${ttl.map((l, i) => `<text x="${cx}" y="${cy - 34 + i * 15}" class="mm-hub-l" style="font-size:12px;fill:#e6edf6">${esc(l)}</text>`).join("")}
    <text x="${cx}" y="${cy + 2}" class="mm-hub-n" style="font-size:22px">${mmPct(f.counts.covered || 0, f.total || 1)}%</text>
    <text x="${cx}" y="${cy + 20}" class="mm-hub-s">${cs.length} ${esc(MM_FILTER || "cases")}</text>
    ${mmStatBar(cx - 75, cy + 30, 150, f)}
    <text x="${cx}" y="${cy + 58}" class="mm-hub-s">← back</text></g>`;
  return (
    mmStage(links + hub + dots + labels, W, H) +
    (cs.length > MM_LEAF_CAP
      ? `<div class="mm-note">Showing ${MM_LEAF_CAP} of ${cs.length} cases — filter by status, or use the list below.</div>`
      : "")
  );
}
// ---- layout B: tidy tree (scales to many repos / features / cases) --------
function mmTree(m) {
  const multi = m.repos.length > 1,
    ROW = 30,
    PAD = 64;
  const COL = {
    root: 26,
    repo: 250,
    feat: multi ? 470 : 300,
    leaf: multi ? 760 : 600,
  };
  const W = 1210;
  // 1) leaves in document order → y is a pure function of leaf index (no overlap ever)
  const leaves = [];
  const groups = [];
  (multi ? m.repos : [null]).forEach((rp) => {
    const fs = multi ? m.groups.get(rp) : m.feats;
    const g = { repo: rp, feats: [] };
    fs.forEach((f) => {
      const item = { f, kids: [] };
      if (MM_SEL === f.i) {
        const cs = MM_FILTER
          ? f.cases.filter((c) => c.status === MM_FILTER)
          : f.cases;
        cs.slice(0, MM_LEAF_CAP).forEach((c) =>
          item.kids.push({ kind: "case", c }),
        );
        if (cs.length > MM_LEAF_CAP)
          item.kids.push({ kind: "more", n: cs.length - MM_LEAF_CAP });
        if (!cs.length) item.kids.push({ kind: "none" });
      } else {
        const act = MM_ST.filter((k) => (f.counts[k] || 0) > 0);
        (act.length ? act : ["na"]).forEach((k) =>
          item.kids.push({ kind: "bucket", k, v: f.counts[k] || 0 }),
        );
      }
      item.kids.forEach((k) => {
        k.y = PAD + leaves.length * ROW;
        leaves.push(k);
      });
      item.y = (item.kids[0].y + item.kids[item.kids.length - 1].y) / 2;
      g.feats.push(item);
    });
    g.y = g.feats.length
      ? (g.feats[0].y + g.feats[g.feats.length - 1].y) / 2
      : PAD;
    groups.push(g);
  });
  const H = Math.max(300, PAD + leaves.length * ROW + 34);
  const rootY = groups.length
    ? (groups[0].y + groups[groups.length - 1].y) / 2
    : H / 2;
  const edge = (x0, y0, x1, y1, cls, sw) => {
    const mx = (x0 + x1) / 2;
    return `<path class="mm-edge${cls ? " " + cls : ""}" style="stroke-width:${sw || 1.6}" d="M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}"/>`;
  };
  let out =
    `<text x="${COL.root}" y="30" class="mm-col-h">PROJECT</text>` +
    (multi
      ? `<text x="${COL.repo}" y="30" class="mm-col-h">REPOSITORY (${m.repos.length})</text>`
      : "") +
    `<text x="${COL.feat}" y="30" class="mm-col-h">FEATURE (${m.feats.length})</text>` +
    `<text x="${COL.leaf}" y="30" class="mm-col-h">${MM_SEL != null ? "TEST CASES" : "COVERAGE"}</text>`;
  const pct = mmPct(m.totals.covered, m.grand);
  out += `<g class="mm-node" ${mmTip(`<b>${m.feats.length} features · ${m.grand} judged cases</b><br>${m.totals.covered} covered · ${m.totals.partial} partial · ${m.totals.uncovered} uncovered`)}>
    <rect x="${COL.root}" y="${rootY - 31}" width="186" height="62" rx="13" fill="url(#mmHubG)" stroke="${MM_C.hub}" stroke-width="1.6" filter="url(#mmSh)"/>
    <text x="${COL.root + 16}" y="${rootY - 8}" class="mm-tree-pct">${pct}%</text>
    <text x="${COL.root + 70}" y="${rootY - 9}" class="mm-hub-l" style="text-anchor:start">implemented</text>
    <text x="${COL.root + 16}" y="${rootY + 11}" class="mm-hub-s" style="text-anchor:start">${m.grand} cases · ${m.feats.length} features</text>
    ${mmStatBar(COL.root + 16, rootY + 18, 154, { total: m.grand, counts: m.totals })}</g>`;
  groups.forEach((g) => {
    const fx = COL.feat;
    if (multi) {
      out += edge(COL.root + 186, rootY, COL.repo, g.y, "", 2.4);
      const fc = g.feats.length;
      out += `<g class="mm-node" ${mmTip(`<b>${esc(g.repo)}</b><br>${fc} feature${fc === 1 ? "" : "s"} reviewed against this repository`)}>
        <rect x="${COL.repo}" y="${g.y - 19}" width="188" height="38" rx="10" class="mm-card mm-card-repo" filter="url(#mmSh)"/>
        <circle cx="${COL.repo + 15}" cy="${g.y}" r="4" fill="${MM_C.repo}"/>
        <text x="${COL.repo + 27}" y="${g.y - 2}" class="mm-card-t" style="text-anchor:start">${esc(mmTrunc(g.repo.split("/").pop(), 22))}</text>
        <text x="${COL.repo + 27}" y="${g.y + 11}" class="mm-card-m" style="text-anchor:start">${fc} feature${fc === 1 ? "" : "s"}</text></g>`;
    }
    g.feats.forEach((it) => {
      const f = it.f,
        x0 = multi ? COL.repo + 188 : COL.root + 186,
        y0 = multi ? g.y : rootY;
      out += edge(
        x0,
        y0,
        fx,
        it.y,
        "",
        Math.max(1.6, Math.min(6, (f.total || 1) / 14)),
      );
      const sel = MM_SEL === f.i;
      out += `<g class="mm-node mm-feat${sel ? " sel" : ""}" data-mmfeat="${f.i}" ${mmFeatTip(f)}>
        <rect x="${fx}" y="${it.y - 21}" width="252" height="42" rx="11" class="mm-card" filter="url(#mmSh)"/>
        <text x="${fx + 13}" y="${it.y - 5}" class="mm-card-t" style="text-anchor:start">${esc(mmTrunc(f.label, 30))}</text>
        ${mmStatBar(fx + 13, it.y + 2, 140, f)}
        <text x="${fx + 161}" y="${it.y + 8}" class="mm-card-m" style="text-anchor:start">v${f.version} · ${f.total || f.case_count}c · ${mmPct(f.counts.covered || 0, f.total || 1)}%</text>
        <text x="${fx + 239}" y="${it.y - 5}" class="mm-chev">${sel ? "▾" : "▸"}</text></g>`;
      it.kids.forEach((k) => {
        out += edge(
          fx + 252,
          it.y,
          COL.leaf,
          k.y,
          k.kind === "bucket" ? k.k : k.kind === "case" ? k.c.status : "",
          k.kind === "bucket" ? Math.max(1.6, Math.min(8, k.v / 5)) : 1.6,
        );
        if (k.kind === "bucket") {
          out += `<g class="mm-node mm-clu" data-mmbucket="${f.i}:${k.k}" ${mmTip(`<b>${k.v} ${k.k}</b> case${k.v === 1 ? "" : "s"}<br>in ${esc(mmTrunc(f.label, 34))}<br><i>click to open</i>`)}>
            <rect x="${COL.leaf}" y="${k.y - 11}" width="150" height="22" rx="11" fill="${MM_C[k.k]}" fill-opacity=".14" stroke="${MM_C[k.k]}" stroke-opacity=".7"/>
            <text x="${COL.leaf + 13}" y="${k.y + 4}" class="mm-pill-n" fill="${MM_C[k.k]}">${k.v}</text>
            <text x="${COL.leaf + 40}" y="${k.y + 4}" class="mm-pill-l">${k.k}</text></g>`;
        } else if (k.kind === "case") {
          out += `<g class="mm-node" ${mmCaseTip(k.c)}>
            <circle cx="${COL.leaf + 8}" cy="${k.y}" r="6" fill="${MM_C[k.c.status]}" class="mm-leaf"/>
            <text x="${COL.leaf + 22}" y="${k.y + 4}" class="mm-leaf-t">${esc(mmTrunc(k.c.title, 46))}</text>
            ${(k.c.files || []).length ? `<text x="${COL.leaf + 22}" y="${k.y + 4}" class="mm-leaf-ev" dx="${Math.min(300, mmTrunc(k.c.title, 46).length * 6.1) + 12}">${esc(mmTrunc((k.c.files[0] || "").split("/").pop(), 22))}</text>` : ""}</g>`;
        } else if (k.kind === "more") {
          out += `<text x="${COL.leaf + 22}" y="${k.y + 4}" class="mm-leaf-more">+${k.n} more — filter by status or see the list below</text>`;
        } else if (k.kind === "none") {
          out += `<text x="${COL.leaf + 22}" y="${k.y + 4}" class="mm-leaf-more">no ${esc(MM_FILTER || "")} cases</text>`;
        } else {
          out += `<g class="mm-node" ${mmTip(`${esc(f.label)}<br>${f.case_count} cases · not analyzed`)}>
            <rect x="${COL.leaf}" y="${k.y - 11}" width="150" height="22" rx="11" class="mm-clu-empty"/>
            <text x="${COL.leaf + 13}" y="${k.y + 4}" class="mm-pill-l">not analyzed</text></g>`;
        }
      });
    });
  });
  return mmStage(out, W, H, true);
}
// ---- chrome ---------------------------------------------------------------
function mmSummary(m) {
  const pct = mmPct(m.totals.covered, m.grand);
  if (!m.grand)
    return `<span class="mm-sum-x">Not analyzed yet — run <b>Analyze codebase</b> to build the map.</span>`;
  return `<span class="mm-sum-hero">${pct}%</span><span class="mm-sum-l">implemented</span><span class="mm-sum-sep"></span>
    <span class="mm-sum-i"><b>${m.grand}</b> cases judged</span>
    <span class="mm-sum-i cov"><b>${m.totals.covered}</b> covered</span>
    <span class="mm-sum-i par"><b>${m.totals.partial}</b> partial</span>
    <span class="mm-sum-i unc"><b>${m.totals.uncovered}</b> uncovered</span>
    <span class="mm-sum-i"><b>${m.feats.length}</b> features</span>
    <span class="mm-sum-i"><b>${m.repos.length}</b> repo${m.repos.length === 1 ? "" : "s"}</span>`;
}
function mmDetail(m) {
  if (MM_SEL == null) {
    if (!m.evidence.length) return "";
    const top = m.evidence.slice(0, 6),
      max = top[0].cases || 1;
    return `<div class="mm-hot"><div class="mm-hot-head">Evidence hotspots <span class="muted">— files cited most often as implementing a case; the riskiest places to change</span></div>
      ${top
        .map(
          (
            e,
          ) => `<div class="mm-hot-row" ${mmTip(`<b>${esc(e.file)}</b><br>${e.cases} case${e.cases === 1 ? "" : "s"} · ${e.feats} feature${e.feats === 1 ? "" : "s"}`)}>
        <span class="mm-hot-file"><code>${esc(mmTrunc(e.file, 50))}</code></span>
        <span class="mm-hot-bar"><i style="width:${Math.max(4, (e.cases / max) * 100)}%"></i></span>
        <span class="mm-hot-n">${e.cases} case${e.cases === 1 ? "" : "s"}</span></div>`,
        )
        .join("")}</div>`;
  }
  const f = m.feats.find((x) => x.i === MM_SEL);
  if (!f) return "";
  const shown = MM_FILTER
    ? f.cases.filter((c) => c.status === MM_FILTER)
    : f.cases;
  const chip = (k) =>
    `<button type="button" class="mm-chip ${k} ${MM_FILTER === k ? "on" : ""}" data-mmfilter="${k}">${f.counts[k] || 0} ${k}</button>`;
  return `<div class="mm-detail-head">
      <div><div class="mm-detail-title">${esc(f.label)} <span class="pill">v${f.version}</span></div>
      <div class="mm-detail-sub">${f.files.length} file${f.files.length === 1 ? "" : "s"} reviewed${f.repos.length ? " · " + esc(f.repos.join(", ")) : ""}</div></div>
      <div class="mm-chip-row">${MM_ST.map(chip).join("")}<button type="button" class="mm-chip ${MM_FILTER ? "" : "on"}" data-mmfilter="">all</button></div></div>
    <div class="mm-case-list">${
      shown
        .slice(0, 60)
        .map(
          (c) => `<div class="mm-case">
      <div class="mm-case-h"><span class="mm-sdot ${c.status}"></span><b>${esc(c.title)}</b>
        <span class="mm-case-tags">${c.display_id ? `<code>${esc(c.display_id)}</code>` : ""}<span class="badge ${c.type}">${esc(typeLabel(c.type || ""))}</span><span class="badge mm-${c.status}">${c.status}</span></span></div>
      ${c.rationale ? `<div class="mm-case-why">${esc(c.rationale)}</div>` : ""}
      ${
        (c.files || []).length
          ? `<div class="mm-case-ev"><span>evidence</span>${c.files.map((x) => `<code>${esc(x)}</code>`).join("")}</div>`
          : `<div class="mm-case-ev none"><span>no implementing file was found in the indexed source</span></div>`
      }</div>`,
        )
        .join("") ||
      `<div class="mm-detail-empty">No ${esc(MM_FILTER || "")} cases here.</div>`
    }</div>`;
}
function renderMmGraph() {
  const el = $("#mm-graph");
  if (!el) return;
  const sm = $("#mm-summary"),
    lg = $("#mm-legend"),
    cb = $("#mm-crumb"),
    det = $("#mm-detail");
  if (!MM_DATA || !(MM_DATA.features || []).length) {
    el.innerHTML = `<div class="mm-empty">No features in this project yet — add a feature, then run <b>Analyze codebase</b>.</div>`;
    if (sm) sm.innerHTML = "";
    if (det) det.innerHTML = "";
    if (cb) cb.innerHTML = "";
    return;
  }
  const m = mmModel(MM_DATA),
    mode = mmLayout(m);
  if (sm) sm.innerHTML = mmSummary(m);
  if (lg)
    lg.innerHTML =
      MM_ST.map(
        (k) =>
          `<span class="mm-lg"><i style="background:${MM_C[k]}"></i>${k}</span>`,
      ).join("") +
      `<span class="mm-lg-hint">${mode === "tree" ? "grouped by repository · click a feature to expand its cases" : "node size = cases · click a branch to expand"}</span>`;
  if (cb) {
    const f = MM_SEL != null ? m.feats.find((x) => x.i === MM_SEL) : null;
    cb.innerHTML =
      (f
        ? `<button type="button" class="mm-crumb-btn" id="mm-crumb-root">All features</button> ▸ <b>${esc(mmTrunc(f.label, 26))}</b>${MM_FILTER ? ` ▸ <b>${esc(MM_FILTER)}</b>` : ""}　`
        : "") +
      `<span class="mm-mode">${["auto", "radial", "tree"].map((x) => `<button type="button" class="mm-mode-b${MM_MODE === x ? " on" : ""}" data-mmmode="${x}" title="${x === "auto" ? "pick the clearest layout automatically" : x === "radial" ? "radial map (best for small projects)" : "tree (best for many repos/features)"}">${x}</button>`).join("")}</span>`;
  }
  el.innerHTML = mmMap(m);
  if (det) det.innerHTML = mmDetail(m);
}
function mmZoom(d) {
  MM_K = Math.min(2.2, Math.max(0.5, MM_K * d));
  const g = $("#mm-graph") && $("#mm-graph").querySelector("#mm-zoom");
  if (g)
    g.setAttribute(
      "transform",
      g.getAttribute("transform").replace(/scale\([^)]*\)/, `scale(${MM_K})`),
    );
}
if ($("#mm-zoom-in")) $("#mm-zoom-in").onclick = () => mmZoom(1.18);
if ($("#mm-zoom-out")) $("#mm-zoom-out").onclick = () => mmZoom(0.85);
if ($("#mm-reset"))
  $("#mm-reset").onclick = () => {
    MM_K = 1;
    MM_SEL = null;
    MM_FILTER = null;
    renderMmGraph();
  };
document.addEventListener("click", (e) => {
  if (!e.target.closest("#mm-graph-card")) return;
  const md = e.target.closest("[data-mmmode]");
  if (md) {
    MM_MODE = md.dataset.mmmode;
    MM_K = 1;
    renderMmGraph();
    return;
  }
  if (e.target.closest("#mm-crumb-root") || e.target.closest(".mm-hub-back")) {
    MM_SEL = null;
    MM_FILTER = null;
    MM_K = 1;
    renderMmGraph();
    return;
  }
  const b = e.target.closest("[data-mmbucket]");
  if (b) {
    const [i, st] = b.dataset.mmbucket.split(":");
    MM_SEL = +i;
    MM_FILTER = st;
    MM_K = 1;
    renderMmGraph();
    return;
  }
  const f = e.target.closest("[data-mmfeat]");
  if (f) {
    const i = +f.dataset.mmfeat;
    MM_SEL = MM_SEL === i ? null : i;
    MM_FILTER = null;
    MM_K = 1;
    renderMmGraph();
    return;
  }
  const fl = e.target.closest("[data-mmfilter]");
  if (fl) {
    MM_FILTER = fl.dataset.mmfilter || null;
    renderMmGraph();
  }
});
document.addEventListener("mouseover", (e) => {
  const host = e.target.closest("#mm-graph-card"),
    tip = $("#mm-graph-tip");
  if (!host || !tip) return;
  const t = e.target.closest("[data-tip]");
  if (!t) {
    tip.hidden = true;
    return;
  }
  tip.innerHTML = t.getAttribute("data-tip");
  tip.hidden = false;
  const b = host.getBoundingClientRect();
  tip.style.left =
    Math.min(Math.max(8, e.clientX - b.left + 14), Math.max(8, b.width - 262)) +
    "px";
  tip.style.top = Math.max(6, e.clientY - b.top - 8) + "px";
});
document.addEventListener("mouseout", (e) => {
  if (e.target.closest("#mm-graph-card")) {
    const t = $("#mm-graph-tip");
    if (t) t.hidden = true;
  }
});

window.syncJira = async (fid) => {
  try {
    const r = await api(`/api/features/${fid}/jira-sync`, { method: "POST" });
    toast("Posted coverage to Jira " + r.issue);
  } catch (e) {
    toast(e.message, true);
  }
};

// ---- Start Developing ----
async function initDevelop() {
  if (!$("#dev-proj")) return;
  await loadProjects();
  await loadDevFR();
}
if ($("#dev-proj")) {
  $("#dev-proj").onchange = () => {
    currentProject = $("#dev-proj").value;
    loadDevFR();
  };
}
async function loadDevFR() {
  if (!$("#dev-proj")) return;
  const pid = $("#dev-proj").value || currentProject;
  if (!pid) return;
  try {
    const f = await api("/api/features?project_id=" + pid);
    $("#dev-feat").innerHTML =
      f.features
        .map(
          (x) =>
            `<option value="${x.id}">${esc(x.name)} (v${x.version || 1})</option>`,
        )
        .join("") || `<option value="">no features</option>`;
  } catch (e) {}
  try {
    const r = await api(`/api/projects/${pid}/repos?repo_type=app`);
    $("#dev-repo").innerHTML =
      r.repos
        .map((x) => `<option value="${x.id}">${esc(x.full_name)}</option>`)
        .join("") || `<option value="">no implementation repos</option>`;
  } catch (e) {}
}
if ($("#dev-go")) {
  $("#dev-go").onclick = async () => {
    const fid = $("#dev-feat").value,
      rid = $("#dev-repo").value;
    if (!fid || !rid) {
      toast("Pick a feature and a repo", true);
      return;
    }
    $("#dev-go").disabled = true;
    $("#dev-out").innerHTML = "";
    $("#dev-status").textContent = "starting…";
    try {
      const r = await api("/api/develop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feature_id: fid,
          repo_id: rid,
          base_branch: $("#dev-base").value.trim() || "main",
          language: $("#dev-lang").value,
        }),
      });
      $("#dev-status").innerHTML =
        "Running in the background — track it in <b>Jobs</b>, or watch here:";
      watchDev(r.job_id);
    } catch (e) {
      $("#dev-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
      $("#dev-go").disabled = false;
    }
  };
}
function watchDev(jobId) {
  if (!jobId) {
    if ($("#dev-go")) $("#dev-go").disabled = false;
    return;
  }
  watchJob(jobId, (j) => {
    const d = j.result || {};
    if ($("#dev-status"))
      $("#dev-status").textContent =
        j.status === "running"
          ? `${esc(j.stage)}…`
          : j.status === "failed"
            ? ""
            : "Done";
    if (j.status === "running") return;
    if ($("#dev-go")) $("#dev-go").disabled = false;
    if (j.status === "failed") {
      if ($("#dev-out"))
        $("#dev-out").innerHTML =
          `<div class="err">failed: ${esc(j.error || "")}</div>`;
      return;
    }
    if ($("#dev-out"))
      $("#dev-out").innerHTML =
        `<div class="explain" style="margin-top:10px">Opened <a href="${esc(d.pr_url)}" target="_blank" rel="noopener noreferrer">PR #${d.pr_number}</a> on branch <code>${esc(d.branch)}</code> — ${d.file_count} implementation file(s) built to satisfy ${d.cases} test cases.<br>${(d.files || []).map((f) => `<code>${esc(f)}</code>`).join(" · ")}<br><button class="go" style="margin-top:8px" onclick="analyzeDevPR('${d.repo_id}',${d.pr_number})">Analyze this PR for coverage</button></div>`;
  });
}
window.analyzeDevPR = async (rid, num) => {
  if (currentFeature) {
    await openFeature(currentFeature);
    navigateTo("gap");
  } else {
    navigateTo("features");
  }
};

// ---- regenerate feature ----
$("#d-regen").onclick = async () => {
  if (!currentFeature) return;
  const btn = $("#d-regen");
  btn.disabled = true;
  btn.textContent = "↻ starting…";
  try {
    const r = await api(`/api/features/${currentFeature}/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    toast("Regeneration started — live progress is shown below");
    watchFeatureGen(r.job_id, currentFeature);
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "↻ regenerate";
  }
};

// ---- Jobs screen ----
let jobsTimer = null;
function initJobs() {
  if (!document.getElementById("view-jobs")) return;
  loadJobsList();
  clearInterval(jobsTimer);
  jobsTimer = setInterval(() => {
    if (
      document.getElementById("view-jobs") &&
      !document.getElementById("view-jobs").hidden
    )
      loadJobsList();
    else clearInterval(jobsTimer);
  }, 3000);
}
if ($("#jobs-refresh")) $("#jobs-refresh").onclick = loadJobsList;
async function loadJobsList() {
  if (!$("#jobs-list")) return;
  try {
    const r = await api("/api/jobs?limit=80");
    const badge = (s) =>
      ({
        running:
          '<span class="badge" style="color:var(--accent2)">running</span>',
        succeeded: '<span class="badge new">succeeded</span>',
        failed: '<span class="badge" style="color:var(--red)">failed</span>',
      })[s] || `<span class="badge">${esc(s)}</span>`;
    $("#jobs-list").innerHTML = r.jobs.length
      ? `<table><tr><th>Type</th><th>Label</th><th>Status</th><th>Stage / error</th><th>When</th><th></th></tr>` +
        r.jobs
          .map(
            (
              j,
            ) => `<tr><td><span class="badge">${esc(j.type)}</span></td><td>${esc(j.label || "")}</td><td>${badge(j.status)}</td>
        <td class="muted">${esc(j.status === "failed" ? j.error || "" : j.stage || "")}</td>
        <td class="muted">${j.created_at ? new Date(j.created_at * 1000).toLocaleString() : ""}</td>
        <td>${j.status !== "running" ? `<button class="ghost" onclick="retryJob('${j.id}')">retry</button>` : ""}</td></tr>`,
          )
          .join("") +
        `</table>`
      : `<span class="muted">no jobs yet</span>`;
  } catch (e) {
    $("#jobs-list").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}
window.retryJob = async (id) => {
  try {
    await api(`/api/jobs/${id}/retry`, { method: "POST" });
    toast("Retry started");
    loadJobsList();
  } catch (e) {
    toast(e.message, true);
  }
};

