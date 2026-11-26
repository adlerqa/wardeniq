/**
 * Role / identity helpers (was the identity half of
 * compat/runtime/controllers/10-auth.js).
 *
 * applyRoleDom, enforceViewerReadOnly and applyRoleTooltips sweep the whole
 * document — sidebar, compat markup and React screens alike — so they stay
 * DOM utilities rather than component state.
 */

export const VIEWER_TIP = "Read-only — your Viewer role can't make changes. Ask an admin for Editor access.";

/** Labels that look like a write action (and aren't a harmless one). */
export const VIEWER_WRITE_RE =
  /\b(create|add|new|save|delete|remove|edit|generate|regenerate|import|invite|run|start|associate|assign|reassign|sync|rescan|watch|apply|submit|upload|clear|reset|link|unlink|promote|export)\b/i;
export const VIEWER_SKIP_RE =
  /\b(cancel|close|back|search|filter|view|open|download|refresh|copy|sign out|logout|use a different|expand|collapse|show|hide|next|prev|previous)\b/i;

export const roleOf = (user) => (user && user.role) || "viewer";

/** Explain why a control is disabled, on hover, for restricted roles. */
export function applyRoleTooltips(role, doc = document) {
  const msg = role === "viewer" ? VIEWER_TIP : "";
  doc.querySelectorAll(".needs-editor").forEach((el) => {
    if (role === "viewer") {
      if (!el.dataset._t) {
        el.dataset._t = el.getAttribute("title") || "";
      }
      el.setAttribute("title", msg);
    } else if (el.dataset._t !== undefined) {
      if (el.dataset._t) el.setAttribute("title", el.dataset._t);
      else el.removeAttribute("title");
    }
  });
}

/**
 * Viewer read-only mode: many write buttons aren't tagged .needs-editor, so
 * mark the ones whose label looks like a write action (the shared CSS dims and
 * disables them). Idempotent; run after every view render and async load.
 */
export function enforceViewerReadOnly(user, doc = document) {
  const isViewer = (user && user.role) === "viewer";
  const scope = doc.querySelector(".view:not([hidden])") || doc;
  scope.querySelectorAll("button").forEach((b) => {
    const label = (b.textContent || b.getAttribute("aria-label") || b.title || "").trim();
    if (!label) return;
    if (!(VIEWER_WRITE_RE.test(label) && !VIEWER_SKIP_RE.test(label))) return;
    b.classList.add("needs-editor");
  });
  applyRoleTooltips(isViewer ? "viewer" : (user && user.role) || "viewer", doc);
}

/**
 * Role-dependent page state outside the header: body role classes, admin-only
 * nav entries, the read-only banner and the tooltips; shows the user menu.
 */
export function applyRoleDom(user, doc = document) {
  const role = roleOf(user);
  const menu = doc.getElementById("usermenu");
  if (menu) menu.hidden = false;
  doc.body.classList.toggle("role-viewer", role === "viewer");
  doc.body.classList.toggle("role-editor", role === "editor");
  const admin = role === "admin";
  doc.querySelectorAll("nav button[data-admin]").forEach((b) => (b.hidden = !admin));
  const rob = doc.getElementById("ro-banner");
  if (rob) rob.hidden = role !== "viewer";
  applyRoleTooltips(role, doc);
}

/** "Change password" is only for the local admin account (email "admin"); others sign in by code. */
export const canChangePassword = (user) => !!(user && user.email === "admin");

/** First problem with a change-password form, or "". */
export function passwordProblem(current, next, confirm) {
  if (!current) return "Enter your current password.";
  if (!next) return "Enter a new password.";
  if (next !== confirm) return "New passwords don't match.";
  return "";
}

/** Invite date (unix seconds) as "1 Jan 2026" in the browser's locale, or "". */
export function fmtDate(ts) {
  try {
    return ts ? new Date(ts * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "";
  } catch {
    return "";
  }
}

/** The invite banner's rows: [label, { text } | { role }]. */
export function inviteRows(inv) {
  const by = inv.invited_by;
  const email = by ? (by.email ?? "") : "";
  const byLabel = by ? (by.name ? `${by.name} (${email})` : email) : "an administrator";
  return [
    ["Invited by", { text: byLabel }],
    ["Workspace", { text: inv.workspace || "WardenIQ" }],
    ["Role granted", { role: inv.role ?? "" }],
    ["Sent", { text: fmtDate(inv.invited_at) || "—" }],
  ];
}
