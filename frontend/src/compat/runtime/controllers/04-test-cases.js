// ---- test cases view ----
async function initCases() {
  await loadProjects();
  try {
    const t = await api("/api/tags");
    $("#tc-tag").innerHTML =
      `<option value="">Any tag</option>` +
      t.tags.map((x) => `<option>${esc(x)}</option>`).join("");
  } catch (e) {}
  // feature filter depends on project
  await fillFeatFilter();
  loadCases();
}
async function fillFeatFilter() {
  try {
    const pf = $("#tc-proj").value;
    const r = await api("/api/features" + (pf ? `?project_id=${pf}` : ""));
    $("#tc-feat").innerHTML =
      `<option value="">All features</option>` +
      r.features
        .map((f) => `<option value="${f.id}">${esc(f.name)}</option>`)
        .join("");
  } catch (e) {}
}
$("#tc-proj").onchange = async () => {
  $("#tc-feat").value = "";
  await fillFeatFilter();
  tcPage = 0;
  loadCases();
};
$("#tc-feat").onchange = () => {
  tcPage = 0;
  loadCases();
};
$("#tc-type").onchange = () => {
  tcPage = 0;
  loadCases();
};
$("#tc-tag").onchange = () => {
  tcPage = 0;
  loadCases();
};
$("#tc-status").onchange = () => {
  tcPage = 0;
  loadCases();
};
$("#tc-result").onchange = () => {
  tcPage = 0;
  loadCases();
};
$("#tc-lineage").onchange = () => {
  tcPage = 0;
  loadCases();
};
$("#tc-q").onkeydown = (e) => {
  if (e.key === "Enter") {
    tcPage = 0;
    loadCases();
  }
};
$("#tc-apply").onclick = () => {
  tcPage = 0;
  loadCases();
};
$("#tc-reset").onclick = async () => {
  $("#tc-proj").value = "";
  $("#tc-type").value = "";
  $("#tc-tag").value = "";
  $("#tc-status").value = "active";
  $("#tc-result").value = "";
  $("#tc-lineage").value = "";
  $("#tc-q").value = "";
  tcPage = 0;
  await fillFeatFilter();
  $("#tc-feat").value = "";
  loadCases();
};
async function loadCases() {
  const qp = new URLSearchParams();
  const m = {
    project_id: $("#tc-proj").value,
    feature_id: $("#tc-feat").value,
    type: $("#tc-type").value,
    tag: $("#tc-tag").value,
    q: $("#tc-q").value.trim(),
    status: $("#tc-status").value,
    execution_status: $("#tc-result").value,
    lineage: $("#tc-lineage").value,
  };
  Object.entries(m).forEach(([k, v]) => {
    if (v) qp.set(k, v);
  });
  qp.set("limit", 25);
  qp.set("skip", tcPage * 25);
  skIn("#tc-list", skeleton.rows(8, "Loading test cases"));
  try {
    const r = await api("/api/test-cases?" + qp.toString());
    $("#tc-list").innerHTML = r.items.length
      ? `<div class="testcase-list">` +
        caseListHeader("cases") +
        r.items.map(testcaseRow).join("") +
        `</div>`
      : `<span class="muted">No test cases match the selected filters.</span>`;
    updateCaseSelection();
    const activeFilters = [
      $("#tc-proj").selectedOptions[0]?.textContent !== "All projects"
        ? $("#tc-proj").selectedOptions[0]?.textContent
        : null,
      $("#tc-feat").value
        ? $("#tc-feat").selectedOptions[0]?.textContent
        : null,
      $("#tc-type").value ? typeLabel($("#tc-type").value) : null,
      $("#tc-tag").value ? `tag: ${$("#tc-tag").value}` : null,
      $("#tc-status").value !== "active"
        ? `lifecycle: ${$("#tc-status").value}`
        : null,
      $("#tc-result").value ? `result: ${$("#tc-result").value}` : null,
      $("#tc-lineage").value
        ? `lineage: ${$("#tc-lineage").selectedOptions[0]?.textContent}`
        : null,
      $("#tc-q").value.trim()
        ? `search contains “${$("#tc-q").value.trim()}”`
        : null,
    ].filter(Boolean);
    $("#tc-summary").textContent =
      `${r.total} matching test case${r.total === 1 ? "" : "s"}${activeFilters.length ? ` · ${activeFilters.join(" · ")}` : ""}`;
    const pages = Math.max(1, Math.ceil(r.total / 25));
    $("#tc-pager").innerHTML =
      `<div style="display:flex;align-items:center;justify-content:center;gap:14px;margin:16px 0 4px">
      <button class="go" id="tcp" ${tcPage <= 0 ? "disabled" : ""} style="flex:0 0 auto;padding:6px 16px">‹ Prev</button>
      <span class="muted" style="font-size:12.5px;white-space:nowrap">${r.total} cases · page ${tcPage + 1} of ${pages}</span>
      <button class="go" id="tcn" ${tcPage >= pages - 1 ? "disabled" : ""} style="flex:0 0 auto;padding:6px 16px">Next ›</button></div>`;
    $("#tcp").onclick = () => {
      if (tcPage > 0) {
        tcPage--;
        loadCases();
      }
    };
    $("#tcn").onclick = () => {
      if (tcPage < pages - 1) {
        tcPage++;
        loadCases();
      }
    };
  } catch (e) {
    $("#tc-list").innerHTML =
      `<div class="empty-state"><div class="empty-state-icon">!</div><h3>Couldn't load test cases</h3><p>${esc(e.message)}</p><button class="ghost" onclick="loadCases()">Retry</button></div>`;
  }
}

