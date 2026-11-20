/**
 * Thin bridge from React code to the shared UI helpers that still live in the
 * compatibility runtime (src/compat/runtime/controllers/00-core.js and
 * 10-auth.js).
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

/** toast(message, isErr | {type, title, duration}) — same signature as 00-core.js. */
export function toast(message, options) {
  const fn = compatFn("toast");
  if (fn) return fn(message, options);
  const isErr = options === true || (options && options.type === "err");
  (isErr ? console.error : console.info)(String(message));
}

/** Resolves true when confirmed, false when cancelled (00-core.js uiConfirm). */
export function uiConfirm(message, title, confirmLabel, danger) {
  const fn = compatFn("uiConfirm");
  if (fn) return fn(message, title, confirmLabel, danger);
  return Promise.resolve(false);
}

/**
 * Opens the shared HTML modal (00-core.js uiModalHTML). `bodyHTML` is inserted
 * as HTML: escape every interpolated value (see escapeHtml in lib/html.js).
 */
export function uiModalHTML(title, bodyHTML, confirmLabel) {
  const fn = compatFn("uiModalHTML");
  if (fn) return fn(title, bodyHTML, confirmLabel);
  return Promise.resolve(false);
}

/** Shows the sign-in screen and clears the cached identity (10-auth.js). */
export function showLogin() {
  const fn = compatFn("showLogin");
  if (fn) return fn();
}

/** Re-reads the signed-in user, e.g. after a 403 (10-auth.js). */
export function refreshMe() {
  const fn = compatFn("refreshMe");
  if (fn) return fn();
}
