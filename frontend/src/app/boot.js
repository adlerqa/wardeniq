/**
 * Start-up sequence (was compat/runtime/controllers/16-boot.js): invitation
 * links, sign-in check, first-run redirect to Configuration, restoring the last
 * view, and the field hardening that keeps browsers from autofilling. Run by
 * useBoot once the compatibility runtime is loaded.
 *
 * Everything outside this file is reached through `deps`, so tests can drive it:
 *   { api, fetch, currentUser, checkAuth, maybeShowInvite, showLogin, toast,
 *     openChangePasswordModal, refreshStatus, navigateTo, setCurrentProject,
 *     setCurrentFeature, location, history, storage, session }
 */

/**
 * First-run gate: until the LLM settings were saved (settings.configured), an
 * admin lands on Configuration — unless the bundled defaults already work
 * (/api/status llm.health, a cheap check that doesn't load the model, #169).
 * Only admins can act on it (GET /api/settings is admin-only), so other roles
 * skip the call rather than getting a "Not allowed" toast on every load.
 */
export async function needsConfig(user, api) {
  if (!(user && user.role === "admin")) return false;
  try {
    const s = await api("/api/settings");
    if (s.configured) return false;
  } catch {
    return false;
  }
  try {
    const st = await api("/api/status");
    return !(st.llm && st.llm.health && st.llm.health.ok);
  } catch {
    return true;
  }
}

/** After sign-in: the mandatory password change, then the saved / linked view. */
export async function startApp(d) {
  // Only the local admin still on the shipped admin123 password.
  const user = d.currentUser();
  if (user && user.must_change_password) await d.openChangePasswordModal(true);
  d.refreshStatus();
  let nav = {};
  try {
    nav = JSON.parse(d.storage.getItem("wq_nav") || "{}");
  } catch {
    /* no saved view */
  }
  if (nav.project) d.setCurrentProject(nav.project);
  if (nav.feature) d.setCurrentFeature(nav.feature);
  if (await needsConfig(d.currentUser(), d.api)) {
    d.navigateTo("config");
    return;
  }
  const hashView = (d.location.hash || "").replace(/^#/, "");
  d.navigateTo(hashView || nav.view || "dashboard"); // restore the last view, not always Dashboard
}

/**
 * An invitation LINK (/invite?token=… or ?token=…): resolve the token, sign in
 * as the invited person, then accept / decline. Returns true when it handled
 * the boot.
 */
export async function handleInviteLink(d) {
  let token = null;
  try {
    token = new URLSearchParams(d.location.search).get("token");
  } catch {
    /* no query */
  }
  if (!token) return false;
  // Keep it across the sign-in round-trip, then clean the URL.
  try {
    d.session.setItem("wq_invite_token", token);
  } catch {
    /* storage unavailable */
  }
  try {
    d.history.replaceState(null, "", d.location.pathname.replace(/\/invite$/, "/") || "/");
  } catch {
    /* history unavailable */
  }
  let info = null;
  try {
    const r = await d.fetch(`/api/invite/verify?token=${encodeURIComponent(token)}`);
    if (r.ok) info = await r.json();
  } catch {
    /* treated as invalid */
  }
  if (!info) {
    d.showLogin();
    d.toast("This invitation link is invalid or has expired.", true);
    return true;
  }
  // Already signed in as the invited person: straight to accept / decline.
  const me = await d.checkAuth();
  const user = d.currentUser();
  if (me && user && user.email === info.email) {
    try {
      d.session.removeItem("wq_invite_token");
    } catch {
      /* storage unavailable */
    }
    if (await d.maybeShowInvite()) return true;
    await startApp(d);
    return true;
  }
  // Not signed in, or as someone else: sign-in prefilled with the invited email.
  d.showLogin({
    msg: `You've been invited to ${(info.invite && info.invite.workspace) || "WardenIQ"} as ${(info.invite && info.invite.role) || "a user"}. Sign in as ${info.email} to accept.`,
  });
  const em = d.document.getElementById("login-email");
  if (em) em.value = info.email;
  return true;
}

/** The whole boot: invite link, else sign-in check → invite gate → app. */
export async function runBoot(d) {
  if (await handleInviteLink(d)) return;
  if (await d.checkAuth()) {
    if (await d.maybeShowInvite()) return;
    await startApp(d);
  }
}

// ---- no browser autofill / autocomplete / suggestions on any field ----

export function hardenField(el) {
  if (!el || el.dataset.wqNoauto) return;
  const tag = el.tagName;
  if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") return;
  const type = (el.getAttribute("type") || "").toLowerCase();
  // "new-password" is the most reliable way to stop the password-manager dropdown.
  el.setAttribute("autocomplete", type === "password" ? "new-password" : "off");
  el.setAttribute("autocorrect", "off");
  el.setAttribute("autocapitalize", "off");
  el.setAttribute("spellcheck", "false");
  el.setAttribute("data-lpignore", "true"); // LastPass
  el.setAttribute("data-1p-ignore", "true"); // 1Password
  el.dataset.wqNoauto = "1";
}

export function hardenFields(root) {
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll("input,textarea,select").forEach(hardenField);
  root.querySelectorAll("form").forEach((f) => f.setAttribute("autocomplete", "off"));
}

/** Harden every field now and every one added later. Returns a stop function. */
export function watchFields(doc, Observer) {
  hardenFields(doc);
  const mo = new Observer((muts) => {
    for (const m of muts)
      for (const n of m.addedNodes) {
        if (n.nodeType !== 1) continue;
        if (n.matches && n.matches("input,textarea,select")) hardenField(n);
        hardenFields(n);
      }
  });
  mo.observe(doc.documentElement, { childList: true, subtree: true });
  return () => mo.disconnect();
}
