/**
 * Pure logic for the API tokens panel (components/ApiTokensPanel.jsx).
 * No DOM or network access, so it is unit-tested with node --test
 * (frontend/tests/api-tokens.test.js).
 */
import { escapeHtml } from "../../../lib/html.js";

export const MSG_NAME_REQUIRED = "Name required";
export const MSG_SELECT_PROJECT =
  "Select at least one project, or choose All projects.";
export const EMPTY_TEXT =
  "No API tokens yet. Create one above for a CI job or other machine caller.";
export const NO_PROJECTS_TEXT =
  "No projects yet — create one first, or grant access to all.";

/**
 * What the Access column shows for a token:
 *   { kind: "all" }                 → "All projects"
 *   { kind: "none" }                → "No projects" (red)
 *   { kind: "projects", names: [] } → one chip per project (name, or id when
 *                                     the project is not in `projects`)
 */
export function tokenAccess(token, projects) {
  if (token.all_projects) return { kind: "all" };
  const ids = token.project_ids || [];
  if (!ids.length) return { kind: "none" };
  const names = ids.map((id) => {
    const p = (projects || []).find((x) => x.id === id);
    return p ? p.name || p.id : id;
  });
  return { kind: "projects", names };
}

/** Project scope sent to the API, from the radio choice and ticked project ids. */
export function scopeFromForm(mode, selectedIds) {
  if (mode !== "some") return { all_projects: true, project_ids: [] };
  return { all_projects: false, project_ids: [...(selectedIds || [])] };
}

/** First validation message for the create form, or null when it is valid. */
export function validateTokenForm({ name, scope }) {
  if (!(name || "").trim()) return MSG_NAME_REQUIRED;
  if (!scope.all_projects && scope.project_ids.length === 0)
    return MSG_SELECT_PROJECT;
  return null;
}

/** Body for POST /api/api-tokens. `expiresDays` is the raw input value. */
export function buildCreateBody({ name, role, expiresDays, scope }) {
  const body = { name: (name || "").trim(), role, ...scope };
  const raw = (expiresDays == null ? "" : String(expiresDays)).trim();
  if (raw) body.expires_in_days = Number(raw);
  return body;
}

/** Unix seconds → local date-time, or "never". */
export function formatTimestamp(ts) {
  return ts ? new Date(ts * 1000).toLocaleString() : "never";
}

export function revokeConfirmMessage(name) {
  return `Revoke the token "${name}"? Any caller using it loses access immediately.`;
}

/** Body of the "Token created — copy it now" dialog (HTML for uiModalHTML). */
export function tokenCreatedHtml(plaintext) {
  return `<p style="margin:0 0 10px">This token won't be shown again. Store it somewhere safe (e.g. a CI secret).</p>
         <input readonly value="${escapeHtml(plaintext)}" onclick="this.select()" style="width:100%;font-family:monospace;font-size:12.5px"/>`;
}
