// ---- auth / identity ----
// The sign-in screen (showLogin, password / one-time code / reset, logout) is React:
// src/features/auth (#257).
function applyRole() {
  const role = (ME && ME.role) || "viewer";
  $("#usermenu").hidden = false;
  const emailEl = $("#user-email");
  emailEl.textContent = ME.email;
  emailEl.title = ME.email;
  const rb = $("#user-role");
  rb.textContent = role;
  rb.className = "rolebadge " + role;
  document.body.classList.toggle("role-viewer", role === "viewer");
  document.body.classList.toggle("role-editor", role === "editor");
  const admin = role === "admin";
  document
    .querySelectorAll("nav button[data-admin]")
    .forEach((b) => (b.hidden = !admin));
  const rob = $("#ro-banner");
  if (rob) rob.hidden = role !== "viewer";
  applyRoleTooltips(role);
  // "Change password" only makes sense for the local admin account (email===
  // "admin"). Email-based accounts sign in with a one-time code and have no
  // password at all.
  const pwBtn = $("#change-pw-btn");
  if (pwBtn) pwBtn.hidden = !(ME && ME.email === "admin");
}

// ---- change password (local admin account only) ----
// Reused for both the voluntary "Change password" profile-menu action and the
// mandatory first-login prompt. In mandatory mode the Cancel/close controls are
// hidden and the returned promise only resolves once a new password is saved —
// there is no way to click past it, matching the shipped default being a known,
// public credential (admin123) that shouldn't stay active silently.
function openChangePasswordModal(mandatory) {
  return new Promise((resolve) => {
    const m = $("#pwd-modal");
    $("#pwd-current").value = "";
    $("#pwd-new").value = "";
    $("#pwd-confirm").value = "";
    $("#pwd-err").textContent = "";
    $("#pwd-title").textContent = mandatory
      ? "Set a new password"
      : "Change password";
    $("#pwd-intro").textContent = mandatory
      ? "You're signed in with the default admin123 password. For security, set a new one before continuing."
      : "Update the local admin password.";
    $("#pwd-x").style.display = mandatory ? "none" : "";
    $("#pwd-cancel").style.display = mandatory ? "none" : "";
    m.classList.add("show");
    setTimeout(() => $("#pwd-current")?.focus(), 50);
    const cleanup = () => {
      $("#pwd-save").onclick = null;
      $("#pwd-cancel").onclick = null;
      $("#pwd-x").onclick = null;
      $("#pwd-current").onkeydown =
        $("#pwd-new").onkeydown =
        $("#pwd-confirm").onkeydown =
          null;
    };
    const done = (ok) => {
      m.classList.remove("show");
      cleanup();
      resolve(ok);
    };
    $("#pwd-cancel").onclick = () => {
      if (!mandatory) done(false);
    };
    $("#pwd-x").onclick = () => {
      if (!mandatory) done(false);
    };
    const save = async () => {
      const current = $("#pwd-current").value,
        next = $("#pwd-new").value,
        confirm = $("#pwd-confirm").value;
      $("#pwd-err").textContent = "";
      if (!current) {
        $("#pwd-err").textContent = "Enter your current password.";
        return;
      }
      if (!next) {
        $("#pwd-err").textContent = "Enter a new password.";
        return;
      }
      if (next !== confirm) {
        $("#pwd-err").textContent = "New passwords don't match.";
        return;
      }
      $("#pwd-save").disabled = true;
      setBusy("#pwd-save", true);
      try {
        const r = await api("/api/auth/change-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current_password: current,
            new_password: next,
          }),
        });
        if (r && r.user) ME = r.user;
        toast("Password changed.");
        done(true);
      } catch (e) {
        $("#pwd-err").textContent = e.message;
      } finally {
        $("#pwd-save").disabled = false;
        setBusy("#pwd-save", false);
      }
    };
    $("#pwd-save").onclick = save;
    $("#pwd-current").onkeydown =
      $("#pwd-new").onkeydown =
      $("#pwd-confirm").onkeydown =
        (e) => {
          if (e.key === "Enter") save();
        };
  });
}
if ($("#change-pw-btn"))
  $("#change-pw-btn").onclick = () => openChangePasswordModal(false);
// Auto read-only enforcement for viewers: many write buttons aren't tagged
// .needs-editor, so we identify them by their label/action and disable+dim+tooltip
// them, instead of letting a viewer click and hit a 403. Idempotent; safe to call
// after every view render and after async loaders inject more buttons.
const _VIEWER_WRITE_RE =
  /\b(create|add|new|save|delete|remove|edit|generate|regenerate|import|invite|run|start|associate|assign|reassign|sync|rescan|watch|apply|submit|upload|clear|reset|link|unlink|promote|export)\b/i;
const _VIEWER_SKIP_RE =
  /\b(cancel|close|back|search|filter|view|open|download|refresh|copy|sign out|logout|use a different|expand|collapse|show|hide|next|prev|previous)\b/i;
