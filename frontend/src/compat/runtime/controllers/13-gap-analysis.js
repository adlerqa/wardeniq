// ---- Gap Analysis ----
let GAP_TAB = "pr";
let GAP_AUTO_POLL = null;

async function initGap() {
  if (!currentFeature) {
    $("#gap-no-feature").style.display = "block";
    $("#gap-workspace").style.display = "none";
    return;
  }
  // Reset any run-detail panel left over from a previously-viewed feature. It is
  // otherwise only cleared by its own Close button, so without this it leaks across
  // features (e.g. a Loan_2 PR run staying visible under Catalog_2's gap view).
  $("#gap-pr-detail").style.display = "none";
  $("#gap-pr-detail-body").innerHTML = "";
  $("#gap-no-feature").style.display = "none";
  $("#gap-workspace").style.display = "block";
  $("#gap-feat-title").textContent =
    `${$("#d-name").textContent || "Feature"} — Gap Analysis`;
  const _gx = (id, kind, fmt) => {
    const a = $(id);
    if (a)
      a.onclick = (e) => {
        e.preventDefault();
        downloadGapExport(kind, fmt)
          .then(() => toast("Export ready"))
          .catch((err) => toast(err.message || "Export failed", true));
      };
  };
  _gx("#gap-pr-export-csv", "pr-coverage", "csv");
  _gx("#gap-pr-export-pdf", "pr-coverage", "pdf");
  _gx("#gap-auto-export-csv", "automation", "csv");
  _gx("#gap-auto-export-pdf", "automation", "pdf");
  switchGapTab(GAP_TAB);
}

function switchGapTab(tab) {
  GAP_TAB = tab;
  // Stop any running pollers before switching so they don't leak across tabs.
  stopGapPrPoll();
  if (GAP_AUTO_POLL) {
    clearTimeout(GAP_AUTO_POLL);
    GAP_AUTO_POLL = null;
  }
  document
    .querySelectorAll("[data-gap-tab]")
    .forEach((b) => b.classList.toggle("active", b.dataset.gapTab === tab));
  $("#gap-tab-pr").style.display = tab === "pr" ? "block" : "none";
  $("#gap-tab-auto").style.display = tab === "auto" ? "block" : "none";
  if (tab === "pr") loadGapPrRuns();
  else loadGapAuto();
}

document.querySelectorAll("[data-gap-tab]").forEach((btn) => {
  btn.onclick = () => switchGapTab(btn.dataset.gapTab);
});

let GAP_PR_POLL = null;
function stopGapPrPoll() {
  if (GAP_PR_POLL) {
    clearTimeout(GAP_PR_POLL);
    GAP_PR_POLL = null;
  }
}

// Re-schedule the PR-runs poller. Fast cadence while a run is active (so the
// RUNNING→DONE flip shows without manual refresh); slow idle cadence so a newly
// raised PR appears on its own. Only runs while the PR tab is actually visible.
function _scheduleGapPrPoll(anyActive) {
  stopGapPrPoll();
  if (
    GAP_TAB !== "pr" ||
    $("#gap-workspace").style.display === "none" ||
    !currentFeature
  )
    return;
  GAP_PR_POLL = setTimeout(
    () => loadGapPrRuns({ silent: true }),
    anyActive ? 2000 : 4000,
  );
}