const RESULT_LABELS = {
  untested: "Untested",
  passed: "Passed",
  failed: "Failed",
  blocked: "Blocked",
};
const resultSelect = (c) =>
  `<select class="result-select needs-editor ${esc(c.execution_status || "untested")}" aria-label="Latest execution result" onclick="event.stopPropagation()" onchange="setCaseResult('${c.id}',this.value,this)"><option value="untested" ${(c.execution_status || "untested") === "untested" ? "selected" : ""}>Untested</option><option value="passed" ${c.execution_status === "passed" ? "selected" : ""}>Passed</option><option value="failed" ${c.execution_status === "failed" ? "selected" : ""}>Failed</option><option value="blocked" ${c.execution_status === "blocked" ? "selected" : ""}>Blocked</option></select>`;
function testcaseRow(c) {
  const lineageImported = c.imported || c.association_origin === "imported";
  const lineageBadge = lineageImported
    ? `<span class="badge reused" style="margin-left:7px" title="This test case came from an uploaded sheet (imported / reused across features)">Imported from sheet</span>`
    : c.inherited
      ? `<span class="badge reused" style="margin-left:7px">Inherited${c.source_feature_name ? ` from ${esc(c.source_feature_name)}` : ""}</span>`
      : "";
  const title = caseTitle(c);
  return `<div class="testcase-item" data-case-item="${c.id}" style="${c.deprecated ? "opacity:.6" : ""}">
    <div class="testcase-row" onclick="viewCase('${c.id}',this)">
      <input class="case-select" data-case-id="${esc(c.id)}" type="checkbox" aria-label="Select ${esc(title)}" onclick="event.stopPropagation()"/>
      <span class="testcase-chevron">›</span>
      <div><div class="testcase-title">${c.display_id ? `<span class="badge" style="margin-right:7px">${esc(c.display_id)}</span>` : ""}${esc(title)}${lineageBadge}</div><div class="testcase-sub">${esc(typeLabel(c.type))} · ${c.step_count} step${c.step_count === 1 ? "" : "s"}${c.shared_with_features > 1 ? ` · linked to ${c.shared_with_features} features` : ""}${c.deprecated ? " · deprecated" : ""}</div></div>
      ${resultSelect(c)}
      <span class="testcase-priority">${prioBadge(c.priority)}</span>
      <button class="testcase-delete needs-editor" title="Delete testcase" aria-label="Delete testcase" onclick="event.stopPropagation();requestDeleteCase('${c.id}')"><span>Delete</span></button>
    </div>
    <div class="testcase-detail" data-case-detail="${c.id}"></div>
  </div>`;
}

