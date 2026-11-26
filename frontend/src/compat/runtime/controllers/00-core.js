// Legacy JavaScript — the original vanilla-JS UI. app/static/index.html has been
// removed, so this file (+ legacyShellHtml.js + styles/global.css) is now the
// CANONICAL source of the legacy UI and is hand-maintained.
//
// The original two <script> blocks, concatenated. LegacyApp.jsx imports this file
// with Vite's `?raw` suffix and injects it as a classic <script> element, so it
// runs in GLOBAL scope exactly like the old single-file page. Because of that,
// every top-level `function foo(){}` / `const foo = ...` is reachable from the
// inline on* handlers in the shell markup (e.g. onclick="navigateTo(...)") with
// no window.* shim required.

// Toasts, the confirm / prompt / HTML dialogs and the skeleton placeholders are
// React (components/overlays/modals, lib/skeleton.js, #257); they register
// toast, confirmModal, uiPrompt, uiModalHTML, skeleton, skIn and loadingRow on
// window.

// The branded loader (lib/brandLoader.js) and the priority / steps HTML for Gap
// Analysis (lib/htmlRenderers.js) are registered on window by React (#257). The
// unused report widgets (rc*) and verdict renderers (v*) were removed.

// ----- second <script> block -----

const $ = (s) => document.querySelector(s);
// Escapes &, <, >, " and ' so the result is safe in BOTH element text and quoted
// HTML attribute contexts (e.g. href="...", title="..."). Entities decode back to
// the original characters when rendered, so this is also safe for text nodes.
const esc = (s) =>
  (s ?? "").toString().replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
// Turn raw backend / httpx error strings into a short, human message (used app-wide).
function cleanErr(detail, status) {
  let d = (detail == null ? "" : detail).toString().trim();
  d = d.replace(/\s*For more information check:\s*https?:\/\/\S+/gi, ""); // drop MDN hint
  d = d.replace(/(?:client|server) error '([^']+)' for url '[^']*'/gi, "$1"); // → "404 Not Found"
  d = d.replace(/\s*for url '[^']*'/gi, "");
  d = d
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s*\n\s*/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
  d = d.replace(/[:\s]+$/, "").trim();
  if (d) return d;
  // No useful detail from the server — give a friendly, status-aware fallback.
  const byStatus = {
    400: "That request wasn't valid. Please check your input and try again.",
    404: "We couldn't find what you were looking for.",
    408: "The request timed out. Please try again.",
    409: "That conflicts with something that already exists.",
    413: "The file or payload is too large.",
    422: "Some of the information provided couldn't be processed. Please review and try again.",
    429: "Too many requests — please wait a moment and try again.",
    500: "The server ran into a problem. Please try again in a moment.",
    502: "The server is unreachable right now (bad gateway). Please try again shortly.",
    503: "The service is temporarily unavailable. Please try again shortly.",
    504: "The server took too long to respond. Please try again.",
  };
  return (
    byStatus[status] ||
    `Request failed${status ? ` (${status})` : ""}. Please try again.`
  );
}
async function api(p, o) {
  // NOTE: never log request bodies or response payloads — they can carry PATs,
  // API keys, SMTP passwords, OTP codes and other secrets into the browser console.
  let r, raw;
  try {
    r = await fetch(p, o);
    raw = await r.text();
  } catch (netErr) {
    // Network / server-unreachable — give the user a clear, non-technical message.
    console.error(`[API Net] ${p}`, netErr);
    if (typeof toast === "function")
      toast(
        "Can't reach the server. Check that wardenIQ is running and your connection is active.",
        { type: "err", title: "Connection problem" },
      );
    throw new Error(
      "Can't reach the server — please check your connection and try again.",
    );
  }
  let j = {};
  try {
    j = raw ? JSON.parse(raw) : {};
  } catch (e) {
    j = { detail: raw || `Request failed with status ${r.status}` };
  }
  if (r.status === 401 && !p.startsWith("/api/auth/")) {
    // Includes session invalidation after a role change / disable / forced logout.
    ME = null;
    showLogin();
    if (typeof toast === "function")
      toast(j.detail || "Your session ended — please sign in again.", {
        type: "info",
        title: "Session expired",
      });
    throw new Error(j.detail || "Please sign in");
  }
  if (r.status === 403) {
    // Authorization denial — surface it instead of failing silently, and refresh
    // identity in case the user's role changed under them.
    if (typeof toast === "function")
      toast(j.detail || "You don't have permission to do that.", {
        type: "err",
        title: "Not allowed",
      });
    if (!p.startsWith("/api/auth/"))
      setTimeout(() => {
        try {
          refreshMe();
        } catch (e) {}
      }, 0);
    throw new Error(cleanErr(j.detail || "not permitted", r.status));
  }
  if (!r.ok) {
    throw new Error(cleanErr(j.detail, r.status));
  }
  return j;
}
let currentProject = null,
  currentFeature = null,
  currentFeatureData = null,
  currentFeatureCases = [],
  currentViewName = "dashboard";