async function loadGapPrRuns(opts) {
  const silent = !!(opts && opts.silent === true);
  if (!currentFeature) return;
  if (!silent)
    skIn(
      "#gap-pr-list",
      skeleton.rows(4, "Loading pull request coverage runs"),
    );
  try {
    const r = await api(
      `/api/features/${currentFeature}/code-coverage/runs?limit=50`,
    );
    const runs = r.runs || [];
    const anyActive = runs.some(
      (run) => run.status === "running" || run.status === "pending",
    );
    const live = $("#gap-pr-live");
    if (live)
      live.innerHTML = anyActive
        ? '<span class="badge functional">⏳ gap analysis running…</span>'
        : "";
    if (!runs.length) {
      $("#gap-pr-list").innerHTML =
        `<div class="muted">No PR coverage runs yet. Waiting for a PR… (updates automatically)</div>`;
      _scheduleGapPrPoll(false);
      return;
    }
    $("#gap-pr-list").innerHTML = runs
      .map((run) => {
        const statusBadge =
          {
            done: '<span class="badge api">DONE</span>',
            running: '<span class="badge functional">RUNNING</span>',
            pending: '<span class="badge">PENDING</span>',
            failed:
              '<span class="badge nfr" style="color:var(--red)">FAILED</span>',
          }[run.status] ||
          `<span class="badge">${esc(run.status || "")}</span>`;
        const total = run.tests_total ?? 0;
        const covered = run.tests_covered ?? 0;
        // Partial = PR touches relevant code but the implementation was not confirmed.
        // It is shown here but is not part of `covered` or the percentage (#291).
        const partial = run.tests_partial ?? 0;
        const pct = total ? Math.round((100 * covered) / total) : 0;
        const ts = run.completed_at || run.created_at;
        const when = ts ? new Date(ts * 1000).toLocaleString() : "";
        const prTitle = esc(run.pr_title || `PR #${run.pr_number}`);
        const rerunBadge = run.needs_rerun
          ? '<span class="badge nfr" style="color:var(--amber)">NEEDS RERUN</span>'
          : "";
        const excluded = !!run.excluded;
        const exclBadge = excluded
          ? '<span class="badge" style="background:#3a2a20;color:var(--amber)">EXCLUDED</span>'
          : "";
        const exclBtn = run.pr_id
          ? `<button class="ghost needs-editor" type="button" title="${excluded ? "Count this PR in coverage again" : "Ignore this PR in coverage"}" style="font-size:11px;padding:3px 9px;margin-top:5px" onclick="event.stopPropagation();togglePrExcluded('${run.pr_id}',${excluded ? "false" : "true"})">${excluded ? "Include" : "Exclude"}</button>`
          : "";
        return `<div class="repo-item-card" style="cursor:pointer${excluded ? ";opacity:.55" : ""}" onclick="openGapPrRun('${run.id}')">
        <div style="flex:1">
          <div><b>#${run.pr_number}</b> · ${prTitle} ${statusBadge} ${rerunBadge} ${exclBadge}</div>
          <div class="muted" style="font-size:11px;margin-top:3px">${esc(run.repo_full_name || "")} · branch <b>${esc(run.pr_branch || "")}</b> · ${esc(when)}</div>
        </div>
        <div style="text-align:right">
          <div><b>${covered}/${total}</b> covered</div>
          <div class="muted" style="font-size:11px">${pct}%${partial ? ` · ${partial} partial, not counted` : ""} · ${run.source || "webhook"}</div>
          ${exclBtn}
        </div>
      </div>`;
      })
      .join("");
    _scheduleGapPrPoll(anyActive);
  } catch (e) {
    if (!silent)
      $("#gap-pr-list").innerHTML = `<div class="err">${esc(e.message)}</div>`;
    _scheduleGapPrPoll(false); // keep retrying slowly on transient errors
  }
}

window.togglePrExcluded = async (prId, excluded) => {
  if (!prId) {
    toast("PR id unavailable for this run", true);
    return;
  }
  try {
    await api(`/api/prs/${prId}/exclude`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ excluded }),
    });
    toast(excluded ? "PR excluded from coverage" : "PR included in coverage");
    loadGapPrRuns();
    // Refresh the feature's coverage card so the % reflects the change.
    if (currentFeature && typeof loadCoverage === "function")
      loadCoverage(currentFeature);
  } catch (e) {
    toast(e.message || "Could not update PR", true);
  }
};

window.toggleCovMode = (btn, section, mode) => {
  const container = btn.closest(".case-group-body");
  if (!container) return;

  // Update buttons active style
  container.querySelectorAll(".cov-toggle-btn").forEach((b) => {
    b.style.background = "transparent";
    b.style.color = "var(--muted)";
  });
  btn.style.background = "#35507a";
  btn.style.color = "#d5e5ff";

  // Show/hide lists
  const covList = container.querySelector(`.cov-list-covered-${section}`);
  const missList = container.querySelector(`.cov-list-missing-${section}`);
  const badge = container.querySelector(`.cov-status-badge`);

  const covCount = covList ? covList.dataset.count : 0;
  const missCount = missList ? missList.dataset.count : 0;

  if (mode === "covered") {
    if (covList) covList.style.display = "block";
    if (missList) missList.style.display = "none";
    if (badge) {
      badge.textContent = `${covCount} covered`;
      badge.style.background = "rgba(52,211,153,0.15)";
      badge.style.color = "#34d399";
      badge.style.borderColor = "rgba(52,211,153,0.2)";
    }
  } else {
    if (covList) covList.style.display = "none";
    if (missList) missList.style.display = "block";
    if (badge) {
      badge.textContent = `${missCount} missing`;
      badge.style.background = "rgba(244,113,113,0.15)";
      badge.style.color = "#f87171";
      badge.style.borderColor = "rgba(244,113,113,0.2)";
    }
  }
};

