// ---- projects + repos ----
async function loadProjects() {
  if (
    $("#project-cards-container") &&
    !$("#project-cards-container").dataset.loaded
  )
    skIn("#project-cards-container", skeleton.cards(6, "Loading projects"));
  try {
    let r = await api("/api/projects");
    window.allProjects = r.projects;
    if ($("#project-cards-container"))
      $("#project-cards-container").dataset.loaded = "1";
    if (r.projects.length) {
      if (!currentProject || !r.projects.find((p) => p.id === currentProject))
        currentProject = r.projects[0].id;
    } else {
      currentProject = "";
    }

    const opts = r.projects
      .map(
        (p) =>
          `<option value="${p.id}">${esc(p.name)} — ${p.repo_count} repos · ${p.feature_count} features</option>`,
      )
      .join("");
    if ($("#proj-sel")) {
      $("#proj-sel").innerHTML = opts;
      $("#proj-sel").value = currentProject;
    }
    if ($("#f-project")) {
      $("#f-project").innerHTML = opts;
      $("#f-project").value = currentProject;
    }
    if ($("#cyc-proj")) {
      $("#cyc-proj").innerHTML = opts;
      $("#cyc-proj").value = currentProject;
    }
    if ($("#tcy-proj")) {
      $("#tcy-proj").innerHTML = opts;
      $("#tcy-proj").value = currentProject;
    }
    if ($("#mm-proj")) {
      $("#mm-proj").innerHTML = opts;
      $("#mm-proj").value = currentProject;
    }
    if ($("#dev-proj")) {
      $("#dev-proj").innerHTML = opts;
      $("#dev-proj").value = currentProject;
    }
    if ($("#tc-proj")) {
      $("#tc-proj").innerHTML = `<option value="">All projects</option>` + opts;
    }

    // Project selection cards: click enters the project's feature list; management lives in the menu.
    if ($("#project-cards-container")) {
      $("#project-cards-container").innerHTML =
        r.projects
          .map(
            (p) => `
        <div class="entity-card" data-project-card="${p.id}" onclick="openProjectFeatures('${p.id}')">
            <button class="entity-menu-btn" title="Project options" onclick="event.stopPropagation();toggleProjectMenu('${p.id}')"><svg viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px;display:block"><circle cx="12" cy="5" r="2"></circle><circle cx="12" cy="12" r="2"></circle><circle cx="12" cy="19" r="2"></circle></svg></button>
          <div class="entity-menu" onclick="event.stopPropagation()">
            <button onclick="openProjectSettings('${p.id}')">Settings & repositories</button>
            <button onclick="renameProjectFromCard('${p.id}')">Rename</button>
            <button class="danger-option" onclick="deleteProjectFromCard('${p.id}')">Delete</button>
          </div>
          <div class="entity-name">${esc(p.name)}</div>
          <div class="entity-meta">${p.feature_count} feature${p.feature_count === 1 ? "" : "s"} · ${p.repo_count} repositor${p.repo_count === 1 ? "y" : "ies"}</div>
          <div class="entity-foot"><span>Open features</span><span class="entity-arrow">›</span></div>
        </div>
      `,
          )
          .join("") ||
        `<div class="empty-state" style="grid-column: 1 / -1"><div class="empty-state-icon">+</div><h3>No projects yet</h3><p>Create your first project to continue.</p><button class="go" onclick="showProjectCreate()">Create project</button></div>`;

      const activeProj = r.projects.find((p) => p.id === currentProject);
      if (activeProj) {
        $("#active-proj-title").textContent = activeProj.name;
        $("#active-proj-stats").textContent =
          `${activeProj.repo_count} repositories · ${activeProj.feature_count} features`;
        $("#project-feature-count").textContent = activeProj.feature_count;
        $("#project-repo-count").textContent = activeProj.repo_count;
        api(`/api/test-cases?project_id=${activeProj.id}&status=all&limit=1`)
          .then((x) => ($("#project-case-count").textContent = x.total))
          .catch(() => ($("#project-case-count").textContent = "—"));
        if ($("#features-page-title"))
          $("#features-page-title").textContent = activeProj.name;
        if ($("#features-project-context"))
          $("#features-project-context").textContent =
            `${activeProj.feature_count} feature${activeProj.feature_count === 1 ? "" : "s"}`;
      } else {
        if ($("#active-proj-title")) $("#active-proj-title").textContent = "";
        if ($("#active-proj-stats")) $("#active-proj-stats").textContent = "";
        if ($("#project-feature-count"))
          $("#project-feature-count").textContent = "0";
        if ($("#project-repo-count"))
          $("#project-repo-count").textContent = "0";
        if ($("#project-case-count"))
          $("#project-case-count").textContent = "—";
        if ($("#features-page-title"))
          $("#features-page-title").textContent = "";
        if ($("#features-project-context"))
          $("#features-project-context").textContent = "";
      }
    }
    if (!$("#project-detail-page").hidden) loadRepos();
    updateBackbar();
  } catch (e) {}
}