const TITLES = {
  dashboard: "Dashboard",
  projects: "Projects & Repos",
  features: "Features",
  validator: "MCQ Validator",
  testplan: "Test Plan",
  cases: "Test Cases",
  gap: "Gap Analysis",
  cycles: "Code Analysis",
  testcycles: "Test Cycles",
  mindmap: "Mind Map",
  develop: "Start Developing",
  steps: "Step Library",
  usage: "LLM Usage & Cost",
  users: "Users",
  config: "Configuration",
};
let ME = null;
// Read-only accessor for React screens (src/lib/compatBridge.js) until the
// navigation state moves out of this file (#257).
function getCurrentProject() {
  return currentProject;
}
function setCurrentProject(id) {
  currentProject = id;
}
function getCurrentFeatureId() {
  return currentFeature;
}
function setCurrentFeature(id) {
  currentFeature = id;
}
function setCurrentFeatureData(f) {
  currentFeatureData = f;
  currentFeatureCases = (f && f.test_cases) || [];
}
// Signed-in user (or null), for React screens until identity moves to React (#257).
function getCurrentUser() {
  return ME;
}
function setCurrentUser(u) {
  ME = u;
}
function getCurrentViewName() {
  return currentViewName;
}

// ---- nav ----
function navigateTo(v) {
  currentViewName = v;
  const sidebarView = ["features", "validator", "testplan"].includes(v)
    ? "projects"
    : v;
  document
    .querySelectorAll("nav button")
    .forEach((x) =>
      x.classList.toggle("active", x.dataset.view === sidebarView),
    );
  document
    .querySelectorAll(".view")
    .forEach((s) => (s.hidden = s.id !== "view-" + v));
  $("#view-title").textContent = TITLES[v] || "";
  if (v === "dashboard") loadDashboard();
  if (v === "projects") {
    showProjectList();
    loadProjects();
    loadSyncStatus();
  }
  if (v === "features") {
    loadProjects();
    loadFeatures();
    if (currentFeature) openFeature(currentFeature);
    else showFeatureList();
  }
  if (v === "cases") initCases();
  if (v === "steps") loadSteps();
  if (v === "cycles") initCycles();
  if (v === "testcycles") initTestCycles();
  if (v === "mindmap") initMindmap();
  if (v === "config") loadConfig();
  if (v === "users") {
    loadProjectPicker();
    loadUsers();
    loadApiTokens();
    loadAudit();
  }
  if (v === "usage") loadUsage();
  if (v === "validator") initValidator();
  if (v === "testplan") initTestPlan();
  if (v === "gap") initGap();
  renderBreadcrumbs();
  updateBackbar();
  // Enforce viewer read-only on the freshly-shown view (now + after async loaders
  // inject their buttons).
  try {
    enforceViewerReadOnly();
    setTimeout(enforceViewerReadOnly, 400);
  } catch (e) {}
  // Remember where the user is so a refresh restores it instead of jumping to Dashboard.
  try {
    history.replaceState(null, "", "#" + v);
  } catch (e) {}
  try {
    localStorage.setItem(
      "wq_nav",
      JSON.stringify({
        view: v,
        project: currentProject,
        feature: currentFeature,
      }),
    );
  } catch (e) {}
}
document
  .querySelectorAll("nav button")
  .forEach((b) => (b.onclick = () => navigateTo(b.dataset.view)));
