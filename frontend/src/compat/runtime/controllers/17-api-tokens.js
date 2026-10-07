// ---- API tokens (admin) — issue #37 ----
function _apiTokenAccessCell(t) {
  if (t.all_projects) return '<span class="access-cell">All projects</span>';
  const ids = t.project_ids || [];
  if (!ids.length)
    return '<span class="access-cell" style="color:var(--red)">No projects</span>';
  const names = ids.map((id) => {
    const p = ALL_PROJECTS_CACHE.find((x) => x.id === id);
    return esc(p ? p.name || p.id : id);
  });
  return `<span class="access-cell">${names.map((n) => `<span class="chip">${n}</span>`).join("")}</span>`;
}
async function loadApiTokens() {
  const list = $("#at-list");
  if (!list) return;
  skIn("#at-list", skeleton.table(4, 6, "Loading API tokens"));
  try {
    if (!ALL_PROJECTS_CACHE.length) {
      try {
        const pr = await api("/api/projects");
        ALL_PROJECTS_CACHE = pr.projects || [];
      } catch (e) {}
    }
    renderApiTokenProjectPicker();
    const r = await api("/api/api-tokens");
    window._API_TOKENS_CACHE = r.tokens || [];
    renderApiTokens();
  } catch (e) {
    list.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}
function renderApiTokenProjectPicker() {
  const box = $("#at-proj-list");
  if (!box) return;
  box.innerHTML = ALL_PROJECTS_CACHE.length
    ? ALL_PROJECTS_CACHE.map(
        (p) =>
          `<label><input type="checkbox" value="${esc(p.id)}"/> ${esc(p.name || p.id)}</label>`,
      ).join("")
    : '<span class="empty">No projects yet — create one first, or grant access to all.</span>';
}
function renderApiTokens() {
  const rows = window._API_TOKENS_CACHE || [];
  if (!rows.length) {
    $("#at-list").innerHTML =
      '<div class="muted" style="padding:16px 0">No API tokens yet. Create one above for a CI job or other machine caller.</div>';
    return;
  }
  const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : "never");
  $("#at-list").innerHTML =
    `<table><tr><th>Name</th><th>Role</th><th>Access</th><th>Status</th><th>Last used</th><th>Expires</th><th></th></tr>` +
    rows
      .map((t) => {
        const status = t.active
          ? '<span class="badge new">active</span>'
          : '<span class="badge">revoked</span>';
        const expires = t.expires_at ? fmt(t.expires_at) : "never";
        const action = t.active
          ? `<button class="u-action danger" onclick="revokeApiToken('${t.id}','${esc(t.name)}')">Revoke</button>`
          : "";
        return `<tr><td>${esc(t.name)}</td><td>${esc(t.role)}</td><td>${_apiTokenAccessCell(t)}</td>
        <td>${status}</td><td class="muted">${fmt(t.last_used_at)}</td><td class="muted">${expires}</td>
        <td><div class="u-actions">${action}</div></td></tr>`;
      })
      .join("") +
    `</table>`;
}
function _apiTokenScope() {
  const mode =
    (document.querySelector('input[name="at-scope"]:checked') || {}).value ||
    "all";
  if (mode === "all") return { all_projects: true, project_ids: [] };
  const ids = [...document.querySelectorAll("#at-proj-list input:checked")].map(
    (c) => c.value,
  );
  return { all_projects: false, project_ids: ids };
}
document.addEventListener("change", (e) => {
  if (e.target && e.target.name === "at-scope") {
    const mode = e.target.value;
    const list = $("#at-proj-list");
    if (list) list.hidden = mode !== "some";
  }
});
window.revokeApiToken = async (id, name) => {
  if (!(await uiConfirm(`Revoke the token "${name}"? Any caller using it loses access immediately.`, "Revoke Token", "Revoke", true)))
    return;
  try {
    await api(`/api/api-tokens/${id}`, { method: "DELETE" });
    toast("Token revoked");
    loadApiTokens();
  } catch (e) {
    toast(e.message, true);
  }
};
$("#at-create") &&
  ($("#at-create").onclick = async () => {
    const name = $("#at-name").value.trim();
    const role = $("#at-role").value;
    const expiresDaysRaw = $("#at-expires-days").value.trim();
    if (!name) {
      toast("Name required", true);
      return;
    }
    const scope = _apiTokenScope();
    if (!scope.all_projects && scope.project_ids.length === 0) {
      toast("Select at least one project, or choose All projects.", true);
      return;
    }
    const body = { name, role, ...scope };
    if (expiresDaysRaw) body.expires_in_days = Number(expiresDaysRaw);
    try {
      const r = await api("/api/api-tokens", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      $("#at-name").value = "";
      $("#at-expires-days").value = "";
      await uiModalHTML(
        "Token created — copy it now",
        `<p style="margin:0 0 10px">This token won't be shown again. Store it somewhere safe (e.g. a CI secret).</p>
         <input readonly value="${esc(r.plaintext)}" onclick="this.select()" style="width:100%;font-family:monospace;font-size:12.5px"/>`,
        "Done",
      );
      loadApiTokens();
    } catch (e) {
      toast(e.message, true);
    }
  });
