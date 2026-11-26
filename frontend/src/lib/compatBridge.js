/**
 * Thin bridge from React code to the shared UI helpers that still live in the
 * compatibility runtime (src/compat/runtime/controllers/00-core.js) or that
 * React screens register on window.
 *
 * The runtime is injected as one classic <script>, so its top-level function
 * declarations (toast, uiConfirm, uiModalHTML, showLogin, refreshMe) are
 * properties of `window`. React components call them through this module
 * instead of reaching into `window` directly, so that:
 *   - there is one place to swap each helper for a React component later;
 *   - a missing helper (runtime not loaded yet, or unit tests) degrades to a
 *     no-op / console fallback instead of throwing.
 *
 * Do not add new behaviour here. When a helper is ported to React, point the
 * matching function at the React version and delete the window lookup.
 */

function compatFn(name) {
  const fn = typeof window !== "undefined" ? window[name] : undefined;
  return typeof fn === "function" ? fn : null;
}

/** toast(message, isErr | {type, title, duration}) (React ToastHost). */
export function toast(message, options) {
  const fn = compatFn("toast");
  if (fn) return fn(message, options);
  const isErr = options === true || (options && options.type === "err");
  (isErr ? console.error : console.info)(String(message));
}

/** Resolves true when confirmed, false when cancelled (window.uiConfirm, React CaseConfirmationModal). */
export function uiConfirm(message, title, confirmLabel, danger) {
  const fn = compatFn("uiConfirm");
  if (fn) return fn(message, title, confirmLabel, danger);
  return Promise.resolve(false);
}

/**
 * Opens the shared HTML modal (React HtmlModal). `bodyHTML` is inserted
 * as HTML: escape every interpolated value (see escapeHtml in lib/html.js).
 */
export function uiModalHTML(title, bodyHTML, confirmLabel) {
  const fn = compatFn("uiModalHTML");
  if (fn) return fn(title, bodyHTML, confirmLabel);
  return Promise.resolve(false);
}

/** Shows the sign-in screen and clears the signed-in user (React, features/auth/hooks/useLogin.js). */
export function showLogin(options) {
  const fn = compatFn("showLogin");
  if (fn) return fn(options);
}

/** The view on screen (00-core.js `currentViewName`), e.g. "dashboard". */
export function currentViewName() {
  const fn = compatFn("getCurrentViewName");
  return fn ? fn() : "dashboard";
}

/** Opens the change-password dialog; resolves true once saved (React PasswordModal). */
export function openChangePasswordModal(mandatory) {
  const fn = compatFn("openChangePasswordModal");
  return fn ? fn(mandatory) : Promise.resolve(false);
}

/** Sets the signed-in user known to the compat runtime (00-core.js `ME`). */
export function setCurrentUser(user) {
  const fn = compatFn("setCurrentUser");
  if (fn) fn(user);
}

/** Re-reads the signed-in user, e.g. after a 403 (React, features/auth/hooks/useIdentity.js). */
export function refreshMe() {
  const fn = compatFn("refreshMe");
  if (fn) return fn();
}

/** Id of the feature open in the compat runtime (00-core.js `currentFeature`), or null. */
export function currentFeatureId() {
  const fn = compatFn("getCurrentFeatureId");
  return fn ? fn() || null : null;
}

/**
 * Name shown in the feature workspace header (#d-name, filled by
 * 03-features-and-usage.js). Screens that title themselves after the open
 * feature read it here, as the compat controllers did.
 */
export function currentFeatureName() {
  if (typeof document === "undefined") return "";
  const el = document.getElementById("d-name");
  return el ? el.textContent || "" : "";
}

/**
 * Follow a background job (lib/jobs.js watchJob: SSE plus a safety poll).
 * Calls onTick(job) on every update; returns a stop function. Not registered
 * (unit tests): a no-op stop.
 */
export function watchJob(jobId, onTick, intervalMs) {
  const fn = compatFn("watchJob");
  return fn ? fn(jobId, onTick, intervalMs) || (() => {}) : () => {};
}

/** Token-usage lines appended to a job log (lib/jobs.js). */
export function usageLogLines(usage) {
  const fn = compatFn("usageLogLines");
  return fn ? fn(usage) : [];
}