if ($("#sidebar-toggle"))
  $("#sidebar-toggle").onclick = () => {
    $("#app-shell").classList.toggle("sidebar-collapsed");
    const isCollapsed = $("#app-shell").classList.contains("sidebar-collapsed");
    $("#sidebar-toggle").textContent = isCollapsed ? "›" : "‹";
    $("#sidebar-toggle").setAttribute(
      "title",
      isCollapsed ? "Expand sidebar" : "Collapse sidebar",
    );
  };

function getProjectName(projectId) {
  if (window.allProjects) {
    const p = window.allProjects.find((x) => x.id === projectId);
    if (p) return p.name;
  }
  const activeTitle = $("#active-proj-title")?.textContent;
  if (activeTitle && activeTitle !== "Project") return activeTitle;
  const featTitle = $("#features-page-title")?.textContent;
  if (featTitle && featTitle !== "Features") return featTitle;
  return "Project";
}

window.goToProjects = () => {
  navigateTo("projects");
  showProjectList();
  loadProjects();
};

// "Analyze" on a project settings repo card (moved from 02-projects.js, #257):
// show Code Analysis with only that repo ticked.
window.gotoAnalyze = async (rid, pid) => {
  currentProject = pid;
  document
    .querySelectorAll("nav button")
    .forEach((x) => x.classList.toggle("active", x.dataset.view === "cycles"));
  document
    .querySelectorAll(".view")
    .forEach((s) => (s.hidden = s.id !== "view-cycles"));
  $("#view-title").textContent = TITLES.cycles;
  // The Code Analysis screen is React (features/code-analysis): it loads the
  // projects and this project's repos with only `rid` ticked.
  if (window.openCodeAnalysisFor) await window.openCodeAnalysisFor(pid, rid);
  loadCycles();
  toast("Repo selected — set days & click Analyze changes");
};

window.goToProjectFeatures = () => {
  currentFeature = null;
  navigateTo("features");
  showFeatureList();
};

window.goToFeatureWorkspace = () => {
  if (currentFeature) {
    navigateTo("features");
    openFeature(currentFeature);
  }
};

function renderBreadcrumbs() {
  updateBackbar();
}

function updateBackbar() {
  const bar = $("#backbar"),
    btn = $("#backbar-btn"),
    label = $("#backbar-label");
  if (!bar || !btn || !label) return;
  let show = true,
    text = "",
    handler = null;
  if (currentViewName === "projects" && !$("#project-detail-page")?.hidden) {
    text = "Project settings";
    handler = () => showProjectList();
  } else if (
    currentViewName === "features" &&
    !$("#feature-create-page")?.hidden
  ) {
    text = "Create feature";
    handler = () => showFeatureList();
  } else if (currentViewName === "features" && currentFeature) {
    text = "Feature workspace";
    handler = () => showFeatureList();
  } else if (currentViewName === "features" && currentProject) {
    text = "Features";
    handler = () => {
      navigateTo("projects");
      showProjectList();
      loadProjects();
    };
  } else if (["validator", "testplan", "gap"].includes(currentViewName)) {
    const labels = {
      validator: "Validator",
      testplan: "Test plan",
      gap: "Gap analysis",
    };
    text = labels[currentViewName];
    handler = () => navigateTo("features");
  } else if (currentViewName === "cases" && currentFeature) {
    text = "Test Cases";
    handler = () => navigateTo("features");
  } else {
    show = false;
  }
  bar.classList.toggle("show", show);
  btn.onclick = handler || null;

  if (show) {
    const crumbs = [];
    crumbs.push({
      label: "Projects & Repos",
      action: "goToProjects()",
    });

    if (currentProject) {
      const projName = getProjectName(currentProject);
      const isProjectCurrent =
        currentViewName === "features" &&
        !currentFeature &&
        (!$("#feature-create-page") || $("#feature-create-page").hidden);
      crumbs.push({
        label: projName,
        action: isProjectCurrent ? null : "goToProjectFeatures()",
      });

      if (
        currentViewName === "projects" &&
        !$("#project-detail-page")?.hidden
      ) {
        crumbs.push({ label: "Settings", action: null });
      } else if (
        currentViewName === "features" &&
        !$("#feature-create-page")?.hidden
      ) {
        crumbs.push({ label: "Create feature", action: null });
      } else if (currentFeature) {
        const featName = currentFeatureData?.name || "Feature";
        const isFeatureCurrent = currentViewName === "features";
        crumbs.push({
          label: featName,
          action: isFeatureCurrent ? null : "goToFeatureWorkspace()",
        });

        if (currentViewName === "validator") {
          crumbs.push({ label: "Validator", action: null });
        } else if (currentViewName === "testplan") {
          crumbs.push({ label: "Test plan", action: null });
        } else if (currentViewName === "gap") {
          crumbs.push({ label: "Gap analysis", action: null });
        } else if (currentViewName === "cases") {
          crumbs.push({ label: "Test cases", action: null });
        }
      } else if (currentViewName === "cases") {
        crumbs.push({ label: "Test cases", action: null });
      }
    }

    label.innerHTML = crumbs
      .map((c, i) => {
        const isLast = i === crumbs.length - 1;
        if (isLast) {
          return `<span class="crumb active">${esc(c.label)}</span>`;
        } else {
          return `<span class="crumb clickable" onclick="${c.action}">${esc(c.label)}</span><span class="separator">›</span>`;
        }
      })
      .join("");
  } else {
    label.innerHTML = "";
  }
}

