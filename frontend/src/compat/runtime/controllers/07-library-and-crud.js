// Step library CRUD moved to React: src/features/step-library/ (#257).

// ---- feature delete / rename ----
$("#d-del").onclick = async () => {
  if (!currentFeature) return;
  const featureId = currentFeature;
  openCaseConfirmation({
    title: "Delete feature",
    copy: "This removes the feature, its document chunks, and its testcase links. Testcases still linked to another feature will not be deleted.",
    summary: `<b>${esc($("#d-name").textContent)}</b><div class="muted" style="margin-top:6px">${esc($("#d-meta").textContent)}</div>`,
    confirmLabel: "Delete feature",
    danger: true,
    onConfirm: async () => {
      const r = await api("/api/features/" + featureId, { method: "DELETE" });
      currentFeature = null;
      showFeatureList();
      loadFeatures();
      refreshStatus();
      toast(
        `Feature deleted · ${r.removed_orphan_cases} orphan testcase(s) removed · ${r.preserved_shared_cases} shared testcase(s) preserved`,
      );
    },
  });
};
$("#d-rename").onclick = async () => {
  if (!currentFeature) return;
  const name = await uiPrompt(
    "Rename feature",
    "Feature name",
    $("#d-name").textContent,
  );
  if (!name) return;
  await api("/api/features/" + currentFeature, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  openFeature(currentFeature);
  loadFeatures();
  toast("Renamed");
};
// ---- new version ----
$("#d-newver").onclick = () => {
  if (!currentFeature) return;
  $("#vm-feat").textContent =
    `${$("#d-name").textContent} — current ${$("#d-version").selectedOptions[0]?.textContent || ""}`;
  $("#vm-file").value = "";
  $("#vm-text").value = "";
  if ($("#vm-confluence")) $("#vm-confluence").value = "";
  if ($("#vm-figma")) $("#vm-figma").value = "";
  $("#vm-replace").checked = false;
  $("#vm-msg").textContent = "";
  $("#vmodal").classList.add("show");
};
if ($("#d-reuse-imports"))
  $("#d-reuse-imports").onclick = () => {
    if (!currentFeature) {
      toast("Open a feature first", true);
      return;
    }
    openImportLibraryModal(currentFeature);
  };
$("#vm-cancel").onclick = () => $("#vmodal").classList.remove("show");
$("#vm-go").onclick = async () => {
  const splitLinks = (el) =>
    ((el && el.value) || "")
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  const vConfl = splitLinks($("#vm-confluence"));
  const vFigma = splitLinks($("#vm-figma"));
  if (
    !$("#vm-file").files.length &&
    !$("#vm-text").value.trim() &&
    !vConfl.length &&
    !vFigma.length
  ) {
    $("#vm-msg").innerHTML =
      `<span class="err">Upload a doc, paste text, or add a Confluence/Figma link.</span>`;
    return;
  }
  $("#vm-go").disabled = true;
  $("#vm-msg").textContent = "uploading + diffing against previous version…";
  const fd = new FormData();
  for (const f of $("#vm-file").files) fd.append("files", f);
  fd.append("text", $("#vm-text").value);
  fd.append("replace", $("#vm-replace").checked ? "true" : "false");
  vConfl.forEach((u) => fd.append("confluence_url", u));
  vFigma.forEach((u) => fd.append("figma_url", u));
  try {
    const r = await api(`/api/features/${currentFeature}/versions`, {
      method: "POST",
      body: fd,
    });
    const d = r.diff || {};
    $("#vm-msg").innerHTML =
      `<span class="ok">v${r.version} created — ${d.kept || 0} kept${d.retired && d.retired.length ? `, ${d.retired.length} retired` : ""}. Generating new cases…</span>`;
    toast(`Version ${r.version} created`);
    setTimeout(() => {
      $("#vmodal").classList.remove("show");
      openFeature(r.feature_id).then(() =>
        watchFeatureGen(r.job_id, r.feature_id),
      );
      loadFeatures();
    }, 1200);
  } catch (e) {
    $("#vm-msg").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  } finally {
    $("#vm-go").disabled = false;
  }
};