function showProjectList() {
  if ($("#project-list-toolbar")) $("#project-list-toolbar").style.display = "";
  if ($("#proj-create-card")) $("#proj-create-card").style.display = "none";
  if ($("#project-cards-container"))
    $("#project-cards-container").style.display = "";
  if ($("#proj-new-btn")) $("#proj-new-btn").style.display = "";
  if ($("#project-list-page")) $("#project-list-page").hidden = false;
  if ($("#project-detail-page")) $("#project-detail-page").hidden = true;
  updateBackbar();
}
function showProjectCreate() {
  if ($("#project-list-page")) $("#project-list-page").hidden = false;
  if ($("#project-detail-page")) $("#project-detail-page").hidden = true;
  if ($("#project-list-toolbar"))
    $("#project-list-toolbar").style.display = "none";
  if ($("#project-cards-container"))
    $("#project-cards-container").style.display = "none";
  if ($("#proj-create-card")) $("#proj-create-card").style.display = "block";
  updateBackbar();
}
function showProjectDetail() {
  $("#project-list-page").hidden = true;
  $("#project-detail-page").hidden = false;
  updateBackbar();
}
window.openProjectFeatures = async (pid) => {
  currentProject = pid;
  currentFeature = null;
  navigateTo("features");
  await loadFeatures();
  showFeatureList();
};
window.openProjectSettings = async (pid) => {
  currentProject = pid;
  showProjectDetail();
  await loadProjects();
  renderBreadcrumbs();
  // Apply the project's saved provider so the PAT/repo panel starts on the right toggle.
  try {
    const proj = await api(`/api/projects/${pid}`);
    const dp = (proj.default_git_provider || "github").toLowerCase();
    PD_PROVIDER = dp;
    document.querySelectorAll("[data-pd-provider]").forEach((b) => {
      const isMatch = b.dataset.pdProvider === dp;
      b.classList.toggle("active", isMatch);
      b.style.display = isMatch ? "" : "none";
    });
    if ($("#pd-pat"))
      $("#pd-pat").placeholder = dp === "gitlab" ? "glpat-..." : "ghp_...";
  } catch (e) {
    /* fall through to default github */
  }
  refreshProjectPatStatus();
};
window.selectProject = window.openProjectSettings;
window.toggleProjectMenu = (pid) => {
  document.querySelectorAll("[data-project-card]").forEach((card) => {
    if (card.dataset.projectCard !== pid) card.classList.remove("menu-open");
  });
  const card = document.querySelector(`[data-project-card="${pid}"]`);
  if (card) card.classList.toggle("menu-open");
};
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-project-card]"))
    document
      .querySelectorAll("[data-project-card]")
      .forEach((card) => card.classList.remove("menu-open"));
  if (!e.target.closest("[data-feature-card]"))
    document
      .querySelectorAll("[data-feature-card]")
      .forEach((card) => card.classList.remove("menu-open"));
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document
      .querySelectorAll("[data-project-card], [data-feature-card]")
      .forEach((card) => card.classList.remove("menu-open"));
  }
});
if ($("#project-detail-back"))
  $("#project-detail-back").onclick = () => showProjectList();
if ($("#proj-features-btn"))
  $("#proj-features-btn").onclick = () => {
    currentFeature = null;
    navigateTo("features");
    showFeatureList();
  };
if ($("#features-back-project"))
  $("#features-back-project").onclick = () => {
    navigateTo("projects");
    showProjectList();
    loadProjects();
  };

if ($("#f-project"))
  $("#f-project").onchange = async (e) => {
    currentProject = e.target.value;
    loadFeatures();
    renderBreadcrumbs();
    await loadFeatureTicketOptions();
  };

// Repo "kind" = display/badge classification (independent of app/test repo_type).
// Canonical: BE, FE, test, infra. "other" is legacy — still rendered, never offered.
const REPO_KINDS = [
  ["BE", "Backend"],
  ["FE", "Frontend"],
  ["test", "Test"],
  ["infra", "Infrastructure"],
];
function repoKindLabel(k) {
  const m = {
    BE: "BE",
    FE: "FE",
    test: "Test",
    infra: "Infra",
    other: "Other",
  };
  return m[k] || k || "BE";
}
function repoKindClass(k) {
  return (k || "BE").toLowerCase();
}
function repoKindOptions(sel) {
  return REPO_KINDS.map(
    ([v, lab]) =>
      `<option value="${v}"${v === sel ? " selected" : ""}>${lab}</option>`,
  ).join("");
}
// Kinds that appear in Mind Map / Change impact analysis but are NOT pre-selected —
// infrastructure code, so the user opts it in rather than out. (Test-TYPE repos are
// already excluded from these views entirely; that exclusion is unchanged.)
const REPO_KINDS_ANALYSIS_OPT_IN = new Set(["infra"]);
function repoAnalysisDefaultChecked(k) {
  return !REPO_KINDS_ANALYSIS_OPT_IN.has((k || "").toLowerCase());
}

