/**
 * API helper (the former compat `api()` / `cleanErr()`, same behaviour); also
 * registered on window as `api` for the Gap Analysis compat controller:
 *
 *   - parses the JSON body (a non-JSON body becomes the error detail);
 *   - network failure: "Can't reach the server" toast, then throws;
 *   - 401 (outside /api/auth/): shows the sign-in screen with a
 *     "Session expired" toast, then throws;
 *   - 403: "Not allowed" toast, refreshes the signed-in user, then throws;
 *   - any other non-2xx: throws an Error whose message is the cleaned `detail`.
 *
 * Toasts and the sign-in screen are reached through lib/compatBridge.js.
 * NEVER log request bodies or response payloads: they can carry PATs, API keys,
 * SMTP passwords, OTP codes, plaintext API tokens and other secrets.
 *
 * Usage:
 *   const r = await api("/api/api-tokens");
 *   await api("/api/api-tokens", { method: "POST", json: { name: "ci" } });
 */
import * as bridge from "./compatBridge.js";

const STATUS_MESSAGES = {
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

/** Turn a raw backend / httpx error string into a short, human message. */
export function cleanErr(detail, status) {
  let d = (detail == null ? "" : detail).toString().trim();
  d = d.replace(/\s*For more information check:\s*https?:\/\/\S+/gi, "");
  d = d.replace(/(?:client|server) error '([^']+)' for url '[^']*'/gi, "$1");
  d = d.replace(/\s*for url '[^']*'/gi, "");
  d = d
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s*\n\s*/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
  d = d.replace(/[:\s]+$/, "").trim();
  if (d) return d;
  return (
    STATUS_MESSAGES[status] ||
    `Request failed${status ? ` (${status})` : ""}. Please try again.`
  );
}

/**
 * fetch() wrapper. `options` is passed to fetch unchanged, except that a
 * `json` property is serialised as the body with a JSON content type.
 * `deps` exists for tests (fetch and the UI bridge); callers leave it out.
 */
export async function api(path, options, deps = {}) {
  const doFetch = deps.fetch || ((...a) => fetch(...a));
  const ui = deps.bridge || bridge;
  let init = options;
  if (options && Object.prototype.hasOwnProperty.call(options, "json")) {
    const { json, headers, ...rest } = options;
    init = {
      ...rest,
      headers: { "Content-Type": "application/json", ...(headers || {}) },
      body: JSON.stringify(json),
    };
  }

  let r, raw;
  try {
    r = await doFetch(path, init);
    raw = await r.text();
  } catch (netErr) {
    console.error(`[API Net] ${path}`, netErr);
    ui.toast(
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
  } catch {
    j = { detail: raw || `Request failed with status ${r.status}` };
  }

  if (r.status === 401 && !path.startsWith("/api/auth/")) {
    // Includes session invalidation after a role change / disable / forced logout.
    ui.showLogin();
    ui.toast(j.detail || "Your session ended — please sign in again.", {
      type: "info",
      title: "Session expired",
    });
    throw new Error(j.detail || "Please sign in");
  }
  if (r.status === 403) {
    ui.toast(j.detail || "You don't have permission to do that.", {
      type: "err",
      title: "Not allowed",
    });
    if (!path.startsWith("/api/auth/"))
      setTimeout(() => {
        try {
          ui.refreshMe();
        } catch {
          /* identity refresh is best-effort */
        }
      }, 0);
    throw new Error(cleanErr(j.detail || "not permitted", r.status));
  }
  if (!r.ok) {
    throw new Error(cleanErr(j.detail, r.status));
  }
  return j;
}
