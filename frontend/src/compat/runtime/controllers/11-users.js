// ---- users (admin) ----
function accessCell(u) {
  if (u.role === "admin")
    return '<span class="access-cell">All projects <span class="muted">(admin)</span></span>';
  if (u.all_projects) return '<span class="access-cell">All projects</span>';
  const ids = u.project_ids || [];
  if (!ids.length)
    return '<span class="access-cell" style="color:var(--red)">No projects</span>';
  const names = ids.map((id) => {
    const p = ALL_PROJECTS_CACHE.find((x) => x.id === id);
    return esc(p ? p.name || p.id : id);
  });
  return `<span class="access-cell">${names.map((n) => `<span class="chip">${n}</span>`).join("")}</span>`;
}
function _userMatchesFilters(u) {
  const q = ($("#u-search")?.value || "").trim().toLowerCase();
  const st = $("#u-filter-status")?.value || "";
  const ro = $("#u-filter-role")?.value || "";
  if (
    q &&
    !(
      (u.email || "").toLowerCase().includes(q) ||
      (u.name || "").toLowerCase().includes(q)
    )
  )
    return false;
  if (ro && u.role !== ro) return false;
  if (st) {
    const pending = u.invite_status === "pending";
    if (st === "pending" && !pending) return false;
    if (st === "active" && (pending || !u.active)) return false;
    if (st === "disabled" && (pending || u.active)) return false;
  }
  return true;
}
async function loadUsers() {
  skIn("#u-list", skeleton.table(7, 6, "Loading users"));
  try {
    if (!ALL_PROJECTS_CACHE.length) {
      try {
        const pr = await api("/api/projects");
        ALL_PROJECTS_CACHE = pr.projects || [];
      } catch (e) {}
    }
    const r = await api("/api/users");
    window._USERS_CACHE = r.users;
    renderUsers();
  } catch (e) {
    $("#u-list").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}
function renderUsers() {
  const all = window._USERS_CACHE || [];
  const rows = all.filter(_userMatchesFilters);
  const c = $("#u-count");
  if (c) c.textContent = `${rows.length} of ${all.length}`;
  // Counted over ALL users (not the filtered/visible rows) — this is the same
  // "how many active admins exist" question the backend guard answers, just
  // computed client-side so the UI can proactively hide/redirect instead of
  // showing a button that only fails with a raw error on click.
  const activeAdmins = all.filter((x) => x.role === "admin" && x.active).length;
  if (!rows.length) {
    $("#u-list").innerHTML = all.length
      ? '<div class="muted" style="padding:16px 0">No users match these filters.</div>'
      : '<div class="muted" style="padding:16px 0">No users yet. Invite your first teammate above.</div>';
    return;
  }
  $("#u-list").innerHTML =
    `<table><tr><th>Email</th><th>Name</th><th>Role</th><th>Access</th><th>Status</th><th>Last login</th><th></th></tr>` +
    rows
      .map((u) => {
        const self = ME && ME.id === u.id;
        const pending = u.invite_status === "pending";
        const status = pending
          ? '<span class="badge" style="background:rgba(216,158,44,.18);color:#e9c46a">invite pending</span>'
          : `<span class="badge ${u.active ? "new" : ""}">${u.active ? "active" : "disabled"}</span>`;
        const ICON = {
          access:
            '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 4v5c0 4-3 7-7 9-4-2-7-5-7-9V7z"/></svg>',
          resend:
            '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l9 6 9-6"/><rect x="3" y="5" width="18" height="14" rx="2"/></svg>',
          cancel:
            '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>',
          disable:
            '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M5 5l14 14"/></svg>',
          enable:
            '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
          lock: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
          del: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>',
        };
        const manageAccess =
          u.role === "admin"
            ? ""
            : `<button class="u-action" onclick="manageAccess('${u.id}')" title="Manage project access">${ICON.access}Access</button>`;
        // The only active admin can't disable themselves — the backend already
        // refuses this (it would lock everyone out), so don't even show a button
        // that can only ever fail. Offer the actual way out instead: add another
        // admin first.
        const isSoleAdminSelf =
          self && u.role === "admin" && u.active && activeAdmins <= 1;
        const actions = pending
          ? `${manageAccess}<button class="u-action" onclick="resendInvite('${u.id}','${esc(u.email)}')" title="Resend invite email">${ICON.resend}Resend</button>
           <button class="u-action danger" onclick="cancelInvite('${u.id}','${esc(u.email)}')" title="Cancel this invite">${ICON.cancel}Cancel</button>`
          : isSoleAdminSelf
            ? `${manageAccess}<button class="u-action" onclick="promptAdminHandoff()" title="You're the only admin — add another admin first to unlock this">${ICON.lock}Add admin to unlock</button>`
            : `${manageAccess}<button class="u-action" onclick="toggleUser('${u.id}',${u.active ? "false" : "true"})" title="${u.active ? "Disable this user" : "Enable this user"}">${u.active ? ICON.disable + "Disable" : ICON.enable + "Enable"}</button>
           ${self ? "" : `<button class="u-action danger" onclick="delUser('${u.id}','${esc(u.email)}')" title="Delete this user">${ICON.del}Delete</button>`}`;
        return `<tr><td>${esc(u.email)}${self ? ' <span class="muted">(you)</span>' : ""}</td><td>${esc(u.name || "")}</td>
        <td><select onchange="setUserRole('${u.id}',this.value)" style="width:auto">${["viewer", "editor", "admin"].map((x) => `<option ${x === u.role ? "selected" : ""}>${x}</option>`).join("")}</select></td>
        <td>${accessCell(u)}</td>
        <td>${status}</td>
        <td class="muted">${u.last_login ? new Date(u.last_login * 1000).toLocaleString() : pending ? "awaiting first sign-in" : "never"}</td>
        <td><div class="u-actions">${actions}</div></td></tr>`;
      })
      .join("") +
    `</table>`;
}
// Guided hand-off: shown instead of "Disable" when you're the only active admin.
// Cancel = "keep using this local admin" (just closes, nothing changes). Confirm
// jumps to the existing invite form above, preset to the Admin role, so the next
// admin can be added through the normal invite flow (works with or without SMTP —
// without it, the invite still creates the account and the link can be shared
// manually; see the "Resend" flow once email is configured).
window.promptAdminHandoff = async () => {
  const html = `<p style="margin:0 0 10px">You're the <b>only admin</b> for this workspace, so disabling your own
    access isn't allowed — that would lock everyone out.</p>
  <p class="muted" style="font-size:12.5px;margin:0">Assign another email address as admin first. Once they accept
    the invite and sign in, you'll be able to disable (or hand off) this local admin account.</p>`;
  const ok = await uiModalHTML(
    "Add another admin first",
    html,
    "Assign an admin email",
  );
  if (!ok) return; // "keep using this local admin" — no change
  const roleSel = $("#u-role");
  if (roleSel) {
    roleSel.value = "admin";
    roleSel.dispatchEvent(new Event("change"));
  }
  $("#u-email")?.scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => $("#u-email")?.focus(), 300);
  toast("Role preset to Admin — enter their email above and click Invite.");
};
// Re-render on filter changes (client-side, no refetch).
["u-search", "u-filter-status", "u-filter-role"].forEach((id) => {
  const el = document.getElementById(id);
  if (el)
    el.addEventListener("input", () => {
      try {
        renderUsers();
      } catch (e) {}
    });
});
// Manage a user's project access via a prompt-driven modal (checkbox list).
window.manageAccess = async (id) => {
  const u = (window._USERS_CACHE || []).find((x) => x.id === id);
  if (!u) return;
  if (!ALL_PROJECTS_CACHE.length) {
    try {
      const pr = await api("/api/projects");
      ALL_PROJECTS_CACHE = pr.projects || [];
    } catch (e) {}
  }
  const cur = new Set(u.all_projects ? [] : u.project_ids || []);
  const rows =
    ALL_PROJECTS_CACHE.map(
      (p) =>
        `<label data-name="${esc((p.name || p.id).toLowerCase())}" style="display:flex;gap:8px;align-items:center;padding:4px 0"><input type="checkbox" data-pid="${esc(p.id)}" ${cur.has(p.id) ? "checked" : ""}/> ${esc(p.name || p.id)}</label>`,
    ).join("") || '<span class="muted">No projects exist yet.</span>';
  const html = `<div style="margin-bottom:8px"><label class="radio-inline"><input type="radio" name="ma-scope" value="all" ${u.all_projects ? "checked" : ""}/> All projects</label>
    <label class="radio-inline" style="margin-left:16px"><input type="radio" name="ma-scope" value="some" ${u.all_projects ? "" : "checked"}/> Specific</label></div>
    <input id="ma-search" type="search" placeholder="Search projects…" ${u.all_projects ? "hidden" : ""} style="width:100%;margin-bottom:8px"/>
    <div id="ma-list" ${u.all_projects ? "hidden" : ""} style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:10px">${rows}</div>`;
  const ok = await uiModalHTML(
    `Project access — ${esc(u.email)}`,
    html,
    "Save access",
  );
  if (!ok) return;
  const mode =
    (document.querySelector('input[name="ma-scope"]:checked') || {}).value ||
    "all";
  const all_projects = mode === "all";
  const project_ids = all_projects
    ? []
    : [...document.querySelectorAll("#ma-list input[data-pid]:checked")].map(
        (c) => c.getAttribute("data-pid"),
      );
  if (!all_projects && !project_ids.length) {
    toast("Select at least one project, or choose All projects.", true);
    return;
  }
  try {
    await api(`/api/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ all_projects, project_ids }),
    });
    toast("Project access updated");
    loadUsers();
  } catch (e) {
    toast(e.message, {
      type: "err",
      title: "Couldn't update project access",
    });
  }
};
// ---- project-access picker (invite form) ----
let ALL_PROJECTS_CACHE = [];
async function loadProjectPicker() {
  try {
    const r = await api("/api/projects");
    ALL_PROJECTS_CACHE = r.projects || [];
  } catch (e) {
    ALL_PROJECTS_CACHE = [];
  }
  const box = $("#u-proj-list");
  if (!box) return;
  box.innerHTML = ALL_PROJECTS_CACHE.length
    ? ALL_PROJECTS_CACHE.map(
        (p) =>
          `<label><input type="checkbox" value="${esc(p.id)}"/> ${esc(p.name || p.id)}</label>`,
      ).join("")
    : '<span class="empty">No projects yet — create one first, or grant access to all.</span>';
}
function inviteScope() {
  const mode =
    (document.querySelector('input[name="u-scope"]:checked') || {}).value ||
    "all";
  const role = $("#u-role").value;
  if (role === "admin" || mode === "all")
    return { all_projects: true, project_ids: [] };
  const ids = [...document.querySelectorAll("#u-proj-list input:checked")].map(
    (c) => c.value,
  );
  return { all_projects: false, project_ids: ids };
}
// Toggle the checklist when the radio changes; hide it entirely for admin role.
document.addEventListener("change", (e) => {
  if (e.target && (e.target.name === "u-scope" || e.target.id === "u-role")) {
    const role = $("#u-role")?.value,
      mode =
        (document.querySelector('input[name="u-scope"]:checked') || {}).value ||
        "all";
    const list = $("#u-proj-list"),
      acc = $("#u-proj-access");
    if (!list || !acc) return;
    const adminForcesAll = role === "admin";
    acc
      .querySelectorAll('input[name="u-scope"]')
      .forEach((r) => (r.disabled = adminForcesAll));
    list.hidden = adminForcesAll || mode !== "some";
    $("#u-proj-hint").textContent = adminForcesAll
      ? "Admins always have access to all projects."
      : mode === "some"
        ? "Select the projects this user can access."
        : "This user will have access to every project.";
  }
});
$("#u-invite").onclick = async () => {
  const email = $("#u-email").value.trim(),
    name = $("#u-name").value.trim(),
    role = $("#u-role").value;
  if (!email) {
    toast("Email required", true);
    return;
  }
  const scope = inviteScope();
  if (!scope.all_projects && scope.project_ids.length === 0) {
    toast("Select at least one project, or choose All projects.", true);
    return;
  }
  try {
    const r = await api("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name, role, ...scope }),
    });
    $("#u-email").value = "";
    $("#u-name").value = "";
    const msg = (r && r.message) || "User created.";
    $("#u-msg").innerHTML = esc(msg);
    if (r && (r.delivery === "refused" || r.delivery === "error")) {
      toast(msg, {
        type: "warn",
        title: "User created, but invitation email failed",
      });
    } else {
      toast(msg);
    }
    loadUsers();
  } catch (e) {
    toast(e.message, {
      type: "err",
      title: "Couldn't invite user",
    });
  }
};
window.setUserRole = async (id, role) => {
  const u = (window._USERS_CACHE || []).find((x) => x.id === id);
  const who = u ? u.name || u.email : "this user";
  const desc = window.RBAC && RBAC.DESC[role] ? ` ${RBAC.DESC[role]}` : "";
  if (
    !(await uiConfirm(
      `Change ${esc(who)}'s role to "${role}"?${desc} They'll be re-authenticated with the new permissions.`,
      "Change role",
      "Change role",
    ))
  ) {
    loadUsers();
    return; // revert the dropdown
  }
  try {
    await api(`/api/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    toast(`Role changed to ${role}.`);
    loadUsers();
  } catch (e) {
    toast(e.message, {
      type: "err",
      title: "Couldn't change user role",
    });
    loadUsers();
  }
};
window.toggleUser = async (id, active) => {
  try {
    await api(`/api/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    });
    toast(active ? "Enabled" : "Disabled");
    loadUsers();
  } catch (e) {
    toast(e.message, {
      type: "err",
      title: "Couldn't update user status",
    });
  }
};
window.delUser = async (id, email) => {
  if (!(await uiConfirm(`Delete ${email}?`, "Delete User", "Delete", true)))
    return;
  try {
    await api(`/api/users/${id}`, { method: "DELETE" });
    toast("User deleted");
    loadUsers();
  } catch (e) {
    toast(e.message, {
      type: "err",
      title: "Couldn't delete user",
    });
  }
};
window.resendInvite = async (id, email) => {
  try {
    const r = await api(`/api/users/${id}/resend-invite`, { method: "POST" });
    const msg = (r && r.message) || "Invite re-sent.";
    $("#u-msg").innerHTML = esc(msg);
    if (r && (r.delivery === "refused" || r.delivery === "error")) {
      toast(msg, {
        type: "warn",
        title: "Invitation email not sent",
      });
    } else {
      toast(msg);
    }
    loadUsers();
  } catch (e) {
    toast(e.message, {
      type: "err",
      title: "Couldn't resend invitation",
    });
  }
};
window.cancelInvite = async (id, email) => {
  if (
    !(await uiConfirm(
      `Cancel the pending invite for ${email}?`,
      "Cancel Invite",
      "Cancel invite",
      true,
    ))
  )
    return;
  try {
    await api(`/api/users/${id}/cancel-invite`, { method: "POST" });
    toast("Invite cancelled");
    loadUsers();
  } catch (e) {
    toast(e.message, {
      type: "err",
      title: "Couldn't cancel invitation",
    });
  }
};
async function loadAudit() {
  const box = $("#audit-list");
  if (!box) return;
  skIn("#audit-list", skeleton.table(5, 6, "Loading audit log"));
  try {
    const r = await api("/api/audit-logs?limit=100");
    const logs = r.logs || [];
    if (!logs.length) {
      box.innerHTML = '<span class="muted">No audit entries yet.</span>';
      return;
    }
    const fmt = (ts) => {
      try {
        return new Date(ts * 1000).toLocaleString();
      } catch (e) {
        return "";
      }
    };
    box.innerHTML =
      `<table><tr><th>When</th><th>Action</th><th>Actor</th><th>Target</th><th>Details</th></tr>` +
      logs
        .map((l) => {
          const det =
            l.detail ||
            [
              l.old && `from ${JSON.stringify(l.old)}`,
              l.new && `to ${JSON.stringify(l.new)}`,
            ]
              .filter(Boolean)
              .join(" ");
          const danger = /deleted|denied|disabled/.test(l.action || "");
          return `<tr><td class="muted" style="white-space:nowrap">${fmt(l.ts)}</td>
          <td><span class="badge ${danger ? "" : "new"}" style="${danger ? "color:var(--red)" : ""}">${esc(l.action || "")}</span></td>
          <td>${esc(l.actor_email || l.actor_id || "—")}</td>
          <td>${esc(l.target || "—")}</td>
          <td class="muted" style="font-size:11.5px">${esc(det || "")}</td></tr>`;
        })
        .join("") +
      `</table>`;
  } catch (e) {
    box.innerHTML = `<div class="err">Couldn't load the audit log. ${esc(e.message)}</div>`;
  }
}