// New Project — multi-step form state
const NEW_PROJ = {
  provider: "github",
  appRepos: [], // [{full_name, label, kind}]
  testRepos: [],
  available: [], // last loaded list
};

function _resetNewProj() {
  NEW_PROJ.provider = "github";
  NEW_PROJ.appRepos = [];
  NEW_PROJ.testRepos = [];
  NEW_PROJ.available = [];
  $("#new-proj-name").value = "";
  $("#new-proj-desc").value = "";
  $("#new-proj-pat").value = "";
  $("#new-proj-name-err").textContent = "";
  $("#new-proj-pat-status").textContent = "";
  $("#new-proj-jira-status").textContent = "";
  $("#new-proj-confluence-status").textContent = "";
  $("#proj-create-status").textContent = "";
  $("#new-proj-jira").innerHTML = '<option value="">— none —</option>';
  $("#new-proj-confluence").innerHTML = '<option value="">— none —</option>';
  _renderCpRepoPickers();
  document.querySelectorAll(".cp-prov").forEach((b) => {
    b.classList.toggle("active", b.dataset.provider === "github");
  });
}

function _renderCpRepoPickers() {
  const stagedAppFullNames = new Set(NEW_PROJ.appRepos.map((r) => r.full_name));
  const stagedTestFullNames = new Set(
    NEW_PROJ.testRepos.map((r) => r.full_name),
  );
  const stagedMapFor = (key) => {
    const bucket = key === "app" ? NEW_PROJ.appRepos : NEW_PROJ.testRepos;
    return new Map(bucket.map((r) => [r.full_name, r]));
  };
  const render = (el, staged, otherStaged, sectionKey) => {
    if (!el) return;
    el.innerHTML = "";
    if (NEW_PROJ.available.length === 0) {
      el.innerHTML =
        '<div class="muted cp-repo-empty">Load repositories above to pick.</div>';
      return;
    }
    const stagedMap = stagedMapFor(sectionKey);
    // Show staged first, then everything not staged in either section
    const lines = [];
    NEW_PROJ.available.forEach((r) => {
      const isStaged = staged.has(r.full_name);
      const usedElsewhere = otherStaged.has(r.full_name);
      if (usedElsewhere) return;
      const stagedRepo = stagedMap.get(r.full_name);
      lines.push(`<div class="cp-repo-row${isStaged ? " staged" : ""}">
        <div class="cp-repo-main">
          <div class="cp-repo-name"><b>${esc(r.full_name)}</b> <span class="cp-repo-meta">${r.private ? "private" : "public"}${r.default_branch ? " · " + esc(r.default_branch) : ""}</span></div>
          ${
            isStaged
              ? `<div class="cp-repo-fields" style="display:flex;gap:8px;align-items:center;margin-top:6px">
                 <input class="cp-repo-label-input" data-key="${sectionKey}" data-fn="${esc(r.full_name)}" value="${esc((stagedRepo && stagedRepo.label) || "")}" placeholder="Display name (e.g. Backend API)" style="flex:1"/>
                 <select class="cp-repo-kind-input" data-key="${sectionKey}" data-fn="${esc(r.full_name)}" title="Kind" style="flex:0 0 130px;font-size:12px;padding:5px 8px">${repoKindOptions((stagedRepo && stagedRepo.kind) || (sectionKey === "test" ? "test" : "BE"))}</select>
               </div>`
              : ``
          }
        </div>
        <div class="cp-repo-actions">
        ${
          isStaged
            ? `<button type="button" class="cp-repo-remove" data-key="${sectionKey}" data-fn="${esc(r.full_name)}">remove</button>`
            : `<button type="button" class="cp-repo-add" data-key="${sectionKey}" data-fn="${esc(r.full_name)}">add</button>`
        }
        </div>
      </div>`);
    });
    el.innerHTML =
      lines.join("") ||
      '<div class="muted cp-repo-empty">No more repositories available.</div>';
  };
  render(
    $("#new-proj-app-picker"),
    stagedAppFullNames,
    stagedTestFullNames,
    "app",
  );
  render(
    $("#new-proj-test-picker"),
    stagedTestFullNames,
    stagedAppFullNames,
    "test",
  );
  $("#new-proj-app-count").textContent = NEW_PROJ.appRepos.length;
  $("#new-proj-test-count").textContent = NEW_PROJ.testRepos.length;
}

document.addEventListener("click", (e) => {
  const t = e.target.closest(".cp-repo-add, .cp-repo-remove");
  if (!t) return;
  const fn = t.dataset.fn;
  const key = t.dataset.key;
  const bucket = key === "app" ? NEW_PROJ.appRepos : NEW_PROJ.testRepos;
  const isRemove = t.classList.contains("cp-repo-remove");
  const meta = NEW_PROJ.available.find((r) => r.full_name === fn);
  if (isRemove) {
    const idx = bucket.findIndex((r) => r.full_name === fn);
    if (idx >= 0) bucket.splice(idx, 1);
  } else if (meta) {
    bucket.push({
      full_name: fn,
      label: (fn.split("/").pop() || fn).replace(/[-_]+/g, " "),
      kind: key === "test" ? "test" : "BE",
    });
  }
  _renderCpRepoPickers();
});

