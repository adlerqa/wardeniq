/**
 * Pure helpers for the sign-in screen (was the login half of
 * compat/runtime/controllers/10-auth.js).
 */
import { escapeHtml } from "../../../lib/html.js";

export const CODE_LENGTH = 6;

export const INTRO_OTP = "Sign in with a one-time code sent to your email. No password needed.";
export const INTRO_PASSWORD = "Sign in with your admin credentials. (SMTP is not configured)";
export const SESSION_LOST =
  "Your code was accepted, but the login session could not be saved. Please clear localhost cookies and try again.";

/**
 * SMTP status for choosing the sign-in method, with one retry after 250 ms so a
 * transient blip (e.g. right after a logout) doesn't pick the wrong method.
 * Resolves null (never throws) when both attempts fail.
 */
export async function smtpStatusWithRetry(api, wait = (ms) => new Promise((r) => setTimeout(r, ms))) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await api("/api/auth/smtp-status");
    } catch {
      if (attempt === 0) await wait(250);
    }
  }
  return null;
}

/**
 * Which sign-in method to show. Password sign-in is the safe default whenever
 * SMTP status can't be determined as well as when SMTP isn't configured: an OTP
 * request on a password-only install "succeeds" (anti-enumeration masking) but
 * never delivers anything, a dead end with no way back to password sign-in. If
 * SMTP really is configured, the password endpoint rejects with a clear error.
 */
export const loginMethod = (status) => (status && status.smtp_setup ? "otp" : "password");

/** Boot-status banner text ("" when ready). */
export const bootText = (status) =>
  status.ready ? "" : [status.detail, status.recovery].filter(Boolean).join(" ");

/**
 * Polls /api/auth/boot-status every 3 s while the sign-in screen is showing and
 * the backend isn't ready. Each start() supersedes the previous poll; a failed
 * request keeps the last diagnosis and retries.
 *   deps: { api, isShown(), show(text), hide(), setTimeout }
 */
export function createBootPoller(deps) {
  let current = 0;
  const run = async (poll) => {
    if (poll !== current || !deps.isShown()) return;
    try {
      const status = await deps.api("/api/auth/boot-status");
      if (poll !== current || !deps.isShown()) return;
      if (status.ready) {
        deps.hide();
        return;
      }
      deps.show(bootText(status));
    } catch {
      /* a transient failure must not erase a useful diagnosis */
    }
    if (poll === current && deps.isShown()) deps.setTimeout(() => run(poll), 3000);
  };
  return {
    start: () => run(++current),
    stop: () => {
      current++;
    },
    /** For tests: the current poll generation. */
    run: (poll) => run(poll === undefined ? current : poll),
  };
}

/**
 * What the code-sent step says after /api/auth/request-otp.
 * `msg` is { html } for the demo code (no SMTP) and { text } otherwise.
 */
export function otpSentMessage(r) {
  if (r && r.delivery === "log") {
    const code = r.dev_code ? String(r.dev_code) : "";
    return {
      sent: "Email isn't set up (demo mode) — your one-time code for ",
      msg: code
        ? {
            html:
              'Demo sign-in code: <b style="font-size:16px;letter-spacing:.3em;font-family:ui-monospace,monospace">' +
              escapeHtml(code) +
              '</b><br><span style="opacity:.75">Configure SMTP under Configuration → Email to stop showing codes in the UI.</span>',
          }
        : {
            text: "Check the server log (e.g. docker logs wardeniq) for the code, then set up email under Configuration → Email.",
          },
    };
  }
  // For an unknown / deactivated / rate-limited email the backend returns the same
  // {sent:true} shape (no account enumeration) with an honest `message`.
  return { sent: "We emailed a 6-digit code to ", msg: { text: (r && r.message) || "Code sent — check your email." } };
}

/** Digits of a pasted code, at most CODE_LENGTH. */
export const pastedDigits = (text) =>
  String(text || "")
    .replace(/\D/g, "")
    .slice(0, CODE_LENGTH);

/** One code box's value: its first digit, if any. */
export const boxDigit = (value) => String(value || "").replace(/\D/g, "").slice(0, 1);
