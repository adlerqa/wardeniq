/** Toast settings (was 00-core.js toast); components/overlays/modals/ToastHost.jsx renders them. */

const TITLES = { ok: "Success", err: "Something went wrong", info: "Heads up", warn: "Warning" };

/**
 * toast(message, isErr) or toast(message, { type: "ok" | "err" | "info" | "warn", title, duration })
 * → the toast's settings. Errors and warnings stay longer, scaled by message length.
 */
export function toastSettings(msg, opt) {
  let type = "ok",
    title,
    duration;
  if (opt === true) {
    type = "err";
  } else if (opt && typeof opt === "object") {
    type = opt.type || (opt.isErr ? "err" : "ok");
    title = opt.title;
    duration = opt.duration;
  }
  return {
    type,
    title: title || TITLES[type],
    msg: msg == null ? "" : String(msg),
    duration: duration || (type === "err" || type === "warn" ? Math.min(9000, 5200 + (msg || "").length * 35) : 3800),
  };
}