// Per-repo Kind dropdown in the create-project wizard.
document.addEventListener("change", (e) => {
  const t = e.target.closest(".cp-repo-kind-input");
  if (!t) return;
  const bucket =
    t.dataset.key === "app" ? NEW_PROJ.appRepos : NEW_PROJ.testRepos;
  const repo = bucket.find((r) => r.full_name === t.dataset.fn);
  if (repo) repo.kind = t.value;
});

document.addEventListener("input", (e) => {
  const t = e.target.closest(".cp-repo-label-input");
  if (!t) return;
  const fn = t.dataset.fn;
  const key = t.dataset.key;
  const bucket = key === "app" ? NEW_PROJ.appRepos : NEW_PROJ.testRepos;
  const repo = bucket.find((r) => r.full_name === fn);
  if (repo) repo.label = t.value;
});

document.querySelectorAll(".cp-prov").forEach((btn) => {
  btn.onclick = () => {
    NEW_PROJ.provider = btn.dataset.provider;
    document
      .querySelectorAll(".cp-prov")
      .forEach((b) => b.classList.toggle("active", b === btn));
    NEW_PROJ.available = [];
    NEW_PROJ.appRepos = [];
    NEW_PROJ.testRepos = [];
    $("#new-proj-pat").placeholder =
      NEW_PROJ.provider === "gitlab" ? "glpat-..." : "ghp_...";
    $("#new-proj-pat-status").textContent = "";
    _renderCpRepoPickers();
  };
});

async function loadJiraProjectsForCreate() {
  $("#new-proj-jira-status").textContent = "Loading…";
  try {
    const r = await api("/api/atlassian/accessible-jira-projects");
    const sel = $("#new-proj-jira");
    const avail = (r.projects || []).filter((p) => !p.in_use);
    sel.innerHTML =
      '<option value="">— none —</option>' +
      avail
        .map(
          (p) =>
            `<option value="${esc(p.key)}" data-name="${esc(p.name)}">${esc(p.key)} — ${esc(p.name)}</option>`,
        )
        .join("");
    const usedCount = (r.projects || []).length - avail.length;
    $("#new-proj-jira-status").textContent =
      `${avail.length} project(s) available` +
      (usedCount ? ` · ${usedCount} already linked` : "");
  } catch (e) {
    $("#new-proj-jira-status").innerHTML =
      `<span class="err">${esc(e.message)}</span>`;
  }
}

async function loadConfluenceSpacesForCreate() {
  $("#new-proj-confluence-status").textContent = "Loading…";
  try {
    const r = await api("/api/atlassian/accessible-confluence-spaces");
    const sel = $("#new-proj-confluence");
    sel.innerHTML =
      '<option value="">— none —</option>' +
      (r.spaces || [])
        .map(
          (s) =>
            `<option value="${esc(s.key)}" data-name="${esc(s.name)}">${esc(s.key)} — ${esc(s.name)}</option>`,
        )
        .join("");
    $("#new-proj-confluence-status").textContent =
      `${(r.spaces || []).length} space(s) available`;
  } catch (e) {
    $("#new-proj-confluence-status").innerHTML =
      `<span class="err">${esc(e.message)}</span>`;
  }
}

if ($("#new-proj-jira-refresh"))
  $("#new-proj-jira-refresh").onclick = loadJiraProjectsForCreate;
if ($("#new-proj-confluence-refresh"))
  $("#new-proj-confluence-refresh").onclick = loadConfluenceSpacesForCreate;

if ($("#new-proj-load-repos"))
  $("#new-proj-load-repos").onclick = async () => {
    const pat = $("#new-proj-pat").value.trim();
    if (!pat) {
      $("#new-proj-pat-status").innerHTML =
        '<span class="err">Enter a PAT first</span>';
      return;
    }
    setBusy("#new-proj-load-repos", true);
    $("#new-proj-pat-status").innerHTML =
      `<span class="spin-inline"></span>Loading repositories…`;
    // We need a transient project context to call the API. Pre-create the project? No — better:
    // hit a paginated repo-list endpoint that accepts X-Provider-PAT *without* a project id by
    // routing through the legacy GitHub paginated path.
    try {
      let repos = [];
      for (let page = 1; page <= 5; page++) {
        const url = `/api/git/accessible-repos?provider=${encodeURIComponent(NEW_PROJ.provider)}&page=${page}`;
        const r = await api(url, { headers: { "X-Provider-PAT": pat } });
        if (!r.repos || !r.repos.length) break;
        repos = repos.concat(r.repos);
        if (r.repos.length < 30) break;
      }
      NEW_PROJ.available = repos;
      _renderCpRepoPickers();
      $("#new-proj-pat-status").innerHTML =
        `<span class="ok">${repos.length} repos loaded</span>`;
    } catch (e) {
      $("#new-proj-pat-status").innerHTML =
        `<span class="err">${esc(e.message)}</span>`;
    } finally {
      setBusy("#new-proj-load-repos", false);
    }
  };