window.clickBreadcrumb = function (stepId) {
  if (stepId === "projects") {
    navigateTo("projects");
  } else if (stepId === "features") {
    if (!currentProject) {
      toast("Please select a project first.");
      return;
    }
    currentFeature = null;
    navigateTo("features");
  } else if (stepId === "workspace") {
    if (!currentProject) {
      toast("Please select a project first.");
      return;
    }
    if (!currentFeature) {
      toast("Please select a feature first.");
      return;
    }
    navigateTo("features");
  }
};

// ---- status ----
// Human-readable Vector Search copy from app/core/bootstrap.py (_SEARCH_REQUIRED_MSG).
// Shown when boot failed but the API still has a raw driver exception in boot.detail.
const BOOT_VECTOR_SEARCH_MSG =
  "wardenIQ requires a MongoDB with Vector Search — it's where embeddings are searched. The database at MONGO_URI doesn't have it. Use MongoDB Atlas (search built in) or a self-managed MongoDB running mongot, then restart.";
// Allowlist of KNOWN-SAFE, canned messages (all authored by app/core/bootstrap.py —
// see _SEARCH_REQUIRED_MSG, _SEARCH_INDEX_LIMIT_MSG, and the insecure-secret /
// insecure-production-posture messages in _check_app_secret / _check_production_posture).
// Anything NOT in this list is treated as potentially-raw backend/driver text and kept
// out of the primary summary (see looksLikeRawBootDetail below).
const BOOT_SAFE_DETAIL_MARKERS = [
  "requires a MongoDB with Vector Search",
  "doesn't allow enough search indexes",
  "insecure APP_SECRET",
  "insecure production configuration",
];

// Deliberately an ALLOWLIST, not a blocklist: boot.detail can carry an arbitrary
// exception from any driver/library in the backend's call stack (pymongo, the OS
// resolver, mongot, …), and that space is unbounded — a blocklist of known raw-dump
// signatures (msgLen/ProtocolError/pymongo/etc.) will always be one exception shape
// behind (confirmed in practice: a plain `pymongo.errors.ConfigurationError` DNS
// failure matched none of the old signatures and was shown verbatim as the primary
// banner text). The set of SAFE messages, by contrast, is small and entirely owned
// by this app (BOOT_SAFE_DETAIL_MARKERS above) — enumerating what we trust is
// tractable in a way enumerating what we don't trust never is. So: safe only if it
// matches a known canned message; everything else stays behind the Details
// disclosure, regardless of whether it happens to look like a "recognizable" dump.
function looksLikeRawBootDetail(detail) {
  const d = String(detail || "");
  if (!d) return false;
  return !BOOT_SAFE_DETAIL_MARKERS.some((m) => d.includes(m));
}

