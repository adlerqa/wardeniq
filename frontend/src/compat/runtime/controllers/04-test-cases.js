// Test Cases screen (filters, list, pager) moved to React:
// src/features/test-cases/ (#257). The case detail, result select, editor and
// confirmation dialog below are still shared with the feature workspace (03).

const RESULT_LABELS = {
  untested: "Untested",
  passed: "Passed",
  failed: "Failed",
  blocked: "Blocked",
};
const resultSelect = (c) =>
  `<select class="result-select needs-editor ${esc(c.execution_status || "untested")}" aria-label="Latest execution result" onclick="event.stopPropagation()" onchange="setCaseResult('${c.id}',this.value,this)"><option value="untested" ${(c.execution_status || "untested") === "untested" ? "selected" : ""}>Untested</option><option value="passed" ${c.execution_status === "passed" ? "selected" : ""}>Passed</option><option value="failed" ${c.execution_status === "failed" ? "selected" : ""}>Failed</option><option value="blocked" ${c.execution_status === "blocked" ? "selected" : ""}>Blocked</option></select>`;
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
function expectedItemHtml(item) {
  if (item !== null && typeof item === "object") {
    return `<pre>${esc(JSON.stringify(item, null, 2))}</pre>`;
  }
  return esc(item);
}

function expectedValueHtml(value) {
  if (Array.isArray(value))
    return value.length
      ? `<ul>${value.map((item) => `<li>${expectedItemHtml(item)}</li>`).join("")}</ul>`
      : `<span class="muted">None</span>`;

  if (value && typeof value === "object")
    return `<ul>${Object.entries(value)
      .map(([key, item]) => {
        const rendered = Array.isArray(item)
          ? `<ul>${item.map((entry) => `<li>${expectedItemHtml(entry)}</li>`).join("")}</ul>`
          : expectedItemHtml(item);

        return `<li><b>${esc(key.replaceAll("_", " "))}:</b> ${rendered}</li>`;
      })
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
// The test case editor dialog (edit, new case, new case in a cycle) and case
// delete are React (features/test-cases/hooks/useCaseEditor.js, #257):
// window.editCase / openNewCase / openNewCaseInCycle / requestDeleteCase.
// The shared confirm / info dialogs are React (components/overlays/modals/
// CaseConfirmationModal.jsx, #257): window.openCaseConfirmation / openInfoDialog.