if ($("#proj-new-btn"))
  $("#proj-new-btn").onclick = () => {
    _resetNewProj();
    showProjectCreate();
    $("#new-proj-name").focus();
    // Pre-load Jira lists if the user already configured them in Settings; silently
    // no-op when not configured (the status line surfaces the reason).
    loadJiraProjectsForCreate();
    loadConfluenceSpacesForCreate();
  };

if ($("#proj-create-back"))
  $("#proj-create-back").onclick = () => {
    showProjectList();
  };

if ($("#proj-create-cancel"))
  $("#proj-create-cancel").onclick = () => {
    showProjectList();
  };

if ($("#proj-create-save"))
  $("#proj-create-save").onclick = async () => {
    const name = $("#new-proj-name").value.trim();
    $("#new-proj-name-err").textContent = "";
    if (!name) {
      $("#new-proj-name-err").textContent = "Project name is required.";
      return;
    }
    const description = $("#new-proj-desc").value.trim();
    const jiraOpt = $("#new-proj-jira").selectedOptions[0];
    const jiraKey = jiraOpt && jiraOpt.value ? jiraOpt.value : null;
    const jiraName =
      jiraOpt && jiraOpt.value
        ? jiraOpt.dataset.name || jiraOpt.textContent
        : null;
    const conOpt = $("#new-proj-confluence").selectedOptions[0];
    const conKey = conOpt && conOpt.value ? conOpt.value : null;
    const conName =
      conOpt && conOpt.value ? conOpt.dataset.name || conOpt.textContent : null;
    const pat = $("#new-proj-pat").value.trim();

    $("#proj-create-status").innerHTML =
      `<span class="spin-inline"></span>Creating project…`;
    setBusy("#proj-create-save", true);
    $("#proj-create-save").disabled = true;
    $("#proj-create-cancel").disabled = true;
    const finishCreate = () => {
      setBusy("#proj-create-save", false);
      $("#proj-create-save").disabled = false;
      $("#proj-create-cancel").disabled = false;
    };
    let createdId = null;
    try {
      const r = await api("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description,
          jira_project_key: jiraKey,
          jira_project_name: jiraName,
          confluence_space_key: conKey,
          confluence_space_name: conName,
          default_git_provider: NEW_PROJ.provider,
        }),
      });
      createdId = r.id;
    } catch (e) {
      $("#proj-create-status").innerHTML =
        `<span class="err">${esc(e.message)}</span>`;
      finishCreate();
      return;
    }

    if (pat) {
      try {
        const patUrl =
          NEW_PROJ.provider === "gitlab"
            ? `/api/projects/${createdId}/gitlab/pat`
            : `/api/projects/${createdId}/github/pat`;
        await api(patUrl, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pat }),
        });
      } catch (e) {
        toast(`Project created, but PAT save failed: ${e.message}`, true);
      }
      const allRepos = [
        ...NEW_PROJ.appRepos.map((r) => ({ ...r, repo_type: "app" })),
        ...NEW_PROJ.testRepos.map((r) => ({ ...r, repo_type: "test" })),
      ];
      let connected = 0;
      if (allRepos.length)
        $("#proj-create-status").innerHTML =
          `<span class="spin-inline"></span>Connecting ${allRepos.length} repositor${allRepos.length === 1 ? "y" : "ies"}…`;
      for (const r of allRepos) {
        try {
          await api(`/api/projects/${createdId}/repos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              repo_full_name: r.full_name,
              label: (r.label || "").trim() || r.full_name,
              repo_type: r.repo_type,
              git_provider: NEW_PROJ.provider,
              kind: r.kind || (r.repo_type === "test" ? "test" : "BE"),
            }),
          });
          connected += 1;
        } catch (e) {
          toast(`Repo ${r.full_name} failed: ${e.message}`, true);
        }
      }
      if (connected > 0)
        toast(`Project created · ${connected} repo(s) connected`);
      else toast("Project created");
    } else {
      toast("Project created");
    }

    $("#proj-create-status").innerHTML =
      `<span class="spin-inline"></span>Opening project…`;
    currentProject = createdId;
    showProjectList();
    try {
      await loadProjects();
      await openProjectFeatures(createdId);
      renderBreadcrumbs();
    } finally {
      finishCreate();
      $("#proj-create-status").textContent = "";
    }
  };

// Rename/delete handlers
if ($("#proj-rename-btn"))
  $("#proj-rename-btn").onclick = async () => {
    if (!currentProject) return;
    const title = $("#active-proj-title").textContent;
    const name = await uiPrompt(
      "Rename project",
      "New name for the project",
      title,
    );
    if (!name) return;
    try {
      await api(`/api/projects/${currentProject}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      loadProjects();
      toast("Project renamed successfully!");
    } catch (e) {
      toast(e.message, true);
    }
  };
function projectCardName(pid) {
  return (
    document
      .querySelector(`[data-project-card="${pid}"] .entity-name`)
      ?.textContent?.trim() || "Project"
  );
}
window.renameProjectFromCard = async (pid) => {
  const name = projectCardName(pid);
  const next = await uiPrompt(
    "Rename project",
    "New name for the project",
    name || "",
  );
  if (!next) return;
  try {
    await api(`/api/projects/${pid}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: next }),
    });
    loadProjects();
    toast("Project renamed");
  } catch (e) {
    toast(e.message, true);
  }
};
if ($("#proj-del-btn"))
  $("#proj-del-btn").onclick = async () => {
    if (!currentProject) return;
    const projectId = currentProject;
    openCaseConfirmation({
      title: "Delete project",
      copy: "This removes this project, its features, repositories, and project-only test-case links. Test cases linked to features in another project will remain.",
      summary: `<b>${esc($("#active-proj-title").textContent)}</b><div class="muted" style="margin-top:6px">${esc($("#active-proj-stats").textContent)}</div>`,
      confirmLabel: "Delete project",
      danger: true,
      onConfirm: async () => {
        const r = await api(`/api/projects/${projectId}`, { method: "DELETE" });
        currentProject = null;
        showProjectList();
        loadProjects();
        refreshStatus();
        toast(
          `Project deleted · ${r.features} feature(s), ${r.removed_orphan_cases} orphan test case(s) removed, ${r.preserved_shared_cases} shared test case(s) preserved`,
        );
      },
    });
  };
window.deleteProjectFromCard = async (pid) => {
  const name = projectCardName(pid);
  currentProject = pid;
  openCaseConfirmation({
    title: "Delete project",
    copy: "This removes this project, its features, repositories, and project-only test-case links. Test cases linked to another project remain available.",
    summary: `<b>${esc(name || "Project")}</b>`,
    confirmLabel: "Delete project",
    danger: true,
    onConfirm: async () => {
      const r = await api(`/api/projects/${pid}`, { method: "DELETE" });
      currentProject = null;
      showProjectList();
      loadProjects();
      refreshStatus();
      toast(
        `Project deleted · ${r.features} feature(s), ${r.removed_orphan_cases} orphan test case(s) removed, ${r.preserved_shared_cases} shared test case(s) preserved`,
      );
    },
  });
};

// Project-detail provider toggle + PAT management
let PD_PROVIDER = "github";
// Repos fetched via "Load my repositories" for the Connect-repository box
// below. Kept in memory and never mutated by selection/filtering, so picking
// one repo doesn't shrink what's offered the next time the suggestion panel
// reopens — see renderRepoSuggest().
let REPO_PICK_CACHE = [];
document.querySelectorAll("[data-pd-provider]").forEach((btn) => {
  btn.onclick = async () => {
    PD_PROVIDER = btn.dataset.pdProvider;
    document
      .querySelectorAll("[data-pd-provider]")
      .forEach((b) => b.classList.toggle("active", b === btn));
    if ($("#pd-pat"))
      $("#pd-pat").placeholder =
        PD_PROVIDER === "gitlab" ? "glpat-..." : "ghp_...";
    // Persist the change so future PR coverage routes through the right API.
    if (currentProject) {
      try {
        await api(`/api/projects/${currentProject}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ default_git_provider: PD_PROVIDER }),
        });
      } catch (e) {
        /* non-fatal — toggle still takes effect for this session */
      }
    }
    refreshProjectPatStatus();
  };
});