window.openGapPrRun = async (rid) => {
  $("#gap-pr-detail").style.display = "block";
  $("#gap-pr-detail-body").innerHTML = skeleton.block(
    "Loading coverage run details",
  );
  try {
    const r = await api(`/api/code-coverage/runs/${rid}`);
    // Guard: never render a run whose feature differs from the one being viewed.
    if (r.feature_id && currentFeature && r.feature_id !== currentFeature) {
      $("#gap-pr-detail").style.display = "none";
      $("#gap-pr-detail-body").innerHTML = "";
      return;
    }
    $("#gap-pr-detail-title").textContent =
      `Run · PR #${r.pr_number} · ${r.repo_full_name || ""}`;

    const result = r.result || {};
    const covered = result.covered || [];
    const cmp = result.comparison || {};
    const newlySet = new Set(cmp.newly_covered || []);
    const lostSet = new Set(cmp.no_longer_covered || []);

    // An entry saved before `status` existed was full coverage; "partial" was never
    // confirmed, so it is shown as a gap with a note instead of as covered (#291).
    const isConfirmed = (c) => (c.status ?? "covered") === "covered";

    // Group feature test cases
    const coveredById = {};
    for (const c of covered) coveredById[c.test_case_id] = c;
    const allCases = r.feature_cases || [];
    const sections = {};
    for (const c of allCases) {
      const t = (c.type || "other").toLowerCase();
      sections[t] = sections[t] || { covered: [], missing: [] };
      const ev = coveredById[c.id];
      if (ev && isConfirmed(ev))
        sections[t].covered.push({
          ...c,
          rationale: ev.rationale,
          by_dev_test: !!ev.by_dev_test,
        });
      else if (ev)
        sections[t].missing.push({ ...c, partial: true, rationale: ev.rationale });
      else sections[t].missing.push(c);
    }

    const TYPE_TITLES = {
      functional: "Business tests",
      e2e: "End-to-End",
      api: "API tests",
      ui: "UI validations",
      nfr: "Edge cases",
      other: "Other tests",
    };
    const TYPE_ORDER = ["functional", "e2e", "api", "ui", "nfr", "other"];

    const headerLinks = [];

    if (r.pr_url) {
      headerLinks.push(`
    <a
      class="run-link-btn run-link-primary"
      target="_blank"
      rel="noopener"
      href="${esc(r.pr_url)}"
      title="Open pull request"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 3v12"></path>
        <circle cx="7" cy="18" r="2"></circle>
        <circle cx="7" cy="5" r="2"></circle>

        <path d="M17 6h4v4"></path>
        <path d="m21 6-6 6"></path>
      </svg>

      <span>Open PR</span>
    </a>
  `);
    }

    if (r.commit_url) {
      headerLinks.push(`
    <a
      class="run-link-btn run-link-secondary"
      target="_blank"
      rel="noopener"
      href="${esc(r.commit_url)}"
      title="View commit"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M3 12h6"></path>
        <path d="M15 12h6"></path>
      </svg>

      <span>View commit</span>

      <svg
        class="run-link-external"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path d="M14 5h5v5"></path>
        <path d="M19 5l-8 8"></path>
        <path d="M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"></path>
      </svg>
    </a>
  `);
    }
    if (r.head_sha)
      headerLinks.push(
        `<span class="muted" style="font-size:11px">SHA <code>${esc(r.head_sha.slice(0, 7))}</code></span>`,
      );
    if (r.feature_name)
      headerLinks.push(
        `<span class="muted" style="font-size:11px">Feature: <b>${esc(r.feature_name)}</b></span>`,
      );
    headerLinks.push(
      `<button class="ghost" type="button" onclick="reassignGapRun('${r.id}')">Reassign feature…</button>`,
    );
    if (r.needs_rerun)
      headerLinks.push(
        '<span class="badge nfr" style="color:var(--amber)">feature edited after run — rerun recommended</span>',
      );

    const total = allCases.length || (r.tests_total ?? 0);
    const cov = covered.filter(isConfirmed).length;
    const partialCount = covered.filter((c) => c.status === "partial").length;
    const gaps = Math.max(0, total - cov);
    const newlyCount = cmp.newly_covered_detail
      ? cmp.newly_covered_detail.length
      : (cmp.newly_covered || []).length;

    const legendHtml = `
      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:16px;border:1px solid #0e1f35;background:#07111f;border-radius:12px;padding:12px 16px;margin-bottom:14px;font-size:12px;color:#a0aec0">
        <div style="display:flex;align-items:center;gap:6px">
          <span style="color:#34d399;font-weight:bold;font-size:14px">↑</span>
          <span><b>Upstream</b> means the testcase is newly covered in this run.</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <span style="color:#f87171;font-weight:bold;font-size:14px">↓</span>
          <span><b>Downstream</b> means the testcase was covered before and is now missing.</span>
        </div>
      </div>
    `;

    const sectionsHtml = TYPE_ORDER.filter((t) => sections[t])
      .map((t) => {
        const sec = sections[t];
        const secTotal = sec.covered.length + sec.missing.length;
        const secPartial = sec.missing.filter((c) => c.partial).length;
        const defaultMode = sec.covered.length ? "covered" : "missing";
        const isCovActive = defaultMode === "covered";

        const badgeText = isCovActive
          ? `${sec.covered.length} covered`
          : `${sec.missing.length} missing`;
        const badgeBg = isCovActive
          ? "rgba(52,211,153,0.15)"
          : "rgba(244,113,113,0.15)";
        const badgeColor = isCovActive ? "#34d399" : "#f87171";
        const badgeBorder = isCovActive
          ? "rgba(52,211,153,0.2)"
          : "rgba(244,113,113,0.2)";

        const renderItem = (c, mode) => {
          let arrowHtml = "";
          if (mode === "covered" && newlySet.has(c.id)) {
            arrowHtml = `<span style="color:#34d399;font-weight:bold;font-size:14px;margin-right:2px" title="Newly covered in this run">↑</span>`;
          } else if (mode === "missing" && lostSet.has(c.id)) {
            arrowHtml = `<span style="color:#f87171;font-weight:bold;font-size:14px;margin-right:2px" title="No longer covered in this run">↓</span>`;
          }

          const displayCodeHtml = c.display_id
            ? `<code style="font-family:monospace;font-size:10px;background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px;color:#94a3b8">${esc(c.display_id)}</code>`
            : "";

          const prioBadgeHtml = prioBadge(c.priority);

          let commitBadgeHtml = "";
          if (r.head_sha) {
            const shortSha = r.head_sha.slice(0, 7);
            if (r.commit_url) {
              commitBadgeHtml = `<a href="${esc(r.commit_url)}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:3px;font-family:monospace;font-size:10px;background:rgba(59,130,246,0.1);color:#60a5fa;border:1px solid rgba(59,130,246,0.2);padding:2px 6px;border-radius:4px;text-decoration:none">${esc(shortSha)} ↗</a>`;
            } else {
              commitBadgeHtml = `<span style="font-family:monospace;font-size:10px;background:rgba(255,255,255,0.06);color:#94a3b8;padding:2px 6px;border-radius:4px">${esc(shortSha)}</span>`;
            }
          }

          const featureBadgeHtml = r.feature_name
            ? `<span style="font-size:10.5px;background:rgba(51, 65, 85, 0.4);color:#94a3b8;padding:2px 8px;border-radius:4px">${esc(r.feature_name)}</span>`
            : "";

          return `
          <div style="border:1px solid #1E2A40;background:#0D1728;border-radius:10px;padding:12px 14px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px">
              <div style="display:flex;align-items:center;gap:6px">
                ${arrowHtml}
                ${displayCodeHtml}
              </div>
              ${prioBadgeHtml}
            </div>
            <div style="font-size:13.5px;font-weight:500;color:#e2e8f0;line-height:1.4;margin-bottom:8px">${esc(c.title)}</div>
            ${c.partial ? `<div style="font-size:11.5px;color:var(--amber);margin-bottom:8px">⚠ Partial match, not confirmed${c.rationale ? ` — ${esc(c.rationale)}` : ""}</div>` : ""}
            ${stepsHtml(c.steps)}
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              ${commitBadgeHtml}
              ${featureBadgeHtml}
            </div>
          </div>
        `;
        };

        return `<details class="case-group gap-section" ${sec.covered.length > 0 ? "open" : ""}>
        <summary style="color:var(--text);font-size:13px;text-transform:none;letter-spacing:normal;font-weight:600">
          <div style="display:flex;align-items:center;gap:8px">
            <span>${esc(TYPE_TITLES[t] || t.toUpperCase())}</span>
            <span class="badge" style="border-radius:999px;background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--muted);padding:2px 7px;font-size:10px">${sec.covered.length} covered · ${sec.missing.length} missing${secPartial ? ` (${secPartial} partial)` : ""}</span>
          </div>
        </summary>
        <div class="case-group-body" style="padding:10px 14px 14px">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px">
            <div class="inline-flex" style="display:inline-flex;background:#0d1728;border:1px solid #28405f;border-radius:999px;padding:2px">
              <button type="button" class="cov-toggle-btn" onclick="toggleCovMode(this, '${t}', 'covered')" style="background:${isCovActive ? "#35507a" : "transparent"};color:${isCovActive ? "#d5e5ff" : "var(--muted)"};border:none;border-radius:999px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;transition:all 0.15s">Covered</button>
              <button type="button" class="cov-toggle-btn" onclick="toggleCovMode(this, '${t}', 'missing')" style="background:${!isCovActive ? "#35507a" : "transparent"};color:${!isCovActive ? "#d5e5ff" : "var(--muted)"};border:none;border-radius:999px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;transition:all 0.15s">Missing</button>
            </div>
            <span class="cov-status-badge" style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:999px;background:${badgeBg};color:${badgeColor};border:1px solid ${badgeBorder};transition:all 0.15s">
              ${badgeText}
            </span>
          </div>
          
          <div class="cov-list-covered-${t}" data-count="${sec.covered.length}" style="display:${isCovActive ? "block" : "none"}">
            ${sec.covered.length ? sec.covered.map((c) => renderItem(c, "covered")).join("") : `<div class="muted" style="padding:8px 4px">No covered test cases.</div>`}
          </div>
          
          <div class="cov-list-missing-${t}" data-count="${sec.missing.length}" style="display:${!isCovActive ? "block" : "none"}">
            ${sec.missing.length ? sec.missing.map((c) => renderItem(c, "missing")).join("") : `<div class="muted" style="padding:8px 4px">No missing test cases.</div>`}
          </div>
        </div>
      </details>`;
      })
      .join("");

    $("#gap-pr-detail-body").innerHTML = `
      <div class="sub" style="margin:8px 0">${esc(r.pr_title || "")} · branch <b>${esc(r.pr_branch || "")}</b></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center">${headerLinks.join("")}</div>
      <div style="display:flex;gap:0;padding:14px 18px;background:var(--panel2);border:1px solid var(--line);border-radius:9px;margin-bottom:14px">
        <div style="flex:1;min-width:140px"><div style="font-size:18px;font-weight:700;line-height:1">${cov} / ${total}</div><div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:5px">Tests covered</div>${partialCount ? `<div class="muted" style="font-size:11px;margin-top:3px">+ ${partialCount} partial, not counted</div>` : ""}</div>
        <div style="flex:1;min-width:140px;border-left:1px solid var(--line);padding-left:18px"><div style="font-size:18px;font-weight:700;line-height:1">${newlyCount}</div><div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:5px">New tests found</div></div>
        <div style="flex:1;min-width:140px;border-left:1px solid var(--line);padding-left:18px"><div style="font-size:18px;font-weight:700;line-height:1">${gaps}</div><div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:5px">Gaps</div></div>
      </div>
      ${legendHtml}
      ${sectionsHtml || '<div class="muted">No test cases on this feature yet.</div>'}
    `;
  } catch (e) {
    $("#gap-pr-detail-body").innerHTML =
      `<div class="err">${esc(e.message)}</div>`;
  }
};

