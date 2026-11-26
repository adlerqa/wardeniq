/**
 * Service / boot status helpers (was the status block of
 * compat/runtime/controllers/00-core.js). layouts/useServiceStatus.js renders
 * the header chips and the boot banner from them.
 */
import { escapeHtml as esc } from "./html.js";

// Human-readable Vector Search copy from app/core/bootstrap.py (_SEARCH_REQUIRED_MSG).
// Shown when boot failed but the API still has a raw driver exception in boot.detail.
export const BOOT_VECTOR_SEARCH_MSG =
  "wardenIQ requires a MongoDB with Vector Search — it's where embeddings are searched. The database at MONGO_URI doesn't have it. Use MongoDB Atlas (search built in) or a self-managed MongoDB running mongot, then restart.";
// Allowlist of KNOWN-SAFE, canned messages (all authored by app/core/bootstrap.py —
// see _SEARCH_REQUIRED_MSG, _SEARCH_INDEX_LIMIT_MSG, and the insecure-secret /
// insecure-production-posture messages in _check_app_secret / _check_production_posture).
// Anything NOT in this list is treated as potentially-raw backend/driver text and kept
// out of the primary summary (see looksLikeRawBootDetail below).
export const BOOT_SAFE_DETAIL_MARKERS = [
  "requires a MongoDB with Vector Search",
  "doesn't allow enough search indexes",
  "insecure APP_SECRET",
  "insecure production configuration",
];

// Deliberately an ALLOWLIST, not a blocklist: boot.detail can carry an arbitrary
// exception from any driver/library in the backend's call stack (pymongo, the OS
// resolver, mongot, …), and that space is unbounded — a blocklist of known raw-dump
// signatures (msgLen/ProtocolError/pymongo/etc.) will always be one exception shape
// behind (confirmed in practice: a plain `pymongo.errors.ConfigurationError` DNS
// failure matched none of the old signatures and was shown verbatim as the primary
// banner text). The set of SAFE messages, by contrast, is small and entirely owned
// by this app (BOOT_SAFE_DETAIL_MARKERS above) — enumerating what we trust is
// tractable in a way enumerating what we don't trust never is. So: safe only if it
// matches a known canned message; everything else stays behind the Details
// disclosure, regardless of whether it happens to look like a "recognizable" dump.
export function looksLikeRawBootDetail(detail) {
  const d = String(detail || "");
  if (!d) return false;
  return !BOOT_SAFE_DETAIL_MARKERS.some((m) => d.includes(m));
}

export function formatBootStatus(boot) {
  boot = boot || {};
  const stage = String(boot.stage || "");
  const detail = String(boot.detail || "");
  if (boot.ready) return { visible: false, kind: "ok", summary: "", raw: "" };

  const raw = looksLikeRawBootDetail(detail) ? detail : "";
  const safeDetail = raw ? "" : detail;

  if (stage === "error") {
    return {
      visible: true,
      kind: "error",
      summary: safeDetail || BOOT_VECTOR_SEARCH_MSG,
      raw,
    };
  }
  if (stage === "indexing") {
    return {
      visible: true,
      kind: "warn",
      summary: "Setting up Vector Search indexes…",
      raw: detail,
    };
  }
  if (stage === "connecting") {
    return {
      visible: true,
      kind: "warn",
      summary: "Connecting to MongoDB…",
      raw: detail,
    };
  }
  return {
    visible: true,
    kind: "warn",
    summary: stage ? `Starting up (${stage})` : "Starting up…",
    raw: raw || "",
  };
}

export function bootBannerDetailsHtml(raw) {
  if (!raw) return "";
  return (
    `<details class="boot-banner-details">` +
    `<summary>Details</summary>` +
    `<pre class="boot-banner-raw">${esc(raw)}</pre>` +
    `</details>`
  );
}

/** The banner after a failed /api/status: raw text stays behind "Details". */
export function statusFailureBanner(message) {
  const raw = message ? String(message) : "";
  const isRaw = looksLikeRawBootDetail(raw);
  return {
    visible: true,
    kind: "error",
    summary: isRaw ? "Can't load service status right now." : raw || "Can't load service status right now.",
    raw: isRaw ? raw : "",
  };
}
