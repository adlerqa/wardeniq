/**
 * Navigation between screens (was compat/runtime/controllers/00-core.js):
 * navigateTo, the back bar / breadcrumbs model, and the goTo* shortcuts the
 * breadcrumbs and screens use. Screens are reached through the functions they
 * register on window (loadDashboard, initCases, …). Showing a view toggles the
 * `.view` sections' hidden flag, as before. useNavigation.js registers these.
 */
import { nav } from "./navState.js";
import { toast } from "../lib/compatBridge.js";

const callWindow = (name, ...args) => (typeof window[name] === "function" ? window[name](...args) : undefined);

export const TITLES = {
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

// Back bar model listener (useNavigation's state setter).
let publishBackbar = () => {};
export const onBackbar = (fn) => {
  publishBackbar = fn;
  return () => {
    if (publishBackbar === fn) publishBackbar = () => {};
  };
};

/** Highlight the sidebar entry and show only the view's section. */
function showView(sidebarView, v) {
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("active", x.dataset.view === sidebarView));
  document.querySelectorAll(".view").forEach((s) => (s.hidden = s.id !== "view-" + v));
  nav.setTitle(TITLES[v] || "");
}

/** Show a screen and run its loader; remembers it for the next visit (#hash, wq_nav). */
export function navigateTo(v) {
  nav.setView(v);
  showView(["features", "validator", "testplan"].includes(v) ? "projects" : v, v);
  const { feature } = nav.get();
  if (v === "dashboard") callWindow("loadDashboard");
  if (v === "projects") {
    callWindow("showProjectList");
    callWindow("loadProjects");
    callWindow("loadSyncStatus");
  }
  if (v === "features") {
    callWindow("loadProjects");
    callWindow("loadFeatures");
    if (feature) callWindow("openFeature", feature);
    else callWindow("showFeatureList");
  }
  if (v === "cases") callWindow("initCases");
  if (v === "steps") callWindow("loadSteps");
  if (v === "cycles") callWindow("initCycles");
  if (v === "testcycles") callWindow("initTestCycles");
  if (v === "mindmap") callWindow("initMindmap");
  if (v === "config") callWindow("loadConfig");
  if (v === "users") {
    callWindow("loadProjectPicker");
    callWindow("loadUsers");
    callWindow("loadApiTokens");
    callWindow("loadAudit");
  }
  if (v === "usage") callWindow("loadUsage");
  if (v === "validator") callWindow("initValidator");
  if (v === "testplan") callWindow("initTestPlan");
  if (v === "gap") callWindow("initGap");
  updateBackbar();
  // Viewer read-only on the new view, now and after async loaders add buttons.
  try {
    callWindow("enforceViewerReadOnly");
    setTimeout(() => callWindow("enforceViewerReadOnly"), 400);
  } catch {
    /* best-effort */
  }
  try {
    history.replaceState(null, "", "#" + v);
  } catch {
    /* history unavailable */
  }
  try {
    const s = nav.get();
    localStorage.setItem("wq_nav", JSON.stringify({ view: v, project: s.project, feature: s.feature }));
  } catch {
    /* storage unavailable */
  }
}

/** Project name for the breadcrumbs: the project list, else the screen titles. */
export function getProjectName(projectId) {
  if (window.allProjects) {
    const p = window.allProjects.find((x) => x.id === projectId);
    if (p) return p.name;
  }
  const activeTitle = document.getElementById("active-proj-title")?.textContent;
  if (activeTitle && activeTitle !== "Project") return activeTitle;
  const featTitle = document.getElementById("features-page-title")?.textContent;
  if (featTitle && featTitle !== "Features") return featTitle;
  return "Project";
}

export function goToProjects() {
  navigateTo("projects");
  callWindow("showProjectList");
  callWindow("loadProjects");
}

/** "Analyze" on a project settings repo card: Code Analysis with only that repo ticked. */
export async function gotoAnalyze(rid, pid) {
  nav.setProject(pid);
  showView("cycles", "cycles");
  if (window.openCodeAnalysisFor) await window.openCodeAnalysisFor(pid, rid);
  callWindow("loadCycles");
  toast("Repo selected — set days & click Analyze changes");
}

export function goToProjectFeatures() {
  nav.setFeature(null);
  navigateTo("features");
  callWindow("showFeatureList");
}

export function goToFeatureWorkspace() {
  const { feature } = nav.get();
  if (feature) {
    navigateTo("features");
    callWindow("openFeature", feature);
  }
}

/** Breadcrumb steps: "projects" | "features" | "workspace". */
export function clickBreadcrumb(stepId) {
  const { project, feature } = nav.get();
  if (stepId === "projects") {
    navigateTo("projects");
  } else if (stepId === "features") {
    if (!project) {
      toast("Please select a project first.");
      return;
    }
    nav.setFeature(null);
    navigateTo("features");
  } else if (stepId === "workspace") {
    if (!project) {
      toast("Please select a project first.");
      return;
    }
    if (!feature) {
      toast("Please select a feature first.");
      return;
    }
    navigateTo("features");
  }
}

// As before, a page that isn't in the DOM counts as shown.
const shown = (id) => !document.getElementById(id)?.hidden;

/**
 * Back bar + breadcrumbs for where the user is: { show, onBack, crumbs: [{ label, onClick }] }.
 * Reads which project / feature page is on screen, so callers redraw it after a page switch.
 */
export function backbarModel() {
  const { view, project, feature, featureData } = nav.get();
  let show = true,
    onBack = null;
  if (view === "projects" && shown("project-detail-page")) {
    onBack = () => callWindow("showProjectList");
  } else if (view === "features" && shown("feature-create-page")) {
    onBack = () => callWindow("showFeatureList");
  } else if (view === "features" && feature) {
    onBack = () => callWindow("showFeatureList");
  } else if (view === "features" && project) {
    onBack = () => goToProjects();
  } else if (["validator", "testplan", "gap"].includes(view)) {
    onBack = () => navigateTo("features");
  } else if (view === "cases" && feature) {
    onBack = () => navigateTo("features");
  } else {
    show = false;
  }
  if (!show) return { show, onBack, crumbs: [] };

  const crumbs = [{ label: "Projects & Repos", onClick: goToProjects }];
  if (project) {
    const createPage = document.getElementById("feature-create-page");
    const isProjectCurrent = view === "features" && !feature && (!createPage || createPage.hidden);
    crumbs.push({ label: getProjectName(project), onClick: isProjectCurrent ? null : goToProjectFeatures });
    if (view === "projects" && shown("project-detail-page")) {
      crumbs.push({ label: "Settings", onClick: null });
    } else if (view === "features" && shown("feature-create-page")) {
      crumbs.push({ label: "Create feature", onClick: null });
    } else if (feature) {
      crumbs.push({
        label: featureData?.name || "Feature",
        onClick: view === "features" ? null : goToFeatureWorkspace,
      });
      const last = { validator: "Validator", testplan: "Test plan", gap: "Gap analysis", cases: "Test cases" }[view];
      if (last) crumbs.push({ label: last, onClick: null });
    } else if (view === "cases") {
      crumbs.push({ label: "Test cases", onClick: null });
    }
  }
  return { show, onBack, crumbs };
}

/** Redraw the back bar (after navigation or a project / feature page switch). */
export function updateBackbar() {
  publishBackbar(backbarModel());
}
