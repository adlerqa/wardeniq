// ---- auth / login ----
// One retry (250ms backoff) before giving up on the SMTP-status check --
// smooths over a transient blip (e.g. right after a fresh logout, when this
// runs again immediately) instead of immediately guessing which login method
// to show. Returns null (never throws) on total failure so showLogin() has
// one shape to branch on.
async function _smtpStatusWithRetry() {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await api("/api/auth/smtp-status");
    } catch (e) {
      if (attempt === 0) await new Promise((r) => setTimeout(r, 250));
    }
  }
  return null;
}
let loginBootPoll = 0;
async function refreshLoginBootStatus(poll) {
  if (poll !== loginBootPoll || $("#login").hidden) return;
  try {
    const status = await api("/api/auth/boot-status");
    if (poll !== loginBootPoll || $("#login").hidden) return;
    const banner = $("#login-boot-status");
    banner.textContent = status.ready
      ? ""
      : [status.detail, status.recovery].filter(Boolean).join(" ");
    banner.hidden = status.ready;
    if (status.ready) return;
  } catch (e) {
    // A transient request failure must not erase an already useful diagnosis.
  }
  if (poll === loginBootPoll && !$("#login").hidden)
    setTimeout(() => refreshLoginBootStatus(poll), 3000);
}
async function showLogin() {
  ME = null;
  $("#login").hidden = false;
  void refreshLoginBootStatus(++loginBootPoll);
  $("#usermenu").hidden = true;
  $("#login-err").textContent = "";
  $("#login-msg").textContent = "";
  clearLoginCode();
  const status = await _smtpStatusWithRetry();
  if (status && status.smtp_setup) {
    $("#login-intro").textContent =
      "Sign in with a one-time code sent to your email. No password needed.";
    $("#login-step1").hidden = false;
    $("#login-step2").hidden = true;
    $("#login-password").hidden = true;
    setTimeout(() => $("#login-email")?.focus(), 50);
  } else {
    // Safe default whenever smtp-status can't be determined (status is null
    // after retries) as well as the genuine "SMTP not configured" case: show
    // password sign-in, not the OTP flow. If SMTP genuinely IS configured,
    // login-password's own backend check rejects the attempt with a clear,
    // actionable error ("Password login is disabled because SMTP is
    // configured..."). Defaulting to OTP instead is the wrong direction --
    // when SMTP genuinely ISN'T configured (a password-only/local-admin
    // install), an OTP request still "succeeds" against the API's own
    // anti-enumeration masking but never delivers anything: a silent dead end
    // with no error and no way back to password login short of reloading the
    // page. This is what QA reported as "admin gets redirected to OTP after
    // logout and can't sign back in with username/password until they clear
    // browser data" -- clearing data just forces a fresh load that happens to
    // give the smtp-status check another chance to succeed.
    $("#login-intro").textContent =
      "Sign in with your admin credentials. (SMTP is not configured)";
    $("#login-step1").hidden = true;
    $("#login-step2").hidden = true;
    $("#login-password").hidden = false;
    setTimeout(() => $("#login-username")?.focus(), 50);
  }
}
function applyRole() {
  const role = (ME && ME.role) || "viewer";
  $("#usermenu").hidden = false;
  $("#user-email").textContent = ME.email;
  const rb = $("#user-role");
  rb.textContent = role;
  rb.className = "rolebadge " + role;
  document.body.classList.toggle("role-viewer", role === "viewer");
  document.body.classList.toggle("role-editor", role === "editor");
  const admin = role === "admin";
  document
    .querySelectorAll("nav button[data-admin]")
    .forEach((b) => (b.hidden = !admin));
  document.querySelectorAll("[data-admin-section]").forEach((section) => {
    section.hidden = !admin;
  });
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
$("#login-send").onclick = async () => {
  const email = $("#login-email").value.trim();
  if (!email) {
    $("#login-err").textContent = "Enter your email";
    return;
  }
  $("#login-send").disabled = true;
  setBusy("#login-send", true);
  $("#login-err").textContent = "";
  $("#login-msg").textContent = "Sending your sign-in code…";
  try {
    const r = await api("/api/auth/request-otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    $("#login-step1").hidden = true;
    $("#login-step2").hidden = false;
    $("#login-to").textContent = email;
    if (r && r.delivery === "log") {
      $("#login-sent-text").textContent =
        "Email isn't set up (demo mode) — your one-time code for ";
      // Show the code inline so contributors/evaluators can sign in without SMTP.
      // The same code is also printed to the server log (docker logs wardeniq).
      const code = r.dev_code ? String(r.dev_code) : "";
      if (code) {
        $("#login-msg").innerHTML =
          'Demo sign-in code: <b style="font-size:16px;letter-spacing:.3em;font-family:ui-monospace,monospace">' +
          esc(code) +
          '</b><br><span style="opacity:.75">Configure SMTP under Configuration → Email to stop showing codes in the UI.</span>';
      } else {
        $("#login-msg").textContent =
          "Check the server log (e.g. docker logs wardeniq) for the code, then set up email under Configuration → Email.";
      }
    } else {
      $("#login-sent-text").textContent = "We emailed a 6-digit code to ";
      // The backend can't always tell us a code actually reached an inbox — for an
      // unrecognized/deactivated/rate-limited email it deliberately returns the same
      // {sent:true} shape (so this screen can't be used to enumerate accounts), but
      // now includes an honest, non-committal `message` for that case instead of
      // nothing. Prefer it over the hardcoded "Code sent" text, which used to claim
      // delivery even when none was attempted.
      $("#login-msg").textContent = r.message || "Code sent — check your email.";
    }
    clearLoginCode();
    setTimeout(focusLoginCode, 50);
  } catch (e) {
    $("#login-err").textContent = e.message;
  } finally {
    $("#login-send").disabled = false;
    setBusy("#login-send", false);
  }
};
$("#login-verify").onclick = async () => {
  const email = $("#login-to").textContent,
    code = getLoginCode();
  if (!code) {
    $("#login-err").textContent = "Enter the code";
    return;
  }
  $("#login-verify").disabled = true;
  setBusy("#login-verify", true);
  $("#login-err").textContent = "";
  try {
    const r = await api("/api/auth/verify-otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code }),
    });
    ME = r.user;

/**
 * OTP verification returned a user,
 * but now confirm that the HTTP-only session cookie
 * was actually stored and can be used.
 */
try {
  const meResponse = await fetch(
    "/api/auth/me",
    {
      credentials: "include",
    },
  );

  if (!meResponse.ok) {
    throw new Error(
      "Session cookie was not created correctly.",
    );
  }

  const meData = await meResponse.json();

  if (!meData?.user) {
    throw new Error(
      "Authenticated user could not be restored.",
    );
  }

  ME = meData.user;
} catch (sessionError) {
  console.error(
    "[Auth] OTP succeeded but session validation failed:",
    sessionError,
  );

  ME = null;

  showLogin();

  $("#login-err").textContent =
    "Your code was accepted, but the login session could not be saved. Please clear localhost cookies and try again.";

  return;
}

$("#login").hidden = true;

applyRole();

try {
  sessionStorage.removeItem(
    "wq_invite_token",
  );
} catch (e) {}

if (await maybeShowInvite()) return;

startApp();
  } catch (e) {
    $("#login-err").textContent = e.message;
  } finally {
    $("#login-verify").disabled = false;
    setBusy("#login-verify", false);
  }
};
$("#login-email").onkeydown = (e) => {
  if (e.key === "Enter") $("#login-send").click();
};
$("#login-back").onclick = () => {
  $("#login-step1").hidden = false;
  $("#login-step2").hidden = true;
  $("#login-err").textContent = "";
  $("#login-msg").textContent = "";
  clearLoginCode();
};
$("#login-signin").onclick = async () => {
  const username = $("#login-username").value.trim();
  const password = $("#login-pw").value;
  if (!username) {
    $("#login-err").textContent = "Enter your username";
    return;
  }
  if (!password) {
    $("#login-err").textContent = "Enter your password";
    return;
  }
  $("#login-signin").disabled = true;
  setBusy("#login-signin", true);
  $("#login-err").textContent = "";
  try {
    const r = await api("/api/auth/login-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    ME = r.user;
    $("#login").hidden = true;
    applyRole();
    try {
      sessionStorage.removeItem("wq_invite_token");
    } catch (e) {}
    if (await maybeShowInvite()) return;
    startApp();
  } catch (e) {
    $("#login-err").textContent = e.message;
  } finally {
    $("#login-signin").disabled = false;
    setBusy("#login-signin", false);
  }
};
$("#login-username").onkeydown = (e) => {
  if (e.key === "Enter") $("#login-pw").focus();
};
$("#login-pw").onkeydown = (e) => {
  if (e.key === "Enter") $("#login-signin").click();
};
const forgotBtn = $("#login-forgot-btn");
if (forgotBtn) {
  forgotBtn.onclick = async () => {
    $("#login-password").hidden = true;
    $("#login-step1").hidden = true;
    $("#login-step2").hidden = true;
    $("#login-forgot-step1").hidden = true;
    $("#login-forgot-step2").hidden = true;
    $("#login-forgot-nosmtp").hidden = true;
    $("#login-err").textContent = "";
    $("#login-msg").textContent = "";
    try {
      const status = await api("/api/auth/smtp-status");
      if (status && status.smtp_setup) {
        $("#login-forgot-step1").hidden = false;
        $("#reset-target").value = $("#login-username")?.value.trim() || "";
      } else {
        $("#login-forgot-nosmtp").hidden = false;
      }
    } catch (e) {
      $("#login-forgot-nosmtp").hidden = false;
    }
  };
}
const resetNoSmtpBackBtn = $("#reset-nosmtp-back-btn");
if (resetNoSmtpBackBtn) {
  resetNoSmtpBackBtn.onclick = () => {
    $("#login-forgot-nosmtp").hidden = true;
    showLogin();
  };
}
const resetMasterBtn = $("#reset-master-submit-btn");
if (resetMasterBtn) {
  resetMasterBtn.onclick = async () => {
    const username = $("#reset-master-username")?.value.trim() || "admin";
    const app_secret = $("#reset-master-secret")?.value.trim();
    const new_password = $("#reset-master-new-pw")?.value;
    if (!app_secret) {
      $("#login-err").textContent = "Enter App Master Secret (APP_SECRET)";
      return;
    }
    if (!new_password) {
      $("#login-err").textContent = "Enter a new password";
      return;
    }
    resetMasterBtn.disabled = true;
    setBusy("#reset-master-submit-btn", true);
    $("#login-err").textContent = "";
    $("#login-msg").textContent = "";
    try {
      const r = await api("/api/auth/reset-password-master", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, app_secret, new_password }),
      });
      $("#login-msg").textContent =
        r.message || "Password reset successfully. Please sign in.";
      $("#login-forgot-nosmtp").hidden = true;
      showLogin();
    } catch (e) {
      $("#login-err").textContent = e.message;
    } finally {
      resetMasterBtn.disabled = false;
      setBusy("#reset-master-submit-btn", false);
    }
  };
}
const resetBackBtn = $("#reset-back-btn");
if (resetBackBtn) {
  resetBackBtn.onclick = () => {
    $("#login-forgot-step1").hidden = true;
    $("#login-forgot-step2").hidden = true;
    showLogin();
  };
}
const resetCancelBtn = $("#reset-cancel-btn");
if (resetCancelBtn) {
  resetCancelBtn.onclick = () => {
    $("#login-forgot-step1").hidden = true;
    $("#login-forgot-step2").hidden = true;
    showLogin();
  };
}
const resetReqBtn = $("#reset-request-btn");
if (resetReqBtn) {
  resetReqBtn.onclick = async () => {
    const target = $("#reset-target").value.trim();
    if (!target) {
      $("#login-err").textContent = "Enter username or email";
      return;
    }
    resetReqBtn.disabled = true;
    setBusy("#reset-request-btn", true);
    $("#login-err").textContent = "";
    $("#login-msg").textContent = "";
    try {
      const r = await api("/api/auth/request-password-reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username_or_email: target }),
      });
      if (r.smtp_configured) {
        $("#login-msg").textContent =
          r.message || "Reset code sent. Please check your email.";
        $("#login-forgot-step1").hidden = true;
        $("#login-forgot-step2").hidden = false;
      } else {
        $("#login-forgot-step1").hidden = true;
        $("#login-forgot-nosmtp").hidden = false;
      }
    } catch (e) {
      $("#login-err").textContent = e.message;
    } finally {
      resetReqBtn.disabled = false;
      setBusy("#reset-request-btn", false);
    }
  };
}
const resetSubmitBtn = $("#reset-submit-btn");
if (resetSubmitBtn) {
  resetSubmitBtn.onclick = async () => {
    const target = $("#reset-target").value.trim();
    const code = $("#reset-code").value.trim();
    const new_password = $("#reset-new-pw").value;
    if (!code) {
      $("#login-err").textContent = "Enter the 6-digit reset code";
      return;
    }
    if (!new_password) {
      $("#login-err").textContent = "Enter a new password";
      return;
    }
    resetSubmitBtn.disabled = true;
    setBusy("#reset-submit-btn", true);
    $("#login-err").textContent = "";
    $("#login-msg").textContent = "";
    try {
      const r = await api("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username_or_email: target, code, new_password }),
      });
      $("#login-msg").textContent =
        r.message || "Password reset successfully. Please sign in.";
      $("#login-forgot-step1").hidden = true;
      $("#login-forgot-step2").hidden = true;
      showLogin();
    } catch (e) {
      $("#login-err").textContent = e.message;
    } finally {
      resetSubmitBtn.disabled = false;
      setBusy("#reset-submit-btn", false);
    }
  };
}
// ---- 6-box OTP entry: digits only, auto-advance, backspace, paste (spaces/letters stripped) ----
function loginCodeBoxes() {
  return Array.from(document.querySelectorAll("#login-code .otp-box"));
}
function getLoginCode() {
  return loginCodeBoxes()
    .map((b) => b.value)
    .join("")
    .replace(/\D/g, "");
}
function clearLoginCode() {
  loginCodeBoxes().forEach((b) => {
    b.value = "";
  });
}
function focusLoginCode() {
  const b = loginCodeBoxes();
  (b.find((x) => !x.value) || b[0])?.focus();
}
(function wireLoginOtp() {
  const boxes = loginCodeBoxes();
  boxes.forEach((box, i) => {
    box.addEventListener("input", () => {
      box.value = box.value.replace(/\D/g, "").slice(0, 1); // digits only
      if (box.value && i < boxes.length - 1) boxes[i + 1].focus(); // auto-advance
    });
    box.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        $("#login-verify").click();
      } else if (e.key === "Backspace" && !box.value && i > 0) {
        boxes[i - 1].value = "";
        boxes[i - 1].focus();
        e.preventDefault();
      } else if (e.key === "ArrowLeft" && i > 0) {
        boxes[i - 1].focus();
        e.preventDefault();
      } else if (e.key === "ArrowRight" && i < boxes.length - 1) {
        boxes[i + 1].focus();
        e.preventDefault();
      }
    });
    box.addEventListener("paste", (e) => {
      // paste a whole code
      e.preventDefault();
      const digits = (
        (e.clipboardData || window.clipboardData).getData("text") || ""
      )
        .replace(/\D/g, "")
        .slice(0, boxes.length);
      if (!digits) return;
      digits.split("").forEach((d, k) => {
        if (boxes[k]) boxes[k].value = d;
      });
      (boxes[Math.min(digits.length, boxes.length - 1)] || box).focus();
      if (digits.length >= boxes.length) $("#login-verify").click();
    });
  });
})();
$("#logout-btn").onclick = async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (e) {}
  showLogin();
};
