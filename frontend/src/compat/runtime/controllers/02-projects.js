// ---- project settings: provider, PAT, repositories, sync status ----
// The project list, the create wizard, rename / delete and the settings header
// are React (src/features/projects, #257); this part moves next.

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

// Project-detail provider toggle + PAT management
let PD_PROVIDER = "github";
let PD_GITLAB_HOST = null;
// Repos fetched via "Load my repositories" for the Connect-repository box
// below. Kept in memory and never mutated by selection/filtering, so picking
// one repo doesn't shrink what's offered the next time the suggestion panel
// reopens — see renderRepoSuggest().
let REPO_PICK_CACHE = [];
document.querySelectorAll("[data-pd-provider]").forEach((btn) => {
  btn.onclick = async () => setProjectProvider(btn.dataset.pdProvider);
});

// Called by the React Projects screen when project settings open: apply the
// project's saved provider so the PAT/repo panel starts on the right toggle.
window.openProjectRepoSettings = async (pid) => {
  try {
    const proj = await api(`/api/projects/${pid}`);
    const dp = (proj.default_git_provider || "github").toLowerCase();
    PD_PROVIDER = dp;
    document.querySelectorAll("[data-pd-provider]").forEach((b) => {
      const isMatch = b.dataset.pdProvider === dp;
      b.classList.toggle("active", isMatch);
    });
    if ($("#pd-pat"))
      $("#pd-pat").placeholder = dp === "gitlab" ? "glpat-..." : "ghp_...";
  } catch (e) {
    /* fall through to default github */
  }
  refreshProjectPatStatus();
};

async function setProjectProvider(provider) {
  if (provider === PD_PROVIDER) return;
  PD_PROVIDER = provider;

  document
    .querySelectorAll("[data-pd-provider]")
    .forEach((b) => b.classList.toggle("active", provider === b.dataset.pdProvider));
  if ($("#pd-pat")) {
    $("#pd-pat").placeholder =
      PD_PROVIDER === "gitlab" ? "glpat-..." : "ghp_...";
  }
  REPO_PICK_CACHE = [];
  renderRepoSuggest("");
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

  await refreshProjectPatStatus();
}

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
      toast(e.message, {
        type: "err",
        title: "Couldn't save project token",
      });
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
      toast(e.message, {
        type: "err",
        title: "Couldn't clear project token",
      });
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
      toast(e.message, {
        type: "err",
        title: "Couldn't add repository",
      });
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
  $("#repo-url").oninput = async (e) => {
    const value = e.target.value.trim();
    renderRepoSuggest(value);
    let hostname;
    try {
      // Convert scp-style SSH addresses so URL can extract their host too.
      const ssh = !value.includes("://") && value.match(/^git@([^/:\s]+):/);
      const source = ssh
        ? `ssh://git@${ssh[1]}/${value.slice(ssh[0].length)}`
        : value;
      hostname = new URL(source).hostname.toLowerCase();
    } catch (e) {
      return;
    }
    if (!PD_GITLAB_HOST) await loadSyncStatus();
    if ($("#repo-url").value.trim() !== value) return;
    const provider =
      hostname === PD_GITLAB_HOST ? "gitlab" :
      hostname.replace(/^www\./, "") === "github.com" ? "github" : null;
    if (provider && provider !== PD_PROVIDER) await setProjectProvider(provider);
  };
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
      toast(e.message, {
        type: "err",
        title: "Couldn't load repositories",
      });
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
          <button class="go" style="padding: 6px 12px; font-size: 12px; display: flex; align-items: center; gap: 4px;" onclick="gotoAnalyze('${rp.id}','${currentProject}')">Analyze</button>
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
  // The Code Analysis screen is React (features/code-analysis, #257): it loads
  // the projects and this project's repos with only `rid` ticked.
  if (window.openCodeAnalysisFor) await window.openCodeAnalysisFor(pid, rid);
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
    PD_GITLAB_HOST = s.gitlab_host || null;
    if ($("#sync-status"))
      $("#sync-status").innerHTML =
        `poller every ${s.poll_interval_s}s · ${s.github_authenticated ? "authenticated" : "public-only"} · ingested ${s.ingested}, mapped ${s.mapped}` +
        (s.errors && s.errors.length
          ? ` · <span class="err">${esc(s.errors.slice(-1)[0])}</span>`
          : "");
  } catch (e) {}
}