/** The signed-in user ({ id, email, role, ... }) known to the compat runtime, or null. */
export function currentUser() {
  const fn = compatFn("getCurrentUser");
  return fn ? fn() || null : null;
}

/** Description of a role from the optional global RBAC table, or "". */
export function roleDescription(role) {
  const rbac = typeof window !== "undefined" ? window.RBAC : undefined;
  return (rbac && rbac.DESC && rbac.DESC[role]) || "";
}

/**
 * Open a test case in its feature workspace (was openAndGoToCase in
 * 05-step-workflows.js): open the feature, switch to the Features screen, then
 * open the case and scroll to it.
 */
export async function openCaseInFeature(caseId, featureId) {
  const openFeature = compatFn("openFeature");
  const navigateTo = compatFn("navigateTo");
  const viewCase = compatFn("viewCase"); // registered by the React workspace
  if (openFeature) await openFeature(featureId);
  if (navigateTo) navigateTo("features");
  setTimeout(() => {
    if (viewCase) viewCase(caseId);
    const el = document.querySelector(`[data-case-item="${caseId}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, 300);
}

/**
 * Refresh the project list (window.loadProjects, registered by the React
 * Projects screen: sets window.allProjects and the runtime project, fills the
 * Features screen's picker) and return the projects. Resolves to [] when it
 * is not registered.
 */
export async function loadProjects() {
  const fn = compatFn("loadProjects");
  if (fn) await fn();
  const list = typeof window !== "undefined" ? window.allProjects : undefined;
  return Array.isArray(list) ? list : [];
}



/** Delete / unlink a test case after confirming (window.requestDeleteCase, React case editor). */
export function requestDeleteCase(caseId) {
  const fn = compatFn("requestDeleteCase");
  if (fn) return fn(caseId);
}


/** Id of the project selected in the compat runtime (00-core.js `currentProject`), or null. */
export function currentProjectId() {
  const fn = compatFn("getCurrentProject");
  return fn ? fn() || null : null;
}

/** Re-open a feature in the workspace so new / removed cases show (window.openFeature, React workspace). */
export function openFeature(featureId) {
  const fn = compatFn("openFeature");
  if (fn) return fn(featureId);
}

/** Reload the feature list (window.loadFeatures, React Features). */
export function loadFeatures() {
  const fn = compatFn("loadFeatures");
  if (fn) return fn();
}

/**
 * The shared case confirmation dialog (window.openCaseConfirmation, React CaseConfirmationModal):
 * { title, copy, summary (HTML — escape it), confirmLabel, danger, onConfirm }.
 * An error thrown by onConfirm is shown inside the dialog.
 */
export function openCaseConfirmation(options) {
  const fn = compatFn("openCaseConfirmation");
  if (fn) return fn(options);
}

/**
 * The shared confirm dialog (React ConfirmationModal):
 * { title, body, confirmText, danger } → Promise<boolean>.
 */
export function confirmModal(options) {
  const fn = compatFn("confirmModal");
  return fn ? fn(options) : Promise.resolve(false);
}

/** The shared one-line prompt dialog (React, modals/ProjectAccessModal.jsx) → Promise<string | null>. */
export function uiPrompt(title, label, value) {
  const fn = compatFn("uiPrompt");
  return fn ? fn(title, label, value) : Promise.resolve(null);
}

/** Write a job's progress log into the element matching `selector` (lib/jobs.js). */
export function renderJobLog(selector, job) {
  const fn = compatFn("renderJobLog");
  if (fn) return fn(selector, job);
}

/** Refresh the project settings sync status line (window.loadSyncStatus, React Projects screen). */
export function loadSyncStatus() {
  const fn = compatFn("loadSyncStatus");
  if (fn) return fn();
}

/** Startup / database status as { kind, summary, raw } (00-core.js formatBootStatus). */
export function formatBootStatus(boot) {
  const fn = compatFn("formatBootStatus");
  return fn ? fn(boot) : { visible: false, kind: "ok", summary: "", raw: "" };
}

/** Select a project in the compat runtime (00-core.js `currentProject`). */
export function setCurrentProject(projectId) {
  const fn = compatFn("setCurrentProject");
  if (fn) fn(projectId);
}

/** Open the case editor on a case (window.editCase, React TestCaseEditorModal). */
export function editCase(caseId) {
  const fn = compatFn("editCase");
  if (fn) return fn(caseId);
}

/** Open the case editor for a new case in a feature that also joins a test cycle (window.openNewCaseInCycle). */
export function openNewCaseInCycle(featureId, cycleId) {
  const fn = compatFn("openNewCaseInCycle");
  if (fn) return fn(featureId, cycleId);
}

/** Read-only info dialog (window.openInfoDialog, React CaseConfirmationModal): { title, copy, summary (HTML — escape it) }. */
export function openInfoDialog(options) {
  const fn = compatFn("openInfoDialog");
  if (fn) return fn(options);
}

/** Open a project's feature list (React, features/features/hooks/useFeatures.js). */
export function openProjectFeatures(projectId) {
  const fn = compatFn("openProjectFeatures");
  if (fn) return fn(projectId);
}

/** The project's feature list, from project settings (00-core.js goToProjectFeatures). */
export function goToProjectFeatures() {
  const fn = compatFn("goToProjectFeatures");
  if (fn) return fn();
}

/** Give the Features screen the project list and current project (window.syncFeatureProjects, React Features). */
export function syncFeatureProjects(projects, currentId) {
  const fn = compatFn("syncFeatureProjects");
  if (fn) return fn(projects, currentId);
}

/** Redraw the backbar / breadcrumbs (00-core.js updateBackbar). */
export function updateBackbar() {
  const fn = compatFn("updateBackbar");
  if (fn) return fn();
}

/** Refresh the header service status chips (00-core.js refreshStatus). */
export function refreshStatus() {
  const fn = compatFn("refreshStatus");
  if (fn) return fn();
}

/** Open Code Analysis on a repo of a project (00-core.js gotoAnalyze). */
export function gotoAnalyze(repoId, projectId) {
  const fn = compatFn("gotoAnalyze");
  if (fn) return fn(repoId, projectId);
}

/** Select a feature in the compat runtime (00-core.js `currentFeature`); null clears it. */
export function setCurrentFeature(featureId) {
  const fn = compatFn("setCurrentFeature");
  if (fn) fn(featureId);
}

/** The Projects screen, reloaded (00-core.js goToProjects). */
export function goToProjects() {
  const fn = compatFn("goToProjects");
  if (fn) return fn();
}

/** The import-sheet dialog for a feature (window.importSheetForFeature, React Imports). */
export function importSheetForFeature(featureId, projectId) {
  const fn = compatFn("importSheetForFeature");
  if (fn) return fn(featureId, projectId);
}

/** Open the case editor for a new case in a feature (window.openNewCase, React TestCaseEditorModal). */
export function openNewCase(featureId) {
  const fn = compatFn("openNewCase");
  if (fn) return fn(featureId);
}

/** Keep the runtime's open-feature data in step (00-core.js currentFeatureData / currentFeatureCases). */
export function setCurrentFeatureData(feature) {
  const fn = compatFn("setCurrentFeatureData");
  if (fn) fn(feature);
}

/** The "Reuse imported" dialog for a feature (window.openImportLibraryModal, React Imports). */
export function openImportLibraryModal(featureId) {
  const fn = compatFn("openImportLibraryModal");
  if (fn) return fn(featureId);
}

/** The "Upload new version" dialog (window.openNewVersionModal, React ValidatorModal). */
export function openNewVersionModal(featureId, label) {
  const fn = compatFn("openNewVersionModal");
  if (fn) return fn(featureId, label);
}

/** The branded loader markup (00-core.js brandLoader), as an HTML string. */
export function brandLoaderHtml(variant, options) {
  const fn = compatFn("brandLoader");
  return fn ? fn(variant, options) : "";
}

/** Switch the main view (00-core.js navigateTo). */
export function navigateTo(view) {
  const fn = compatFn("navigateTo");
  if (fn) return fn(view);
}

/** "Test Cases" from a feature page: the Test Cases screen scoped to the open feature. */
export async function openFeatureTestCases() {
  const fid = currentFeatureId();
  if (!fid) return;
  navigateTo("cases");
  // The Test Cases screen is React (features/test-cases).
  if (typeof window.openTestCasesFor === "function") await window.openTestCasesFor(fid, currentProjectId() || "");
}