const caseMetaText = (value) => {
  if (value === null || value === undefined || value === "")
    return "Not specified";
  if (Array.isArray(value))
    return value.length
      ? value
          .map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x)))
          .join("\n• ")
      : "None";
  if (typeof value === "object")
    return Object.entries(value)
      .map(
        ([k, v]) =>
          `${k.replaceAll("_", " ")}: ${Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : v}`,
      )
      .join("\n");
  return String(value);
};
function cleanRequirementText(value) {
  let text = String(value || "").trim();
  const original = text.toLowerCase();
  const sourceKeyword = String.raw`(?:prd|hld|lld|spec|specification|document|requirements?|product|business|functional|technical|api|ui|ux|security|compliance|architecture|design|uploaded|source|reference)(?:\s+[\w.-]+){0,5}`;
  const sourceExact = String.raw`(?:[A-Z][A-Z0-9_-]{1,20}|[\w.-]+\.(?:pdf|docx?|md|txt))`;
  const kind = String.raw`(?:document|docs?|spec(?:ification)?|requirements?|rules?|design|architecture|guide|policy|story|ticket|epic|acceptance\s+criteria)`;
  const verb = String.raw`(?:requires?|states?|specifies?|defines?|indicates?|says?|suggests?|allows?|documents?|mandates?|notes?|describes?)`;
  text = text.replace(
    new RegExp(
      `^according\\s+to\\s+(?:the\\s+)?(?:${sourceExact}|${sourceKeyword})(?:\\s+${kind})?\\s*[,;:]\\s*`,
      "i",
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceExact}(?:\\s+${kind})?\\s*(?:rule|requirement)?(?:\\s*:\\s*|\\s+-\\s+)`,
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceKeyword}(?:\\s+${kind})?\\s*(?:rule|requirement)?(?:\\s*:\\s*|\\s+-\\s+)`,
      "i",
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceExact}(?:\\s+${kind})?\\s+${verb}\\s+(?:that\\s+)?`,
    ),
    "",
  );
  text = text.replace(
    new RegExp(
      `^(?:the\\s+)?${sourceKeyword}(?:\\s+${kind})?\\s+${verb}\\s+(?:that\\s+)?`,
      "i",
    ),
    "",
  );
  if (original.includes("requires"))
    text = text.replace(/\bto be\b/i, "must be");
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}
const EXPECTED_LABELS = {
  status_code: "Status code",
  db_changes: "Database changes",
  side_effects: "Side effects",
  negative_assertions: "Must not happen",
};
function expectedValueHtml(value) {
  if (Array.isArray(value))
    return value.length
      ? `<ul>${value.map((item) => `<li>${esc(typeof item === "object" ? JSON.stringify(item) : item)}</li>`).join("")}</ul>`
      : `<span class="muted">None</span>`;
  if (value && typeof value === "object")
    return `<ul>${Object.entries(value)
      .map(
        ([key, item]) =>
          `<li><b>${esc(key.replaceAll("_", " "))}:</b> ${esc(Array.isArray(item) ? item.join(", ") : item)}</li>`,
      )
      .join("")}</ul>`;
  return `<span>${esc(value === null || value === undefined || value === "" ? "Not specified" : value)}</span>`;
}
function expectedResultHtml(value) {
  if (!value || typeof value !== "object" || Array.isArray(value))
    return `<div class="case-detail-value">${esc(caseMetaText(value))}</div>`;
  const preferred = [
    "status_code",
    "db_changes",
    "side_effects",
    "negative_assertions",
  ];
  const keys = [
    ...preferred.filter((k) => Object.prototype.hasOwnProperty.call(value, k)),
    ...Object.keys(value).filter((k) => !preferred.includes(k)),
  ];
  return `<div class="expected-grid">${keys.map((key) => `<div class="expected-row"><div class="expected-key">${esc(EXPECTED_LABELS[key] || key.replaceAll("_", " "))}</div><div class="expected-content">${expectedValueHtml(value[key])}</div></div>`).join("")}</div>`;
}
function caseDetailHtml(c) {
  const m = c.metadata || {};
  const title = caseTitle(c);
  const description =
    cleanRequirementText(
      m.description || m.intent || m.scenario || c.preconditions,
    ) || "No separate description was generated.";
  const endpoint = [m.method, m.endpoint || m.path].filter(Boolean).join(" ");
  const expected = m.expected_result || m.expected_behavior || m.result;
  const lineage = (c.features || [])
    .map(
      (f) =>
        `${f.name}${f.version ? ` v${f.version}` : ""}${f.origin ? ` · ${f.origin}` : ""}`,
    )
    .join("\n");
  // Imported when the backend flag says so, or any feature link's origin is an import.
  const isImported =
    c.imported ||
    (c.features || []).some((f) =>
      String(f.origin || "")
        .toLowerCase()
        .includes("import"),
    );
  const lineageText =
    (isImported ? "Imported from sheet\n" : "") +
    (lineage || "No feature lineage recorded");
  const importedBadge = isImported
    ? `<span class="badge reused" style="margin-left:6px" title="Came from an uploaded sheet">Imported from sheet</span>`
    : "";
  const steps = c.steps || [];
  return `<div class="case-detail-head"><div><div style="font-size:15px;font-weight:700">${c.display_id ? `<span class="badge" style="margin-right:8px">${esc(c.display_id)}</span>` : ""}${esc(title)}${importedBadge}</div><div style="margin-top:5px"><span class="badge ${esc(c.type)}">${esc(typeLabel(c.type))}</span> ${prioBadge(c.priority)} ${(c.tags || []).map((t) => `<span class="badge">${esc(t)}</span>`).join(" ")}</div></div><div style="display:flex;gap:7px"><button class="ghost needs-editor" onclick="event.stopPropagation();editCase('${c.id}')">Edit testcase</button><button class="ghost" onclick="event.stopPropagation();viewCase('${c.id}',this)">Close</button></div></div>
    <div class="case-detail-grid">
      <div class="case-detail-panel"><div class="case-detail-label">Description</div><div class="case-detail-value">${esc(caseMetaText(description))}</div></div>
      <div class="case-detail-panel"><div class="case-detail-label">Endpoint</div><div class="case-detail-value">${esc(endpoint || "Not applicable or not specified")}</div></div>
      <div class="case-detail-panel"><div class="case-detail-label">Expected result</div>${expectedResultHtml(expected)}</div>
      <div class="case-detail-panel"><div class="case-detail-label">Source lineage</div><div class="case-detail-value">${esc(lineageText)}</div></div>
    </div>
    <div class="case-steps-table"><div class="case-step case-step-head"><span>#</span><span>Step</span><span>Expected result</span></div>${steps.length ? steps.map((s, i) => `<div class="case-step"><span class="case-step-num">${i + 1}.</span><span>${esc(s.action)}</span><span class="case-step-expected">${esc(s.expected || "No separate expected result")}</span></div>`).join("") : `<div class="case-detail-loading">No detailed steps were saved for this testcase.</div>`}</div>`;
}
window.viewCase = async (cid, source) => {
  const item =
    source?.closest?.(`[data-case-item="${cid}"]`) ||
    document.querySelector(`[data-case-item="${cid}"]`);
  if (!item) return;
  const detail = item.querySelector(`[data-case-detail="${cid}"]`);
  if (item.classList.contains("open")) {
    item.classList.remove("open");
    return;
  }
  document
    .querySelectorAll(".testcase-item.open")
    .forEach((x) => x.classList.remove("open"));
  item.classList.add("open");
  if (detail.dataset.loaded) return;
  detail.innerHTML = skeleton.block("Loading test case details");
  try {
    const c = await api("/api/test-cases/" + cid);
    detail.innerHTML = caseDetailHtml(c);
    detail.dataset.loaded = "1";
  } catch (e) {
    detail.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
};
window.setCaseResult = async (cid, status, select) => {
  const old =
    [...select.options].find((o) => o.defaultSelected)?.value || "untested";
  select.disabled = true;
  try {
    await api(`/api/test-cases/${cid}/execution`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    select.className = `result-select ${status}`;
    [...select.options].forEach(
      (o) => (o.defaultSelected = o.value === status),
    );
    toast(`Marked ${RESULT_LABELS[status].toLowerCase()}`);
  } catch (e) {
    select.value = old;
    toast(e.message, true);
  } finally {
    select.disabled = false;
  }
};

// ---- case editor ----
window.editCase = async (cid) => {
  try {
    const c = await api("/api/test-cases/" + cid);
    editing = {
      id: cid,
      shared_with_features: c.shared_with_features || 0,
      steps: c.steps.map((s) => ({
        id: s.id,
        action: s.action,
        expected: s.expected,
        usage_count: s.usage_count,
      })),
    };
    $("#m-heading").textContent = "Edit test case";
    $("#m-title").value = c.title;
    $("#m-type").value = c.type;
    $("#m-prio").value = prioLabel(c.priority);
    $("#m-pre").value = c.preconditions || "";
    $("#m-tags").value = (c.tags || []).join(", ");
    $("#m-warn").textContent =
      c.shared_with_features > 1
        ? `Linked to ${c.shared_with_features} features. Testcase field changes appear in every linked feature; shared-step edits also update other cases that use those exact steps.`
        : "";
    $("#m-del").style.display = "";
    $("#m-del").onclick = () => requestDeleteCase(cid, c);
    renderSteps();
    $("#m-msg").textContent = "";
    $("#modal").classList.add("show");
  } catch (e) {
    toast(e.message, true);
  }
};
function renderSteps() {
  $("#m-steps").innerHTML = editing.steps
    .map(
      (s, i) => `
    <div class="steprow" draggable="true" data-i="${i}">
      <div class="drag-handle">⋮⋮</div>
      <textarea draggable="false" data-i="${i}" data-f="action" placeholder="action">${esc(s.action)}</textarea>
      <textarea draggable="false" data-i="${i}" data-f="expected" placeholder="expected">${esc(s.expected)}</textarea>
      <div class="ctrl"><button class="iconbtn" title="Remove step from this testcase" onclick="rmStep(${i})">×</button></div>
      ${s.usage_count > 1 ? `<div class="editor-shared-note">This exact step is shared by ${s.usage_count} testcases. Editing its text updates all of them; removing it only unlinks it from this testcase.</div>` : ""}
    </div>`,
    )
    .join("");

  $("#m-steps")
    .querySelectorAll("textarea")
    .forEach(
      (t) =>
        (t.oninput = (e) => {
          editing.steps[+e.target.dataset.i][e.target.dataset.f] =
            e.target.value;
        }),
    );

  let draggedIdx = null;
  const rows = $("#m-steps").querySelectorAll(".steprow");
  rows.forEach((row) => {
    row.addEventListener("dragstart", (e) => {
      draggedIdx = +row.dataset.i;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      rows.forEach((r) => r.classList.remove("drag-over"));
    });
    row.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      row.classList.add("drag-over");
    });
    row.addEventListener("dragleave", () => {
      row.classList.remove("drag-over");
    });
    row.addEventListener("drop", (e) => {
      e.preventDefault();
      row.classList.remove("drag-over");
      const targetIdx = +row.dataset.i;
      if (draggedIdx !== null && draggedIdx !== targetIdx) {
        const item = editing.steps.splice(draggedIdx, 1)[0];
        editing.steps.splice(targetIdx, 0, item);
        renderSteps();
      }
    });
  });
}
window.rmStep = (i) => {
  editing.steps.splice(i, 1);
  renderSteps();
};
$("#m-addstep").onclick = () => {
  editing.steps.push({ action: "", expected: "" });
  renderSteps();
};
function editorBody() {
  return {
    title: $("#m-title").value.trim(),
    type: $("#m-type").value,
    priority: $("#m-prio").value,
    preconditions: $("#m-pre").value.trim(),
    tags: $("#m-tags")
      .value.split(",")
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean),
    steps: editing.steps
      .filter((s) => s.action || s.expected)
      .map((s) =>
        s.id
          ? { id: s.id, action: s.action, expected: s.expected }
          : { action: s.action, expected: s.expected },
      ),
  };
}
function openCaseConfirmation({
  title,
  copy,
  summary,
  confirmLabel,
  danger = false,
  onConfirm,
  secondaryLabel = null,
  onSecondary = null,
}) {
  $("#cc-title").textContent = title;
  $("#cc-copy").textContent = copy;
  // Only show the summary box when there's actual summary content — otherwise it
  // renders as a stray empty input-looking box (role-change / delete confirmations).
  $("#cc-summary").innerHTML = summary || "";
  $("#cc-summary").style.display = summary ? "" : "none";
  $("#cc-error").textContent = "";
  $("#cc-confirm").textContent = confirmLabel;
  $("#cc-confirm").className = danger ? "danger" : "go";
  $("#cc-cancel").style.display = "";
  $("#cc-cancel").textContent = "Cancel";
  $("#cc-secondary").style.display = secondaryLabel ? "" : "none";
  $("#cc-secondary").textContent = secondaryLabel || "";
  $("#case-confirm").classList.add("show");
  $("#cc-cancel").onclick = () => $("#case-confirm").classList.remove("show");
  $("#cc-confirm").onclick = async () => {
    try {
      $("#cc-confirm").disabled = true;
      await onConfirm();
      $("#case-confirm").classList.remove("show");
    } catch (e) {
      $("#cc-error").textContent = e.message;
    } finally {
      $("#cc-confirm").disabled = false;
    }
  };
  $("#cc-secondary").onclick = secondaryLabel
    ? async () => {
        try {
          $("#cc-secondary").disabled = true;
          await onSecondary();
          $("#case-confirm").classList.remove("show");
        } catch (e) {
          $("#cc-error").textContent = e.message;
        } finally {
          $("#cc-secondary").disabled = false;
        }
      }
    : null;
}
function openInfoDialog({ title, copy, summary, closeLabel = "Close" }) {
  $("#cc-title").textContent = title;
  $("#cc-copy").textContent = copy;
  $("#cc-summary").innerHTML = summary || "";
  $("#cc-summary").style.display = summary ? "" : "none";
  $("#cc-error").textContent = "";
  $("#cc-secondary").style.display = "none";
  $("#cc-cancel").style.display = "none";
  $("#cc-confirm").textContent = closeLabel;
  $("#cc-confirm").className = "go";
  $("#case-confirm").classList.add("show");
  $("#cc-confirm").onclick = () => $("#case-confirm").classList.remove("show");
}
$("#m-save").onclick = () => {
  const body = editorBody();
  if (!body.title) {
    $("#m-msg").innerHTML = `<span class="err">Title is required.</span>`;
    return;
  }
  openCaseConfirmation({
    title: editing.id ? "Confirm testcase update" : "Confirm new testcase",
    copy: editing.id
      ? `Review the fields before updating “${body.title}”.`
      : `Create “${body.title}” in the selected feature.`,
    summary: `<div><b>${esc(body.title)}</b></div><div class="muted" style="margin-top:6px">${esc(typeLabel(body.type))} · ${prioLabel(body.priority)} · ${body.steps.length} step${body.steps.length === 1 ? "" : "s"}${editing.shared_with_features > 1 ? ` · linked to ${editing.shared_with_features} features` : ""}</div>`,
    confirmLabel: editing.id ? "Update testcase" : "Create testcase",
    onConfirm: () => saveCase(body),
  });
};
async function saveCase(body) {
  $("#m-save").disabled = true;
  $("#m-msg").textContent = "saving…";
  try {
    let r;
    if (editing.id) {
      r = await api("/api/test-cases/" + editing.id, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      $("#m-msg").innerHTML =
        `<span class="ok">Saved ${r.steps} steps${r.other_cases_affected_by_step_edits ? ` · ${r.other_cases_affected_by_step_edits} other case(s) updated via shared steps` : ""}</span>`;
    } else {
      r = await api("/api/test-cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, feature_id: editing.feature_id }),
      });
      $("#m-msg").innerHTML =
        `<span class="ok">Created${r && r.display_id ? ` — ${esc(r.display_id)}` : ""}</span>`;
      if (editing.cycle_id && r && r.id) {
        try {
          await api(`/api/test-cycles/${editing.cycle_id}/items`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ case_ids: [r.id] }),
          });
        } catch (e) {
          // The case itself was created fine (message above already reflects
          // that) -- this second call only links it into the current cycle,
          // and can legitimately be rejected, e.g. a duplicate-title guard in
          // add_cycle_items() for the same feature within this cycle. Swallowing
          // that silently used to leave the user thinking the case landed in
          // the cycle when it didn't, with no indication anything went wrong.
          $("#m-msg").innerHTML =
            `<span class="err">Created${r && r.display_id ? ` — ${esc(r.display_id)}` : ""}, but not added to this cycle: ${esc(e.message)}</span>`;
        }
      }
    }
    loadCases();
    loadSteps();
    if (currentFeature) openFeature(currentFeature);
    refreshStatus();
    if (
      window._cycle &&
      $("#cyc-detail-card") &&
      $("#cyc-detail-card").style.display !== "none"
    ) {
      openCycle(window._cycle);
    }
    document
      .querySelectorAll(`[data-case-detail="${editing.id}"]`)
      .forEach((x) => {
        x.dataset.loaded = "";
      });
    setTimeout(() => $("#modal").classList.remove("show"), 500);
  } catch (e) {
    $("#m-msg").innerHTML = `<span class="err">${esc(e.message)}</span>`;
    throw e;
  } finally {
    $("#m-save").disabled = false;
  }
}
$("#m-cancel").onclick = $("#m-close").onclick = () =>
  $("#modal").classList.remove("show");

