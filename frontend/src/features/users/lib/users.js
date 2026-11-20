/**
 * Pure logic for the Users screen (invite form, users list, audit log), ported
 * from the compat 11-users.js. Unit-tested in frontend/tests/users.test.js.
 */
import { escapeHtml } from "../../../lib/html.js";

export const ROLES = ["viewer", "editor", "admin"];
export const MSG_EMAIL_REQUIRED = "Email required";
export const MSG_SELECT_PROJECT = "Select at least one project, or choose All projects.";
export const NO_PROJECTS_TEXT = "No projects yet — create one first, or grant access to all.";

/** Hint under the invite form's project access. Initial text is the admin one, as before. */
export const HINT_ADMIN = "Admins always have access to all projects.";
export function inviteHint(role, mode) {
  if (role === "admin") return HINT_ADMIN;
  return mode === "some"
    ? "Select the projects this user can access."
    : "This user will have access to every project.";
}

/** Project scope for an invite: admins and "All projects" get every project. */
export function inviteScope(role, mode, selectedIds) {
  if (role === "admin" || mode !== "some") return { all_projects: true, project_ids: [] };
  return { all_projects: false, project_ids: [...(selectedIds || [])] };
}

/** First validation message for the invite form, or null. */
export function validateInvite(email, scope) {
  if (!(email || "").trim()) return MSG_EMAIL_REQUIRED;
  if (!scope.all_projects && scope.project_ids.length === 0) return MSG_SELECT_PROJECT;
  return null;
}

/** True when an invite/resend response says the email was not delivered. */
export const deliveryFailed = (r) => !!r && (r.delivery === "refused" || r.delivery === "error");

/** Users-list filters (search text, status, role). */
export function matchesFilters(u, { q = "", status = "", role = "" } = {}) {
  const query = q.trim().toLowerCase();
  if (
    query &&
    !((u.email || "").toLowerCase().includes(query) || (u.name || "").toLowerCase().includes(query))
  )
    return false;
  if (role && u.role !== role) return false;
  if (status) {
    const pending = u.invite_status === "pending";
    if (status === "pending" && !pending) return false;
    if (status === "active" && (pending || !u.active)) return false;
    if (status === "disabled" && (pending || u.active)) return false;
  }
  return true;
}

/** Access column: { kind: "admin" | "all" | "none" | "projects", names? }. */
export function userAccess(u, projects) {
  if (u.role === "admin") return { kind: "admin" };
  if (u.all_projects) return { kind: "all" };
  const ids = u.project_ids || [];
  if (!ids.length) return { kind: "none" };
  return {
    kind: "projects",
    names: ids.map((id) => {
      const p = (projects || []).find((x) => x.id === id);
      return p ? p.name || p.id : id;
    }),
  };
}

/** Status badge: "pending" | "active" | "disabled". */
export function userStatus(u) {
  if (u.invite_status === "pending") return "pending";
  return u.active ? "active" : "disabled";
}

export function lastLoginText(u) {
  if (u.last_login) return new Date(u.last_login * 1000).toLocaleString();
  return u.invite_status === "pending" ? "awaiting first sign-in" : "never";
}

/**
 * Row actions, in order: "access" (non-admins), then "resend" + "cancel" for
 * a pending invite; "unlock" when you are the only active admin; otherwise
 * "enable" / "disable", plus "delete" unless the row is you.
 */
export function rowActions(u, { selfId, activeAdmins }) {
  const self = selfId != null && selfId === u.id;
  const out = u.role === "admin" ? [] : ["access"];
  if (u.invite_status === "pending") return [...out, "resend", "cancel"];
  if (self && u.role === "admin" && u.active && activeAdmins <= 1) return [...out, "unlock"];
  out.push(u.active ? "disable" : "enable");
  if (!self) out.push("delete");
  return out;
}

export const countActiveAdmins = (users) =>
  users.filter((x) => x.role === "admin" && x.active).length;

export function roleChangeMessage(who, role, description) {
  // The name is HTML-escaped exactly as the compat code did.
  return `Change ${escapeHtml(who)}'s role to "${role}"?${description ? ` ${description}` : ""} They'll be re-authenticated with the new permissions.`;
}

/** Audit details: the server's detail, else "from {old} to {new}". */
export function auditDetail(l) {
  return (
    l.detail ||
    [l.old && `from ${JSON.stringify(l.old)}`, l.new && `to ${JSON.stringify(l.new)}`]
      .filter(Boolean)
      .join(" ")
  );
}
export const auditDanger = (action) => /deleted|denied|disabled/.test(action || "");
export function auditTime(ts) {
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return "";
  }
}

/**
 * Body of the "Project access" dialog (shared uiModalHTML). The ma-* names and
 * ids are wired by uiModalHTML in 00-core.js (scope toggle, search) and read
 * back by readAccessDialog(), so they must not change.
 */
export function accessDialogHtml(u, projects) {
  const cur = new Set(u.all_projects ? [] : u.project_ids || []);
  const rows =
    (projects || [])
      .map(
        (p) =>
          `<label data-name="${escapeHtml((p.name || p.id).toLowerCase())}" style="display:flex;gap:8px;align-items:center;padding:4px 0"><input type="checkbox" data-pid="${escapeHtml(p.id)}" ${cur.has(p.id) ? "checked" : ""}/> ${escapeHtml(p.name || p.id)}</label>`,
      )
      .join("") || '<span class="muted">No projects exist yet.</span>';
  return `<div style="margin-bottom:8px"><label class="radio-inline"><input type="radio" name="ma-scope" value="all" ${u.all_projects ? "checked" : ""}/> All projects</label>
    <label class="radio-inline" style="margin-left:16px"><input type="radio" name="ma-scope" value="some" ${u.all_projects ? "" : "checked"}/> Specific</label></div>
    <input id="ma-search" type="search" placeholder="Search projects…" ${u.all_projects ? "hidden" : ""} style="width:100%;margin-bottom:8px"/>
    <div id="ma-list" ${u.all_projects ? "hidden" : ""} style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:10px">${rows}</div>`;
}

/** Read the scope back from the (still open in the DOM) "Project access" dialog. */
export function readAccessDialog(doc) {
  const mode = (doc.querySelector('input[name="ma-scope"]:checked') || {}).value || "all";
  const all_projects = mode === "all";
  const project_ids = all_projects
    ? []
    : [...doc.querySelectorAll("#ma-list input[data-pid]:checked")].map((c) =>
        c.getAttribute("data-pid"),
      );
  return { all_projects, project_ids };
}

export const HANDOFF_HTML = `<p style="margin:0 0 10px">You're the <b>only admin</b> for this workspace, so disabling your own
    access isn't allowed — that would lock everyone out.</p>
  <p class="muted" style="font-size:12.5px;margin:0">Assign another email address as admin first. Once they accept
    the invite and sign in, you'll be able to disable (or hand off) this local admin account.</p>`;