function formatBootStatus(boot) {
  boot = boot || {};
  const stage = String(boot.stage || "");
  const detail = String(boot.detail || "");
  if (boot.ready) return { visible: false, kind: "ok", summary: "", raw: "" };

  const raw = looksLikeRawBootDetail(detail) ? detail : "";
  const safeDetail = raw ? "" : detail;

  if (stage === "error") {
    return {
      visible: true,
      kind: "error",
      summary: safeDetail || BOOT_VECTOR_SEARCH_MSG,
      raw,
    };
  }
  if (stage === "indexing") {
    return {
      visible: true,
      kind: "warn",
      summary: "Setting up Vector Search indexes…",
      raw: detail,
    };
  }
  if (stage === "connecting") {
    return {
      visible: true,
      kind: "warn",
      summary: "Connecting to MongoDB…",
      raw: detail,
    };
  }
  return {
    visible: true,
    kind: "warn",
    summary: stage ? `Starting up (${stage})` : "Starting up…",
    raw: raw || "",
  };
}

function bootBannerDetailsHtml(raw) {
  if (!raw) return "";
  return (
    `<details class="boot-banner-details">` +
    `<summary>Details</summary>` +
    `<pre class="boot-banner-raw">${esc(raw)}</pre>` +
    `</details>`
  );
}

function applyBootBanner(formatted) {
  const el = $("#boot-banner");
  if (!el) return;
  if (!formatted || !formatted.visible) {
    el.hidden = true;
    el.innerHTML = "";
    el.removeAttribute("data-kind");
    return;
  }
  el.hidden = false;
  el.dataset.kind = formatted.kind || "warn";
  if (formatted.raw) {
    try {
      console.warn("[wardenIQ] boot detail:", formatted.raw);
    } catch (e) {}
  }
  const icon = formatted.kind === "error" ? "⚠" : "●";
  el.innerHTML =
    `<span class="boot-banner-msg">${icon} ${esc(formatted.summary)}</span>` +
    bootBannerDetailsHtml(formatted.raw);
}

async function refreshStatus() {
  if ($("#status") && !$("#status").dataset.loaded)
    $("#status").innerHTML =
      `<span class="stat"><span class="spin-inline"></span>Checking services…</span>`;
  try {
    const s = await api("/api/status");
    const c = s.counts || {};
    if ($("#status")) $("#status").dataset.loaded = "1";
    // Keep #status to compact service chips only — long boot copy belongs in
    // the in-flow #boot-banner so it cannot overlay the sticky header chrome.
    $("#status").innerHTML =
      `<span class="status-group">` +
      `<span class="stat" title="MongoDB connection">${dot(s.mongo_connected)}Mongo</span>` +
      `<span class="stat" title="Embeddings: ${esc(s.embedding?.provider || "")}${s.embedding?.dims ? " · " + s.embedding.dims + "-d" : ""}${s.embedding?.health?.error ? " · " + s.embedding.health.error : ""}">${dot(s.embedding?.health?.ok)}${esc(s.embedding?.model)}</span>` +
      `<span class="stat" title="LLM: ${esc(s.llm?.health?.error || s.llm?.provider || "")}">${dot(s.llm?.health?.ok)}${esc(s.llm?.model)}</span>` +
      `</span>` +
      `<span class="stat-metric" title="Features and test cases in scope"><span><b>${c.features || 0}</b> features</span><span class="sep"></span><span><b>${c.test_cases || 0}</b> cases</span></span>`;
    applyBootBanner(formatBootStatus(s.boot));
  } catch (e) {
    const raw = e && e.message ? String(e.message) : "";
    applyBootBanner({
      visible: true,
      kind: "error",
      summary: looksLikeRawBootDetail(raw)
        ? "Can't load service status right now."
        : raw || "Can't load service status right now.",
      raw: looksLikeRawBootDetail(raw) ? raw : "",
    });
    if ($("#status") && !$("#status").dataset.loaded) {
      $("#status").innerHTML = `<span class="stat">${dot(false)}Status unavailable</span>`;
    }
  }
}
const dot = (ok) => `<span class="dot ${ok ? "ok" : "bad"}"></span>`;