if ($("#gap-pr-detail-close"))
  $("#gap-pr-detail-close").onclick = () => {
    $("#gap-pr-detail").style.display = "none";
  };

window.reassignGapRun = async (runId) => {
  if (!currentProject) return;
  try {
    const r = await api(`/api/features?project_id=${currentProject}`);
    const features = r.features || [];
    if (!features.length) {
      toast("No features in this project", true);
      return;
    }
    const labels = features
      .map(
        (f, i) =>
          `${i + 1}. ${f.name}${f.version ? " (v" + f.version + ")" : ""}`,
      )
      .join("\n");
    const choice = await uiPrompt(
      "Reassign feature",
      `Pick a feature for this run by number:\n${labels}`,
      "1",
    );
    const idx = parseInt(choice || "0", 10) - 1;
    if (isNaN(idx) || idx < 0 || idx >= features.length) {
      toast("Invalid pick", true);
      return;
    }
    const fid = features[idx].id;
    await api(`/api/code-coverage/runs/${runId}/reassign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature_id: fid }),
    });
    toast(`Reassigning + re-running against ${features[idx].name}…`);
    setTimeout(loadGapPrRuns, 1500);
    $("#gap-pr-detail").style.display = "none";
  } catch (e) {
    toast(e.message, true);
  }
};
if ($("#gap-pr-refresh")) $("#gap-pr-refresh").onclick = () => loadGapPrRuns();

if ($("#gap-pr-manual"))
  $("#gap-pr-manual").onclick = async () => {
    if (!currentFeature || !currentProject) {
      toast("Open a feature first", true);
      return;
    }
    const choice = await uiPrompt(
      "Run PR coverage",
      "Paste a full PR/MR URL (github.com/.../pull/N or gitlab.com/.../merge_requests/N) — or just a PR number if you only have one App repo connected.",
      "",
    );
    if (!choice) return;
    const v = String(choice).trim();
    const body = { feature_id: currentFeature };
    if (/https?:\/\//i.test(v)) {
      body.pr_url = v;
    } else {
      // Number-only — fall back to the project's first App repo
      const repos = await api(`/api/projects/${currentProject}/repos`);
      const appRepos = (repos.repos || []).filter(
        (rp) => (rp.repo_type || "app") === "app",
      );
      if (!appRepos.length) {
        toast("No App repos connected on this project", true);
        return;
      }
      const pn = parseInt(v.replace(/[^0-9]/g, ""));
      if (!pn) {
        toast("Enter a numeric PR number or a full PR/MR URL", true);
        return;
      }
      body.repo_id = appRepos[0].id;
      body.pr_number = pn;
    }
    const btn = $("#gap-pr-manual");
    const origLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Starting…";
    $("#gap-pr-list").innerHTML =
      `<div class="muted">⏳ Starting coverage analysis…</div>`;
    let jobId = null;
    try {
      const r = await api("/api/code-coverage/runs/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      jobId = r.job_id;
      toast(
        `Coverage run started · ${r.repo_full_name || ""} #${r.pr_number || ""}`,
      );
    } catch (e) {
      toast(e.message, true);
      btn.disabled = false;
      btn.textContent = origLabel;
      $("#gap-pr-list").innerHTML = `<div class="err">${esc(e.message)}</div>`;
      return;
    }
    // Poll the job + refresh the run list periodically until terminal.
    const start = Date.now();
    async function poll() {
      try {
        const j = await api(`/api/jobs/${jobId}`);
        const stage = j.stage || "Working…";
        const progress = j.progress || 0;
        $("#gap-pr-list").innerHTML =
          `<div class="muted">⏳ ${esc(stage)} · ${progress}%</div>`;
        if (j.status === "succeeded" || j.status === "failed") {
          btn.disabled = false;
          btn.textContent = origLabel;
          if (j.status === "failed")
            toast(`Run failed: ${j.error || ""}`, true);
          loadGapPrRuns();
          return;
        }
      } catch (e) {
        /* keep polling on transient errors */
      }
      if (Date.now() - start > 10 * 60 * 1000) {
        // give up after 10 min
        btn.disabled = false;
        btn.textContent = origLabel;
        loadGapPrRuns();
        return;
      }
      setTimeout(poll, 1500);
    }
    poll();
  };

