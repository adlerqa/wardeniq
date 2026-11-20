/**
 * Escape a value for interpolation into an HTML string. Only needed where React
 * code hands HTML to a compatibility helper (e.g. uiModalHTML); JSX escapes on
 * its own.
 */
export function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
