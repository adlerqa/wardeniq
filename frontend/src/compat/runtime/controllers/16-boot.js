// ---- boot ----
// First-run gate: until the required LLM section has been saved (settings.configured),
// sign-in lands on Configuration. This is a soft redirect only — the user is free to
// navigate anywhere else; nothing is locked.
async function needsConfig() {
  // GET /api/settings is admin-only (core/security.py ADMIN_PATHS). Configuration
  // is itself an admin-only page (its nav entry is hidden for everyone else — see
  // applyRole()'s `nav button[data-admin]` gating), so this first-run redirect is
  // only ever actionable by an admin anyway. Skipping the call for every other role
  // avoids a 403 the `api()` helper turns into a "Not allowed" toast on every single
  // page load/refresh -- previously fired for every Editor/Viewer, unconditionally,
  // even though the app went on to load their view normally right after.
  if (!(ME && ME.role === "admin")) return false;
  try {
    const s = await api("/api/settings");
    if (s.configured) return false;
  } catch (e) {
    return false;
  }
  // Settings were never saved, but the bundled defaults may already work: only
  // send the admin to Configuration when the model is actually unreachable (#169).
  // A passing health check counts as configured.
  try {
    const h = await api("/api/llm/test", { method: "POST" });
    return !h.ok;
  } catch (e) {
    return true;
  }
}
async function startApp() {
  // Block on a mandatory password change before anything else renders — only
  // ever true for the local admin account, and only while it's still on the
  // shipped default password.
  if (ME && ME.must_change_password) await openChangePasswordModal(true);
  refreshStatus();
  let nav = {};
  try {
    nav = JSON.parse(localStorage.getItem("wq_nav") || "{}");
  } catch (e) {}
  if (nav.project) currentProject = nav.project;
  if (nav.feature) currentFeature = nav.feature;
  if (await needsConfig()) {
    navigateTo("config");
    return;
  }
  const hashView = (location.hash || "").replace(/^#/, "");
  navigateTo(hashView || nav.view || "dashboard"); // restore last view, not always Dashboard
}
// If the user arrived via an invitation LINK (/invite?token=… or ?token=…), resolve
// the token, steer them through login-in-context, then straight to accept/decline.
// Returns true if it handled the boot (caller should stop).
async function handleInviteLink() {
  let token = null;
  try {
    token = new URLSearchParams(location.search).get("token");
  } catch (e) {}
  if (!token) return false;
  // Remember it so we survive the login round-trip, then clean the URL.
  try {
    sessionStorage.setItem("wq_invite_token", token);
  } catch (e) {}
  try {
    history.replaceState(
      null,
      "",
      location.pathname.replace(/\/invite$/, "/") || "/",
    );
  } catch (e) {}
  let info = null;
  try {
    const r = await fetch(
      `/api/invite/verify?token=${encodeURIComponent(token)}`,
    );
    if (r.ok) info = await r.json();
  } catch (e) {}
  if (!info) {
    // bad/expired token
    showLogin();
    if (typeof toast === "function")
      toast("This invitation link is invalid or has expired.", true);
    return true;
  }
  // Already signed in as the invited person? Go straight to accept/decline.
  const me = await checkAuth();
  if (me && ME && ME.email === info.email) {
    try {
      sessionStorage.removeItem("wq_invite_token");
    } catch (e) {}
    if (await maybeShowInvite()) return true;
    startApp();
    return true;
  }
  // Not signed in (or as someone else): prompt login prefilled with the invited email.
  showLogin();
  const em = $("#login-email");
  if (em) {
    em.value = info.email;
  }
  $("#login-msg").textContent =
    `You've been invited to ${(info.invite && info.invite.workspace) || "WardenIQ"} as ${(info.invite && info.invite.role) || "a user"}. Sign in as ${info.email} to accept.`;
  return true;
}
(async () => {
  if (await handleInviteLink()) return;
  if (await checkAuth()) {
    if (await maybeShowInvite()) return;
    startApp();
  }
})();
setInterval(() => {
  if (ME) refreshStatus();
}, 5000);
// Poll identity so admin-side role/disable changes propagate within ~30s even
// without a tab focus event (focus handler covers the common case instantly).
setInterval(() => {
  if (ME) refreshMe();
}, 30000);

// ---- disable browser autofill / autocomplete / suggestions on every field ----
// Applies to inputs/textareas/selects that exist now AND any added later (modals,
// tables, config forms are rendered dynamically), so nothing slips through.
function hardenField(el) {
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
function hardenFields(root) {
  const r = root || document;
  if (r.querySelectorAll)
    r.querySelectorAll("input,textarea,select").forEach(hardenField);
  if (r.querySelectorAll)
    r.querySelectorAll("form").forEach((f) =>
      f.setAttribute("autocomplete", "off"),
    );
}
hardenFields(document);
new MutationObserver((muts) => {
  for (const m of muts)
    for (const n of m.addedNodes) {
      if (n.nodeType !== 1) continue;
      if (n.matches && n.matches("input,textarea,select")) hardenField(n);
      hardenFields(n);
    }
}).observe(document.documentElement, { childList: true, subtree: true });