async function loadGapAuto() {
  if (!currentFeature) return;
  $("#gap-auto-stats").style.display = "none";
  skIn("#gap-auto-repos", skeleton.rows(4, "Loading automation repositories"));
  try {
    const r = await api(`/api/features/${currentFeature}/automation-coverage`);
    const repos = r.test_repos || [];
    if (!repos.length) {
      $("#gap-auto-repos").innerHTML =
        `<div class="muted">No <b>Test</b> repos connected on this project. Add one from the project detail page (type = Test).</div>`;
      $("#gap-auto-summary").textContent = "";
      return;
    }
    $("#gap-auto-repos").innerHTML = repos
      .map((rp) => {
        const status = rp.scan_status || "never";
        const last = rp.last_scan_at
          ? new Date(rp.last_scan_at * 1000).toLocaleString()
          : "never";
        const badge =
          {
            running: '<span class="badge functional">scanning…</span>',
            done: '<span class="badge api">scanned</span>',
            failed:
              '<span class="badge nfr" style="color:var(--red)">scan failed</span>',
            never: '<span class="badge">never scanned</span>',
          }[status] || `<span class="badge">${esc(status)}</span>`;
        const actionBtns =
          status === "running"
            ? `<button class="ghost" type="button" disabled>Scanning…</button>
           <button class="ghost" type="button" onclick="resetScanStatus('${rp.id}')" title="Force-clear a scan that's been stuck for too long" style="color:var(--amber)">Reset</button>`
            : `<button class="ghost" type="button" onclick="rescanTestRepo('${rp.id}')">Rescan</button>`;
        return `<div class="repo-item-card">
        <div style="flex:1">
          <div><b>${esc(rp.full_name)}</b> ${badge}</div>
          <div class="muted" style="font-size:11px;margin-top:3px">files: ${rp.scan_files_found || 0} · tests extracted: ${rp.scan_cases_count || 0} · last scan: ${esc(last)}${rp.scan_error ? ` · <span class="err">${esc(rp.scan_error)}</span>` : ""}</div>
        </div>
        <div style="display:flex;gap:6px">${actionBtns}</div>
      </div>`;
      })
      .join("");

    const haveScan = (r.total_generated || 0) > 0 && (r.items || []).length;
    if (!haveScan) {
      $("#gap-auto-summary").textContent = repos.length
        ? "Rescan a test repo to populate coverage."
        : "";
      return;
    }
    $("#gap-auto-stats").style.display = "block";
    $("#gap-auto-pct").textContent = (r.coverage_pct ?? 0) + "%";
    $("#gap-auto-covered").textContent = r.covered_count ?? 0;
    $("#gap-auto-missing").textContent = r.missing_count ?? 0;
    $("#gap-auto-total").textContent = r.total_generated ?? 0;
    $("#gap-auto-summary").textContent =
      `${r.covered_count}/${r.total_generated} covered · scanned ${r.scanned_repo_full_name || ""}`;
    const sections = {};
    for (const it of r.items || []) {
      const t = (it.generated_type || "other").toLowerCase();
      sections[t] = sections[t] || { covered: [], missing: [] };
      if (it.status === "covered") {
        sections[t].covered.push(it);
      } else {
        sections[t].missing.push(it);
      }
    }

    const TYPE_TITLES = {
      functional: "Business tests",
      e2e: "End-to-End",
      api: "API tests",
      ui: "UI validations",
      nfr: "Edge cases",
      other: "Other tests",
    };
    const TYPE_ORDER = ["functional", "e2e", "api", "ui", "nfr", "other"];

    $("#gap-auto-items").innerHTML = TYPE_ORDER.filter((t) => sections[t])
      .map((t) => {
        const sec = sections[t];
        const secTotal = sec.covered.length + sec.missing.length;

        const renderItem = (it) => {
          const m = it.match;
          const isCov = it.status === "covered" && m;
          const prio =
            {
              p1: "high",
              p2: "medium",
              p3: "low",
              1: "high",
              2: "medium",
              3: "low",
              critical: "high",
              mid: "medium",
              high: "high",
              medium: "medium",
              low: "low",
            }[(it.priority || "low").toString().toLowerCase()] || "low";
          const displayCodeHtml = it.display_id
            ? `<code class="auto-cov-code">${esc(it.display_id)}</code>`
            : "";

          let detailHtml = "";
          if (isCov) {
            const fw = m.framework || "unknown";
            const fwClass = [
              "playwright",
              "cypress",
              "cucumber",
              "jest",
            ].includes(fw.toLowerCase())
              ? fw.toLowerCase()
              : "unknown";

            const shortRepo =
              (m.repo_full_name || "").split("/").pop() ||
              m.repo_full_name ||
              "";

            let fileLink = "";
            if (m.file_url) {
              const shortPath = (m.file_path || "")
                .split("/")
                .slice(-3)
                .join("/");
              fileLink = `<a href="${esc(m.file_url)}" target="_blank" rel="noopener" class="auto-cov-detail-link" title="Open file">${esc(shortPath)}</a>`;
            } else if (m.file_path) {
              const shortPath = (m.file_path || "")
                .split("/")
                .slice(-3)
                .join("/");
              fileLink = `<span class="auto-cov-detail-link" title="${esc(m.file_path)}">${esc(shortPath)}</span>`;
            }

            detailHtml = `
            <div class="auto-cov-detail">
              <p class="auto-cov-detail-label">Matched Automation Test</p>
              <p class="auto-cov-detail-title">${esc(m.title || "Untitled test")}</p>
              <div class="auto-cov-detail-meta">
                <span class="auto-cov-fw-badge ${fwClass}">${esc(fw)}</span>
                <span class="auto-cov-repo-badge" title="${esc(m.repo_full_name)}">${esc(shortRepo)}</span>
                ${fileLink}
                <span class="auto-cov-detail-confidence">${Math.round((m.score || 0) * 100)}% match confidence</span>
              </div>
            </div>
          `;
          }

          const cardClass = `auto-cov-card ${isCov ? "covered" : "missing"}`;
          const checkClass = `auto-cov-check ${isCov ? "covered" : "missing"}`;
          const prioClass = `auto-cov-priority ${prio}`;
          const statusBadgeClass = `auto-cov-badge-status ${isCov ? "covered" : "missing"}`;
          const typeLabelMuted = it.generated_type
            ? `<span class="badge" style="border:none;background:transparent;padding:0;color:var(--muted);font-size:11px;margin-left:auto">${esc(it.generated_type.replace(/_/g, " "))} tests</span>`
            : "";

          const statusBadge = isCov
            ? `<span class="${statusBadgeClass}">✓ Test Exists</span>`
            : `<span class="${statusBadgeClass}">○ Test Missing</span>`;

          const chevronHtml = isCov
            ? `<span class="auto-cov-chevron">▼</span>`
            : "";

          const onclickAttr = isCov
            ? `onclick="this.closest('.auto-cov-card').classList.toggle('open')"`
            : "";

          return `
          <div class="${cardClass}">
            <button type="button" class="auto-cov-row" ${onclickAttr}>
              <span class="${checkClass}">${isCov ? "✓" : "○"}</span>
              <span class="${prioClass}" title="Priority: ${esc(prio)}"></span>
              ${displayCodeHtml}
              <span class="auto-cov-title">${esc(it.generated_title || "")}</span>
              ${typeLabelMuted}
              ${statusBadge}
              ${chevronHtml}
            </button>
            ${detailHtml}
          </div>
        `;
        };

        return `<details class="case-group gap-section" ${sec.covered.length > 0 ? "open" : ""}>
        <summary style="color:var(--text);font-size:13px;text-transform:none;letter-spacing:normal;font-weight:600">
          <div style="display:flex;align-items:center;gap:8px">
            <span>${esc(TYPE_TITLES[t] || t.toUpperCase())}</span>
            <span class="badge" style="border-radius:999px;background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--muted);padding:2px 7px;font-size:10px">${secTotal}</span>
          </div>
        </summary>
        <div class="case-group-body" style="padding:10px 14px 14px">
          ${
            sec.covered.length
              ? `
            <div class="typehdr" style="margin:0 0 8px;font-size:10.5px;color:var(--green)">DONE (${sec.covered.length})</div>
            ${sec.covered.map(renderItem).join("")}
          `
              : ""
          }
          ${
            sec.missing.length
              ? `
            <div class="typehdr" style="margin:12px 0 8px;font-size:10.5px;color:var(--red)">MISSING (${sec.missing.length})</div>
            ${sec.missing.map(renderItem).join("")}
          `
              : ""
          }
        </div>
      </details>`;
      })
      .join("");

    const stillRunning = repos.some((rp) => rp.scan_status === "running");
    if (stillRunning) {
      if (GAP_AUTO_POLL) clearTimeout(GAP_AUTO_POLL);
      GAP_AUTO_POLL = setTimeout(loadGapAuto, 3000);
    }
  } catch (e) {
    $("#gap-auto-repos").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

if ($("#gap-auto-refresh")) $("#gap-auto-refresh").onclick = loadGapAuto;

window.rescanTestRepo = async (rid) => {
  if (!currentProject) return;
  try {
    const fid = currentFeature ? `?feature_id=${currentFeature}` : "";
    await api(`/api/projects/${currentProject}/repos/${rid}/rescan${fid}`, {
      method: "POST",
    });
    toast("Rescan started — matching only the current feature for speed");
    setTimeout(loadGapAuto, 1500);
  } catch (e) {
    toast(e.message, true);
  }
};

window.resetScanStatus = async (rid) => {
  if (!currentProject) return;
  if (
    !(await uiConfirm(
      "Force-mark this scan as failed? Use this when a scan has been stuck for several minutes.",
      "Reset Scan Status",
      "Reset",
      true,
    ))
  )
    return;
  try {
    await api(`/api/projects/${currentProject}/repos/${rid}/scan/reset`, {
      method: "POST",
    });
    toast("Scan reset — you can now try Rescan again");
    setTimeout(loadGapAuto, 500);
  } catch (e) {
    toast(e.message, true);
  }
};