async function refreshProjectPatStatus() {
  if (!currentProject || !$("#pd-pat-status")) return;
  try {
    const url =
      PD_PROVIDER === "gitlab"
        ? `/api/projects/${currentProject}/gitlab/pat`
        : `/api/projects/${currentProject}/github/pat`;
    const r = await api(url);
    $("#pd-pat-status").innerHTML = r.configured
      ? `<span class="ok">${PD_PROVIDER === "gitlab" ? "GitLab" : "GitHub"} PAT configured</span>`
      : `<span class="muted">No ${PD_PROVIDER === "gitlab" ? "GitLab" : "GitHub"} PAT set for this project</span>`;
  } catch (e) {
    $("#pd-pat-status").innerHTML =
      `<span class="muted">PAT status unknown</span>`;
  }
}

if ($("#pd-pat-save"))
  $("#pd-pat-save").onclick = async () => {
    const pat = $("#pd-pat").value.trim();
    if (!pat) {
      toast("Enter a PAT first", true);
      return;
    }
    const url =
      PD_PROVIDER === "gitlab"
        ? `/api/projects/${currentProject}/gitlab/pat`
        : `/api/projects/${currentProject}/github/pat`;
    try {
      await api(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pat }),
      });
      $("#pd-pat").value = "";
      toast("PAT saved");
      refreshProjectPatStatus();
    } catch (e) {
      toast(e.message, true);
    }
  };

