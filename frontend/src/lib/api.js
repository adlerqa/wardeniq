// wardenIQ API client — a thin wrapper around fetch() that:
//   - always sends cookies (session auth is a signed HTTP-only cookie)
//   - JSON-encodes bodies and parses JSON responses
//   - surfaces backend errors as thrown Error objects with { status, detail }
//   - hooks into a global 401 handler so the UI can transition to the login gate
//
// This mirrors the behavior of the legacy inline `api()` helper (see
// app/static/index.html, formerly lines 2171-2205) and is the ONLY module the
// React feature code should use to talk to the FastAPI backend.

const AUTH_PATH_PREFIX = "/api/auth/";

let onUnauthorized = null;

/**
 * Register a callback invoked when any non-auth request returns 401.
 * The AppShell wires this up to trigger a re-check of the session.
 */
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

/**
 * Extract a human-readable error message from a FastAPI error payload.
 * FastAPI can return { detail: string } or { detail: [{ msg, loc }] }.
 */
function cleanErr(detail, status) {
  if (!detail) return `Request failed (${status})`;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === "string" ? d : d.msg || JSON.stringify(d))).join("; ");
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return `Request failed (${status})`;
  }
}

/**
 * Perform an authenticated JSON request.
 *
 * @param {string} path — API path starting with `/api/` (or absolute URL).
 * @param {object} [opts] — { method, body, headers, signal, raw }
 *   - body is auto-JSON-stringified unless it's already a string or FormData
 *   - set `raw: true` to receive the raw Response instead of parsed JSON
 * @returns {Promise<any>} parsed JSON body (or Response when raw=true)
 */
export async function api(path, opts = {}) {
  const { method = "GET", body, headers = {}, signal, raw = false } = opts;

  const init = {
    method,
    credentials: "include",
    headers: { ...headers },
    signal,
  };

  if (body !== undefined && body !== null) {
    if (body instanceof FormData || typeof body === "string") {
      init.body = body;
    } else {
      init.headers["Content-Type"] = init.headers["Content-Type"] || "application/json";
      init.body = JSON.stringify(body);
    }
  }

  const res = await fetch(path, init);

  if (res.status === 401 && !path.startsWith(AUTH_PATH_PREFIX)) {
    if (typeof onUnauthorized === "function") {
      // Fire-and-forget — the handler decides whether to redirect to login.
      try {
        onUnauthorized();
      } catch {
        /* ignore */
      }
    }
  }

  if (raw) return res;

  const text = await res.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    const err = new Error(cleanErr(payload?.detail ?? payload, res.status));
    err.status = res.status;
    err.detail = payload?.detail ?? payload;
    throw err;
  }

  return payload;
}

/** Convenience shortcut for GET requests. */
export const apiGet = (path, opts) => api(path, { ...opts, method: "GET" });

/** Convenience shortcut for POST requests. */
export const apiPost = (path, body, opts) =>
  api(path, { ...opts, method: "POST", body });

/** Convenience shortcut for PATCH requests. */
export const apiPatch = (path, body, opts) =>
  api(path, { ...opts, method: "PATCH", body });

/** Convenience shortcut for DELETE requests. */
export const apiDelete = (path, opts) => api(path, { ...opts, method: "DELETE" });