function enforceViewerReadOnly() {
  const isViewer = (ME && ME.role) === "viewer";
  const scope = document.querySelector(".view:not([hidden])") || document;
  scope.querySelectorAll("button").forEach((b) => {
    const label = (
      b.textContent ||
      b.getAttribute("aria-label") ||
      b.title ||
      ""
    ).trim();
    if (!label) return;
    const looksWrite =
      _VIEWER_WRITE_RE.test(label) && !_VIEWER_SKIP_RE.test(label);
    if (!looksWrite) return;
    b.classList.add("needs-editor"); // reuse the dim/disable CSS + tooltip logic
  });
  applyRoleTooltips(isViewer ? "viewer" : (ME && ME.role) || "viewer");
}
// Explain WHY a control is disabled, on hover, for restricted roles.
function applyRoleTooltips(role) {
  const msg =
    role === "viewer"
      ? "Read-only — your Viewer role can't make changes. Ask an admin for Editor access."
      : "";
  document.querySelectorAll(".needs-editor").forEach((el) => {
    if (role === "viewer") {
      if (!el.dataset._t) {
        el.dataset._t = el.getAttribute("title") || "";
      }
      el.setAttribute("title", msg);
    } else if (el.dataset._t !== undefined) {
      if (el.dataset._t) el.setAttribute("title", el.dataset._t);
      else el.removeAttribute("title");
    }
  });
}
async function checkAuth() {
  try {
    const r = await api("/api/auth/me");
    ME = r.user;
    $("#login").hidden = true;
    applyRole();
    return true;
  } catch (e) {
    showLogin();
    return false;
  }
}

// ---- invite banner (pending invite shown after login) ----
function fmtDate(ts) {
  try {
    return ts
      ? new Date(ts * 1000).toLocaleDateString(undefined, {
          year: "numeric",
          month: "short",
          day: "numeric",
        })
      : "";
  } catch (e) {
    return "";
  }
}
// Returns true if a pending invite is being shown (caller should NOT start the app yet).
async function maybeShowInvite() {
  try {
    const r = await api("/api/auth/my-invite");
    const inv = r && r.invite;
    if (!inv || !inv.pending) {
      $("#invite-gate").hidden = true;
      return false;
    }
    // Populate the banner.
    $("#invite-workspace").textContent = inv.workspace || "WardenIQ";
    const by = inv.invited_by;
    const byLabel = by
      ? by.name
        ? `${esc(by.name)} (${esc(by.email)})`
        : esc(by.email)
      : "an administrator";
    const rows = [
      ["Invited by", byLabel],
      ["Workspace", esc(inv.workspace || "WardenIQ")],
      [
        "Role granted",
        `<span class="rolebadge ${esc(inv.role)}">${esc(inv.role)}</span>`,
      ],
      ["Sent", esc(fmtDate(inv.invited_at)) || "—"],
    ];
    const roleDesc = (window.RBAC && RBAC.DESC[inv.role]) || "";
    $("#invite-meta").innerHTML =
      rows
        .map(
          ([k, v]) =>
            `<div class="row"><span>${k}</span><span>${v}</span></div>`,
        )
        .join("") +
      (roleDesc ? `<div class="row-desc">${esc(roleDesc)}</div>` : "");
    $("#invite-err").textContent = "";
    $("#invite-gate").hidden = false;
    return true;
  } catch (e) {
    $("#invite-gate").hidden = true;
    return false;
  }
}
$("#invite-accept").onclick = async () => {
  $("#invite-accept").disabled = true;
  $("#invite-err").textContent = "";
  try {
    const r = await api("/api/auth/invite/accept", { method: "POST" });
    if (r && r.user) ME = r.user;
    $("#invite-gate").hidden = true;
    applyRole();
    toast("Invitation accepted — welcome!");
    startApp();
  } catch (e) {
    $("#invite-err").textContent = e.message;
  } finally {
    $("#invite-accept").disabled = false;
  }
};
$("#invite-decline").onclick = async () => {
  if (
    !(await uiConfirm(
      "Decline this invitation? You'll be signed out and won't have access.",
      "Decline invitation",
      "Decline",
      true,
    ))
  )
    return;
  $("#invite-decline").disabled = true;
  $("#invite-err").textContent = "";
  try {
    await api("/api/auth/invite/decline", { method: "POST" });
    $("#invite-gate").hidden = true;
    ME = null;
    showLogin();
    toast("Invitation declined.");
  } catch (e) {
    $("#invite-err").textContent = e.message;
  } finally {
    $("#invite-decline").disabled = false;
  }
};
// Re-fetch identity so a role change / disable made by an admin takes effect live
// without a manual refresh. Called on window focus and on a light poll.
let _refreshingMe = false;
async function refreshMe() {
  if (_refreshingMe || !ME) return;

  _refreshingMe = true;

  try {
    const r = await fetch("/api/auth/me", {
      method: "GET",

      // Explicitly make sure the session cookie is sent.
      credentials: "include",

      headers: {
        Accept: "application/json",
      },
    });

    if (r.status === 401) {
      console.warn(
        "[Auth] /api/auth/me returned 401. Session cookie may be missing or invalid.",
      );

      ME = null;

      showLogin();

      if (typeof toast === "function") {
        toast(
          "Your session ended — please sign in again.",
          true,
        );
      }

      return;
    }

    if (!r.ok) {
      console.warn(
        `[Auth] Identity refresh failed with status ${r.status}`,
      );

      // Don't log the user out for temporary server errors.
      return;
    }

    const j = await r.json();

    if (!j?.user) {
      console.warn(
        "[Auth] /api/auth/me did not return a user.",
      );

      return;
    }

    const prevRole = ME?.role;

    ME = j.user;

    if (ME.role !== prevRole) {
      applyRole();

      if (typeof toast === "function") {
        toast(`Your role is now "${ME.role}".`);
      }

      const adminOnly = [
        "users",
        "config",
      ];

      if (
        ME.role !== "admin" &&
        adminOnly.includes(currentViewName)
      ) {
        try {
          navigateTo("dashboard");
        } catch (e) {}
      } else {
        try {
          navigateTo(currentViewName);
        } catch (e) {}
      }
    }
  } catch (e) {
    // Network failure should NOT destroy the current session.
    console.warn(
      "[Auth] Unable to refresh session:",
      e,
    );
  } finally {
    _refreshingMe = false;
  }
}
window.addEventListener("focus", () => {
  try {
    refreshMe();
  } catch (e) {}
});