if ($("#pd-pat-clear"))
  $("#pd-pat-clear").onclick = async () => {
    const url =
      PD_PROVIDER === "gitlab"
        ? `/api/projects/${currentProject}/gitlab/pat`
        : `/api/projects/${currentProject}/github/pat`;
    try {
      await api(url, { method: "DELETE" });
      $("#pd-pat").value = "";
      toast("PAT cleared");
      refreshProjectPatStatus();
    } catch (e) {
      toast(e.message, true);
    }
  };

if ($("#repo-add"))
  $("#repo-add").onclick = async () => {
    const url = $("#repo-url").value.trim();
    if (!url || !currentProject) return;
    try {
      await api(`/api/projects/${currentProject}/repos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          kind: $("#repo-kind").value,
          repo_type: $("#repo-type") ? $("#repo-type").value : "app",
          git_provider: PD_PROVIDER,
        }),
      });
      $("#repo-url").value = "";
      loadRepos();
      toast("Repo added & watching");
    } catch (e) {
      toast(e.message, true);
    }
  };

// Renders the "Connect repository" suggestion panel from REPO_PICK_CACHE,
// filtered by `q` (case-insensitive substring match on full_name). The
// filter only ever reads REPO_PICK_CACHE — it's never trimmed or replaced —
// so calling this with an empty `q` (which onfocus/onclick below always do)
// shows the COMPLETE loaded list again, regardless of whatever value is
// currently sitting in the input from a prior selection. That's the bug fix:
// previously this box was a native <input list="myrepos"> + <datalist>,
// and browsers filter datalist suggestions against the input's current
// value — so after picking a repo, reopening only offered entries matching
// that exact text (usually just itself).
function renderRepoSuggest(q) {
  const box = $("#repo-url-suggest");
  if (!box) return;
  if (!REPO_PICK_CACHE.length) {
    box.hidden = true;
    return;
  }
  const ql = (q || "").trim().toLowerCase();
  const matches = REPO_PICK_CACHE.filter(
    (x) => !ql || (x.full_name || "").toLowerCase().includes(ql),
  );
  if (!matches.length) {
    box.innerHTML = `<div class="muted" style="padding:8px 10px;font-size:12px">No matches.</div>`;
    box.hidden = false;
    return;
  }
  box.innerHTML = matches
    .slice(0, 200)
    .map(
      (x) =>
        `<div class="repo-suggest-row" data-full-name="${esc(x.full_name)}" style="padding:7px 10px;font-size:12.5px;cursor:pointer;display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid rgba(255,255,255,.04)">
       <span>${esc(x.full_name)}</span>
       <span class="muted" style="font-size:11px;white-space:nowrap">${x.private ? "private" : "public"}${x.language ? " · " + esc(x.language) : ""}</span>
     </div>`,
    )
    .join("");
  box.hidden = false;
}
// mousedown (not click) fires before the input's blur, so picking a row
// registers before the panel would otherwise close out from under it.
document.addEventListener("mousedown", (e) => {
  const row = e.target.closest(".repo-suggest-row");
  if (row) {
    if ($("#repo-url")) $("#repo-url").value = row.dataset.fullName;
    if ($("#repo-url-suggest")) $("#repo-url-suggest").hidden = true;
    return;
  }
  if (!e.target.closest("[data-repo-suggest-wrap]") && $("#repo-url-suggest"))
    $("#repo-url-suggest").hidden = true;
});
document.addEventListener("keydown", (e) => {
  if (
    e.key === "Escape" &&
    $("#repo-url-suggest") &&
    !$("#repo-url-suggest").hidden
  )
    $("#repo-url-suggest").hidden = true;
});
if ($("#repo-url")) {
  $("#repo-url").oninput = (e) => renderRepoSuggest(e.target.value);
  // Reopening (focus or click) always re-shows the complete cached list —
  // see renderRepoSuggest()'s comment above for why this is the actual fix.
  $("#repo-url").onfocus = () => renderRepoSuggest("");
  $("#repo-url").onclick = () => renderRepoSuggest("");
}

if ($("#repo-pick"))
  $("#repo-pick").onclick = async () => {
    if (!currentProject) return;
    try {
      const url =
        PD_PROVIDER === "gitlab"
          ? `/api/projects/${currentProject}/gitlab/accessible-repos?page=1`
          : `/api/projects/${currentProject}/github/accessible-repos?page=1`;
      const r = await api(url);
      REPO_PICK_CACHE = r.repos || [];
      renderRepoSuggest("");
      toast(
        `${REPO_PICK_CACHE.length} repos loaded — click the box to browse, or type to filter`,
      );
    } catch (e) {
      toast(e.message, true);
    }
  };

async function loadRepos() {
  if (!currentProject || !$("#repo-list")) return;
  try {
    const r = await api(`/api/projects/${currentProject}/repos`);
    $("#repo-list").innerHTML =
      r.repos
        .map(
          (rp) => `
      <div class="repo-item-card">
        <div style="display: flex; align-items: center; gap: 10px;">
          <div>
            <div style="font-weight: 600; font-size: 13.5px; color: var(--text);">${esc(rp.full_name)}</div>
            <div style="display: flex; gap: 6px; margin-top: 4px; flex-wrap: wrap;">
              <span class="badge ${repoKindClass(rp.kind)}" style="font-size: 10px;">${esc(repoKindLabel(rp.kind))}</span>
              <span class="badge" style="font-size: 10px;">${rp.pr_count} PRs</span>
              <span style="font-size: 10.5px; display: flex; align-items: center; gap: 4px;" class="muted">
                <span class="dot ${rp.watch ? "ok" : ""}" style="margin: 0; width: 6px; height: 6px;"></span>
                ${rp.watch ? "watching" : "paused"}
              </span>
            </div>
          </div>
        </div>
        
        <div style="display: flex; gap: 6px; align-items: center;">
          ${rp.repo_type === "test"
            ? `<button class="go" style="padding: 6px 12px; font-size: 12px; display: flex; align-items: center; gap: 4px;" disabled title="Code Analysis covers app repos only">Analyze</button>`
            : `<button class="go" style="padding: 6px 12px; font-size: 12px; display: flex; align-items: center; gap: 4px;" onclick="gotoAnalyze('${rp.id}','${currentProject}')">Analyze</button>`}
          <button class="ghost" style="padding: 5px 10px; font-size: 11.5px;" onclick="syncRepo('${rp.id}')">Sync</button>
          <button class="ghost" style="padding: 5px 10px; font-size: 11.5px;" onclick="toggleWatch('${rp.id}',${!rp.watch})">
            ${rp.watch ? "Pause" : "Resume"}
          </button>
          <button class="danger" style="padding: 6px 9px; font-size: 11.5px; display: flex; align-items: center; justify-content: center;" onclick="delRepo('${rp.id}')">Remove</button>
        </div>
      </div>
    `,
        )
        .join("") || `<span class="muted">no repos yet</span>`;
  } catch (e) {}
}

window.gotoAnalyze = async (rid, pid) => {
  currentProject = pid;
  document
    .querySelectorAll("nav button")
    .forEach((x) => x.classList.toggle("active", x.dataset.view === "cycles"));
  document
    .querySelectorAll(".view")
    .forEach((s) => (s.hidden = s.id !== "view-cycles"));
  $("#view-title").textContent = TITLES.cycles;
  // The old code stopped here, so the breadcrumb bar still showed the
  // previous view (Settings) and the URL stayed on #projects. Mirror the
  // bookkeeping navigateTo() does for the cycles view: current view name
  // (drives the breadcrumb bar), URL hash, and saved nav state. This is
  // done inline instead of calling navigateTo("cycles") because its
  // initCycles() would run a second loadCycleRepos() concurrently with the
  // one below and could re-render the repo rows after the checkbox below
  // is set, silently unchecking the repo.
  currentViewName = "cycles";
  renderBreadcrumbs();
  try {
    history.replaceState(null, "", "#cycles");
  } catch (e) {}
  try {
    localStorage.setItem(
      "wq_nav",
      JSON.stringify({ view: "cycles", project: pid, feature: currentFeature }),
    );
  } catch (e) {}
  await loadProjects();
  if ($("#cyc-proj")) $("#cyc-proj").value = pid;
  await loadCycleRepos();
  document.querySelectorAll(".cyc-repo-chk").forEach((c) => {
    c.checked = c.value === rid;
  });
  loadCycles();
  toast("Repo selected — set days & click Analyze changes");
};
window.delRepo = async (id) => {
  if (
    !(await uiConfirm(
      "Remove this repo and its tracked PRs?",
      "Delete Repository",
      "Remove",
      true,
    ))
  )
    return;
  await api(`/api/repos/${id}`, { method: "DELETE" });
  loadRepos();
  toast("Repo removed");
};
window.syncRepo = async (id) => {
  await api(`/api/repos/${id}/sync`, { method: "POST" });
  $("#sync-status").textContent = "sync started…";
  setTimeout(() => {
    loadRepos();
    loadSyncStatus();
  }, 1500);
};
window.toggleWatch = async (id, w) => {
  await api(`/api/repos/${id}/watch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ watch: w }),
  });
  loadRepos();
};
async function loadSyncStatus() {
  try {
    const s = await api("/api/sync/status");
    if ($("#sync-status"))
      $("#sync-status").innerHTML =
        `poller every ${s.poll_interval_s}s · ${s.github_authenticated ? "authenticated" : "public-only"} · ingested ${s.ingested}, mapped ${s.mapped}` +
        (s.errors && s.errors.length
          ? ` · <span class="err">${esc(s.errors.slice(-1)[0])}</span>`
          : "");
  } catch (e) {}
}

