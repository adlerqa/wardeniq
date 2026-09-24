// ---- features ----
function showFeatureList() {
  if ($("#feature-list-page")) $("#feature-list-page").hidden = false;
  if ($("#feature-create-page")) $("#feature-create-page").hidden = true;
  if ($("#detail-card")) $("#detail-card").hidden = true;
  currentFeature = null;
  renderBreadcrumbs();
  updateBackbar();
}
async function loadFeatureTicketOptions() {
  const pid = $("#f-project").value || currentProject || "";
  const select = $("#f-key");
  const status = $("#f-key-status");
  if (!select || !status) return;
  select.innerHTML = `<option value="">No Jira epic</option>`;
  status.textContent =
    "Associate an Epic so PRs auto-link to this feature (ticket → epic → feature). Each Epic maps to one feature only.";
  if (!pid) return;
  try {
    const r = await api(`/api/projects/${pid}`);
    const jiraProjectKey = (r.jira_project_key || "").trim();
    if (!jiraProjectKey) {
      status.textContent = "No Jira project is linked to this project.";
      return;
    }
    status.textContent = `Loading available Epics from ${jiraProjectKey}…`;
    const issues = await api(`/api/projects/${pid}/jira-issues`);
    const items = issues.issues || [];
    select.innerHTML =
      `<option value="">No Jira epic</option>` +
      items
        .map((item) => {
          return `<option value="${esc(item.key)}">${esc(item.key)} — ${esc(item.summary)}</option>`;
        })
        .join("");
    status.textContent = items.length
      ? `${items.length} unassociated Epic(s) available from ${jiraProjectKey}`
      : `No unassociated Epics found in ${jiraProjectKey}`;
  } catch (e) {
    status.innerHTML = `<span class="err">${esc(e.message)}</span>`;
  }
}
async function showFeatureCreate() {
  $("#feature-list-page").hidden = true;
  $("#feature-create-page").hidden = false;
  $("#detail-card").hidden = true;
  $("#f-name").value = "";
  $("#f-key").innerHTML = `<option value="">No Jira ticket</option>`;
  $("#f-file").value = "";
  $("#f-text").value = "";
  $("#f-filelist").textContent = "";
  $("#f-status").textContent = "";
  $("#f-log").textContent = "";
  $("#f-log").style.display = "none";
  if ($("#f-cost-estimate")) $("#f-cost-estimate").textContent = "";
  if ($("#f-match-key")) $("#f-match-key").value = "";
  await loadFeatureTicketOptions();
  updateBackbar();
}
if ($("#feature-new-btn"))
  $("#feature-new-btn").onclick = () => showFeatureCreate();
if ($("#feature-create-back"))
  $("#feature-create-back").onclick = showFeatureList;
$("#f-file").onchange = (e) => {
  const fs = [...e.target.files].map((f) => f.name);
  $("#f-filelist").textContent = fs.length
    ? `${fs.length} file(s): ${fs.join(", ")}`
    : "";
  scheduleCostEstimate();
};
if ($("#f-text")) $("#f-text").addEventListener("input", scheduleCostEstimate);

// ---- pre-run cost estimate (issue #22) ----
// Uses File.size as a rough stand-in for extracted character count (files aren't
// parsed until the real /api/features upload) — an order-of-magnitude estimate,
// not an exact one; the backend estimate itself is explicitly labelled as rough.
let costEstimateTimer = null;
function scheduleCostEstimate() {
  clearTimeout(costEstimateTimer);
  costEstimateTimer = setTimeout(updateCostEstimate, 400);
}
async function updateCostEstimate() {
  const el = $("#f-cost-estimate");
  if (!el) return;
  const fileEl = $("#f-file");
  const textEl = $("#f-text");
  const textLen = (textEl && textEl.value ? textEl.value.length : 0);
  const fileBytes = fileEl
    ? [...fileEl.files].reduce((sum, f) => sum + (f.size || 0), 0)
    : 0;
  const textLength = textLen + fileBytes;
  if (!textLength) {
    el.textContent = "";
    return;
  }
  el.textContent = "Estimating cost…";
  try {
    const r = await api("/api/usage/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text_length: textLength }),
    });
    el.textContent =
      r.low != null && r.high != null
        ? `Estimated cost: ${fmtUsd(r.low)}–${fmtUsd(r.high)} (${r.note})`
        : r.note || "";
  } catch (e) {
    el.textContent = "";
  }
}
const FOCUS_TYPES = ["functional", "ui", "e2e", "api", "nfr"];
function focusVals() {
  return FOCUS_TYPES.reduce((o, t) => {
    o[t] = parseInt($("#foc-" + t).value) || 0;
    return o;
  }, {});
}
let FOCUS_PREVIOUS = focusVals();
let FOCUS_PARTNER = null;
function largestFocusOther(changed, values, exclude = []) {
  return FOCUS_TYPES.filter((t) => t !== changed && !exclude.includes(t)).sort(
    (a, b) =>
      values[b] - values[a] || FOCUS_TYPES.indexOf(a) - FOCUS_TYPES.indexOf(b),
  )[0];
}
function paintFocus() {
  const values = focusVals();
  FOCUS_TYPES.forEach((t) => {
    $("#foc-" + t + "-v").textContent = values[t] + "%";
    $("#foc-" + t).style.setProperty("--fill", values[t] + "%");
  });
  $("#foc-total").textContent =
    FOCUS_TYPES.reduce((sum, t) => sum + values[t], 0) + "%";
}
function rebalanceFocus(changed) {
  const values = focusVals();
  const previous = FOCUS_PREVIOUS;
  const changedValue = Math.max(0, Math.min(100, values[changed]));
  let delta = changedValue - (previous[changed] || 0);
  values[changed] = changedValue;
  const exhausted = [];
  while (delta !== 0) {
    let partner = FOCUS_PARTNER;
    if (!partner || partner === changed || exhausted.includes(partner)) {
      partner = largestFocusOther(changed, values, exhausted);
      FOCUS_PARTNER = partner;
    }
    if (!partner) break;
    if (delta > 0) {
      const taken = Math.min(delta, values[partner]);
      values[partner] -= taken;
      delta -= taken;
      if (values[partner] === 0) exhausted.push(partner);
    } else {
      values[partner] += -delta;
      delta = 0;
    }
  }
  FOCUS_TYPES.forEach((t) => ($("#foc-" + t).value = values[t]));
  FOCUS_PREVIOUS = { ...values };
  paintFocus();
}
FOCUS_TYPES.forEach((t) => {
  const slider = $("#foc-" + t);
  const start = () => {
    FOCUS_PARTNER = largestFocusOther(t, FOCUS_PREVIOUS);
  };
  slider.addEventListener("pointerdown", start);
  slider.addEventListener("focus", () => {
    if (!FOCUS_PARTNER) start();
  });
  slider.addEventListener("input", () => rebalanceFocus(t));
  slider.addEventListener("change", () => {
    FOCUS_PARTNER = null;
    FOCUS_PREVIOUS = focusVals();
  });
  slider.addEventListener("blur", () => {
    FOCUS_PARTNER = null;
  });
});
paintFocus();
$("#f-go").onclick = async () => {
  const name = $("#f-name").value.trim();
  // --- validation with visible, non-scrolling feedback ---
  const fail = (msg, focusEl) => {
    $("#f-status").innerHTML = `<span class="err">${esc(msg)}</span>`;
    toast(msg, true);
    if (focusEl) focusEl.focus();
  };
  if (!name) {
    fail("Enter a feature name to continue.", $("#f-name"));
    return;
  }
  const pid = $("#f-project").value || currentProject || "";
  const splitLinks = (el) =>
    ((el && el.value) || "")
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  const conflList = splitLinks($("#f-confluence"));
  const figmaList = splitLinks($("#f-figma"));
  if (
    !$("#f-file").files.length &&
    !$("#f-text").value.trim() &&
    !conflList.length &&
    !figmaList.length
  ) {
    fail(
      "Add at least one source — upload a document, paste requirement text, or add a Confluence/Figma link.",
    );
    return;
  }
  const fd = new FormData();
  fd.append("name", name);
  fd.append("project_id", pid);
  fd.append("key", $("#f-key").value.trim());
  fd.append(
    "match_key",
    (($("#f-match-key") && $("#f-match-key").value) || "").trim(),
  );
  for (const f of $("#f-file").files) fd.append("files", f);
  fd.append("text", $("#f-text").value);
  fd.append("focus", JSON.stringify(focusVals()));
  conflList.forEach((u) => fd.append("confluence_url", u));
  figmaList.forEach((u) => fd.append("figma_url", u));
  $("#f-go").disabled = true;
  setBusy("#f-go", true);
  $("#f-status").innerHTML =
    `<span class="muted">Uploading sources and starting generation…</span>`;
  $("#f-log").style.display = "block";
  $("#f-log").textContent = "Starting generation…";
  try {
    const r = await api("/api/features", { method: "POST", body: fd });
    $("#f-status").innerHTML =
      `<span class="ok">✓ ${r.doc_count} document(s) accepted · ${r.chunks} chunk(s) prepared.</span> Live progress below.`;
    toast("Generation started");
    // Optional sheet import alongside ingest — fires its own job.
    const sheet =
      $("#f-sheet") && $("#f-sheet").files && $("#f-sheet").files[0];
    if (sheet && r.feature_id && pid) {
      try {
        const sfd = new FormData();
        sfd.append("file", sheet);
        const sr = await fetch(
          `/api/projects/${pid}/features/${r.feature_id}/tests/import`,
          { method: "POST", body: sfd },
        );
        const sj = await sr.json();
        if (sr.ok) toast(`Sheet queued for import (${sheet.name})`);
        else toast(`Sheet import failed: ${sj.detail || sr.status}`, true);
      } catch (e) {
        toast("Sheet import failed: " + e.message, true);
      }
    }
    watchGen(r.job_id, r.feature_id);
  } catch (e) {
    $("#f-status").innerHTML =
      `<span class="err">✕ Couldn't start generation: ${esc(e.message)}</span>`;
    toast("Generation failed: " + e.message, true);
    $("#f-go").disabled = false;
    setBusy("#f-go", false);
  }
};
if ($("#f-sheet-template"))
  $("#f-sheet-template").onclick = (e) => {
    e.preventDefault();
    // No feature yet — use a known feature template route, or fall back to /api/features/_/...
    // The template endpoint doesn't care about the feature id; any will do.
    const fid = currentFeature || "_";
    window.location.href = `/api/features/${fid}/tests/import/template?format=xlsx`;
  };
function fmtTok(n) {
  return Number(n || 0).toLocaleString();
}
function fmtUsd(c) {
  return c == null ? "—" : "$" + Number(c).toFixed(Number(c) < 1 ? 4 : 2);
}

function usageIcon(type) {
  const icons = {
    total: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="3"></circle>
        <path d="M19 12a7 7 0 0 0-7-7"></path>
        <path d="M5 12a7 7 0 0 0 7 7"></path>
        <path d="M12 2v3"></path>
        <path d="M12 19v3"></path>
        <path d="M2 12h3"></path>
        <path d="M19 12h3"></path>
      </svg>
    `,

    input: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3v12"></path>
        <path d="m7 10 5 5 5-5"></path>
        <path d="M5 21h14"></path>
      </svg>
    `,

    output: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 21V9"></path>
        <path d="m7 14 5-5 5 5"></path>
        <path d="M5 3h14"></path>
      </svg>
    `,

    cost: `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9"></circle>
        <path d="M12 6v12"></path>
        <path d="M16 8.5c-.8-1-2-1.5-4-1.5-2.2 0-3.5 1-3.5 2.5 0 3.5 7 1.5 7 5 0 1.5-1.3 2.5-3.5 2.5-1.8 0-3.3-.6-4-1.5"></path>
      </svg>
    `,
  };

  return icons[type] || "";
}

function usageStatCard(label, value, type, description) {
  return `
    <div class="usage-stat-card usage-stat-${type}">
      <div class="usage-stat-head">
        <span class="usage-stat-label">
          ${esc(label)}
        </span>

        <span class="usage-stat-icon">
          ${usageIcon(type)}
        </span>
      </div>

      <div class="usage-stat-value">
        ${esc(String(value))}
      </div>

      <div class="usage-stat-description">
        ${esc(description)}
      </div>
    </div>
  `;
}

function usageLogLines(u) {
  if (!u || !u.total_tokens) return [];
  const out = ["", "── LLM tokens ──"];
  Object.entries(u.by_model || {})
    .sort((a, b) => b[1].total_tokens - a[1].total_tokens)
    .forEach(([m, d]) => {
      out.push(
        `${m}${d.estimated ? " (~est)" : ""}: ${fmtTok(d.total_tokens)} tok  (${fmtTok(d.prompt_tokens)} in / ${fmtTok(d.completion_tokens)} out)  ${fmtUsd(d.cost_usd)}`,
      );
    });
  out.push(`TOTAL: ${fmtTok(u.total_tokens)} tok · ${fmtUsd(u.cost_usd)}`);
  return out;
}
function renderJobLog(target, j) {
  const el = $(target);
  if (!el) return;
  const logs = (j.logs || []).map(
    (x) =>
      `${x.progress == null ? "   " : String(x.progress).padStart(3) + "%"}  ${x.stage || ""}`,
  );
  if (j.error) logs.push(`ERR  ${j.error}`);
  logs.push(...usageLogLines(j.usage));
  el.style.display = logs.length ? "block" : "none";
  el.textContent = logs.join("\n");
  el.scrollTop = el.scrollHeight;
}
async function loadUsage() {
  const totals = $("#usage-totals");
  if (!totals) return;
  try {
    const r = await api("/api/usage"); // global view — the table breaks it down by project
    const t = r.totals || {};

    totals.innerHTML = [
      usageStatCard(
        "Total tokens",
        fmtTok(t.total_tokens),
        "total",
        "All AI token usage",
      ),

      usageStatCard(
        "Input tokens",
        fmtTok(t.prompt_tokens),
        "input",
        "Tokens sent to models",
      ),

      usageStatCard(
        "Output tokens",
        fmtTok(t.completion_tokens),
        "output",
        "Tokens generated by models",
      ),

      usageStatCard(
        "Estimated cost",
        fmtUsd(t.cost_usd),
        "cost",
        "Estimated provider spend",
      ),
    ].join("");

    const bm = Object.entries(r.by_model || {}).sort(
      (a, b) => b[1].total_tokens - a[1].total_tokens,
    );
    $("#usage-by-model").innerHTML = bm.length
      ? `<table><tr><th>Model</th><th>Type</th><th>Calls</th><th>Input</th><th>Output</th><th>Total</th><th>Est. cost</th></tr>` +
        bm
          .map(
            ([m, d]) =>
              `<tr><td><code>${esc(m)}</code>${d.estimated ? ' <span class="muted" title="tokens estimated">~est</span>' : ""}</td><td>${esc(d.kind || "")}</td><td>${fmtTok(d.calls)}</td><td>${fmtTok(d.prompt_tokens)}</td><td>${fmtTok(d.completion_tokens)}</td><td>${fmtTok(d.total_tokens)}</td><td>${fmtUsd(d.cost_usd)}</td></tr>`,
          )
          .join("") +
        `</table>`
      : '<span class="muted">No usage recorded yet — run a generation or analysis.</span>';
    // model dropdown: only the models actually used (dynamic), preserving selection
    fillUsageSelect(
      "#usage-model-filter",
      "All models",
      bm.map(([m]) => [m, m]),
    );

    const bp = r.by_project || [];
    $("#usage-by-project").innerHTML = bp.length
      ? `<table><tr><th>Project</th><th>Total tokens</th><th>Est. cost</th></tr>` +
        bp
          .map(
            (p) =>
              `<tr><td>${esc(p.name || p.project_id || "Unassigned")}</td><td>${fmtTok(p.total_tokens)}</td><td>${fmtUsd(p.cost_usd)}</td></tr>`,
          )
          .join("") +
        `</table>`
      : '<span class="muted">—</span>';
    // project dropdown: ALL projects (not just those with usage)
    let projOpts = bp.map((p) => [
      p.name || p.project_id || "Unassigned",
      p.name || p.project_id || "Unassigned",
    ]);
    try {
      const pr = await api("/api/projects");
      const all = (pr.projects || pr || []).map((p) => p.name).filter(Boolean);
      const seen = new Set(projOpts.map((o) => o[0]));
      all.forEach((n) => {
        if (!seen.has(n)) {
          seen.add(n);
          projOpts.push([n, n]);
        }
      });
    } catch (e) {}
    fillUsageSelect("#usage-project-filter", "All projects", projOpts);

    const rec = r.recent || [];
    $("#usage-recent").innerHTML = rec.length
      ? `<table><tr><th>Process</th><th>Project</th><th>Feature</th><th>Status</th><th>When</th><th>Models</th><th>Total tokens</th><th>Est. cost</th></tr>` +
        rec
          .map((j) => {
            const models =
              Object.keys(j.by_model || {})
                .map(esc)
                .join(", ") || "—";
            const when = j.created_at
              ? new Date(j.created_at * 1000).toLocaleString()
              : "";
            const st = esc(j.status || "");
            const stCls =
              j.status === "failed"
                ? "err"
                : j.status === "running"
                  ? "warn"
                  : "ok";
            return `<tr><td>${esc(j.label || j.type || "")}</td><td>${esc(j.project_name || j.project_id || "—")}</td><td>${esc(j.feature_name || "—")}</td><td><span class="${stCls}">${st}</span></td><td class="muted" style="white-space:nowrap">${esc(when)}</td><td><span class="muted" style="font-size:11px">${models}</span></td><td>${fmtTok(j.total_tokens)}</td><td>${fmtUsd(j.cost_usd)}</td></tr>`;
          })
          .join("") +
        `</table>`
      : '<span class="muted">No processes yet.</span>';
    // re-apply any active filters after re-render
    filterUsageTable("#usage-recent-search", "usage-recent");
    filterUsageTable("#usage-model-filter", "usage-by-model");
    filterUsageTable("#usage-project-filter", "usage-by-project");
    loadPricingEditor(); // refresh the editable price table (defaults + overrides)
  } catch (e) {
    totals.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

// ---- Model pricing editor (Usage page) -------------------------------------
// Lets users set input/output $/1M for ANY model id — including custom/new models
// the app doesn't ship a default for — so Usage & Cost stays accurate. Only prices
// that differ from the built-in default are persisted (as `llm_prices` overrides).
let _priceDefaults = {};
async function loadPricingEditor() {
  const box = $("#usage-pricing-rows");
  if (!box) return;
  try {
    const s = await api("/api/settings");
    _priceDefaults = s.llm_price_defaults || {};
    const overrides = s.llm_prices || {};
    const ids = Array.from(
      new Set([...Object.keys(_priceDefaults), ...Object.keys(overrides)]),
    ).sort();
    box.innerHTML =
      `<div style="display:flex;gap:8px;font-size:11px;margin-bottom:4px" class="muted">` +
      `<span style="flex:2;min-width:160px">Model</span><span style="flex:1;min-width:90px">Input $/1M</span><span style="flex:1;min-width:90px">Output $/1M</span></div>` +
      ids
        .map((m) => {
          const p = overrides[m] || _priceDefaults[m] || { in: 0, out: 0 };
          const custom = !!overrides[m];
          return (
            `<div class="price-row" data-model="${esc(m)}" style="display:flex;gap:8px;align-items:center;margin-bottom:6px">` +
            `<code style="flex:2;min-width:160px">${esc(m)}${custom ? ' <span class="muted" title="custom override">•</span>' : ""}</code>` +
            `<input class="price-in" type="number" step="0.01" min="0" value="${Number(p.in || 0)}" style="flex:1;min-width:90px"/>` +
            `<input class="price-out" type="number" step="0.01" min="0" value="${Number(p.out || 0)}" style="flex:1;min-width:90px"/>` +
            `</div>`
          );
        })
        .join("");
  } catch (e) {
    box.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}
if ($("#usage-price-add"))
  $("#usage-price-add").onclick = () => {
    const m = ($("#usage-price-new-model").value || "").trim();
    if (!m) {
      toast("Enter a model id", true);
      return;
    }
    const pin = parseFloat($("#usage-price-new-in").value) || 0;
    const pout = parseFloat($("#usage-price-new-out").value) || 0;
    const box = $("#usage-pricing-rows");
    if (!box) return;
    if (box.querySelector(`.price-row[data-model="${CSS.escape(m)}"]`)) {
      toast("Model already listed — edit its row", true);
      return;
    }
    const row = document.createElement("div");
    row.className = "price-row";
    row.setAttribute("data-model", m);
    row.style.cssText =
      "display:flex;gap:8px;align-items:center;margin-bottom:6px";
    row.innerHTML =
      `<code style="flex:2;min-width:160px">${esc(m)} <span class="muted" title="custom override">•</span></code>` +
      `<input class="price-in" type="number" step="0.01" min="0" value="${pin}" style="flex:1;min-width:90px"/>` +
      `<input class="price-out" type="number" step="0.01" min="0" value="${pout}" style="flex:1;min-width:90px"/>`;
    box.appendChild(row);
    $("#usage-price-new-model").value = "";
    $("#usage-price-new-in").value = "";
    $("#usage-price-new-out").value = "";
  };
if ($("#usage-price-save"))
  $("#usage-price-save").onclick = async () => {
    const status = $("#usage-price-status");
    const prices = {};
    document.querySelectorAll("#usage-pricing-rows .price-row").forEach((r) => {
      const m = r.getAttribute("data-model");
      const pin = parseFloat(r.querySelector(".price-in").value) || 0;
      const pout = parseFloat(r.querySelector(".price-out").value) || 0;
      const d = _priceDefaults[m];
      // Persist only real overrides: custom models, or values that differ from default.
      if (!d || Number(d.in) !== pin || Number(d.out) !== pout) {
        prices[m] = { in: pin, out: pout };
      }
    });
    try {
      if (status) {
        status.classList.remove("err", "ok");
        status.textContent = "Saving…";
      }
      await api("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ llm_prices: prices }),
      });
      if (status) {
        status.innerHTML = `<span class="ok">Saved ${Object.keys(prices).length} override(s) — costs recalculated.</span>`;
      }
      loadUsage(); // re-render totals/tables with the new prices
    } catch (e) {
      if (status) {
        status.innerHTML = `<span class="err">${esc(e.message)}</span>`;
      }
    }
  };
// Populate a <select> with [value,label] options, keeping the current selection if still present.
function fillUsageSelect(sel, allLabel, options) {
  const el = $(sel);
  if (!el) return;
  const cur = el.value;
  el.innerHTML =
    `<option value="">${esc(allLabel)}</option>` +
    options
      .map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`)
      .join("");
  if (cur && options.some((o) => o[0] === cur)) el.value = cur;
}
// Filter table rows by a select's value (or a text input's value); skips the header.
function filterUsageTable(ctrlSel, containerId) {
  const ctrl = $(ctrlSel);
  if (!ctrl) return;
  const q = (ctrl.value || "").trim().toLowerCase();
  document.querySelectorAll(`#${containerId} table tr`).forEach((tr) => {
    if (tr.querySelector("th")) return;
    tr.style.display =
      !q || tr.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}
if ($("#usage-recent-search"))
  $("#usage-recent-search").oninput = () =>
    filterUsageTable("#usage-recent-search", "usage-recent");
if ($("#usage-model-filter"))
  $("#usage-model-filter").onchange = () =>
    filterUsageTable("#usage-model-filter", "usage-by-model");
if ($("#usage-project-filter"))
  $("#usage-project-filter").onchange = () =>
    filterUsageTable("#usage-project-filter", "usage-by-project");
if ($("#usage-refresh")) $("#usage-refresh").onclick = loadUsage;
// Generic durable job watcher. SSE gives immediate stage/log updates; polling is
// retained as a fallback for proxies that buffer or block event streams.
function watchJob(jobId, onTick, intervalMs) {
  let stop = false,
    settled = false,
    es = null,
    pollTimer = null;
  // Client-side stall detector — if the server's updated_at never advances
  // while status stays "running", the worker thread is likely dead (backend
  // sweeper will confirm it shortly). Deliver a synthetic "failed" tick so the
  // loader in the caller is replaced instead of spinning forever.
  let lastUpdatedAt = null,
    lastAdvanceMs = Date.now();
  const STALL_MS = 120000; // 2 min without progress = give up; slightly longer than backend sweep default
  const finish = () => {
    settled = true;
    if (es) {
      es.close();
      es = null;
    }
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  };
  const deliver = (j) => {
    if (stop || settled) return;
    // Track heartbeat: any change in updated_at (or stage/progress) is progress.
    const beat = j && j.updated_at != null ? j.updated_at : null;
    if (beat !== null && beat !== lastUpdatedAt) {
      lastUpdatedAt = beat;
      lastAdvanceMs = Date.now();
    }
    if (j && j.status === "running" && Date.now() - lastAdvanceMs > STALL_MS) {
      const synth = Object.assign({}, j, {
        status: "failed",
        stage: "stalled",
        error: j.error || "Worker appears unresponsive — please retry.",
      });
      onTick(synth);
      finish();
      return;
    }
    onTick(j);
    if (j.status !== "running") finish();
  };
  // Safety poll ALWAYS runs alongside SSE (slow cadence). SSE gives instant updates,
  // but if the stream goes quiet on a long job (proxy buffering, busy event loop)
  // without firing onerror, the poll still catches the terminal state so the UI never
  // gets stuck "in progress" after the job has finished.
  const poll = async () => {
    if (stop || settled) return;
    try {
      deliver(await api("/api/jobs/" + jobId));
    } catch (e) {}
    if (!stop && !settled) pollTimer = setTimeout(poll, intervalMs || 3000);
  };
  try {
    es = new EventSource(`/api/jobs/${jobId}/stream`);
    es.addEventListener("update", (e) => deliver(JSON.parse(e.data)));
    es.addEventListener("done", (e) => deliver(JSON.parse(e.data)));
    es.onerror = () => {
      if (es) {
        es.close();
        es = null;
      }
    }; // SSE dropped — the safety poll carries on
  } catch (e) {}
  pollTimer = setTimeout(poll, intervalMs || 3000); // always-on safety net
  return () => {
    stop = true;
    finish();
  };
}
function watchGen(jobId, fid) {
  if (!jobId) {
    $("#f-go").disabled = false;
    setBusy("#f-go", false);
    return;
  }
  watchJob(jobId, (j) => {
    const res = j.result || {};
    renderJobLog("#f-log", j);
    const line = `${res.cases_new || 0} new + ${res.cases_reused || 0} reused cases · ${res.steps_new || 0} new + ${res.steps_reused || 0} reused steps`;
    $("#f-status").innerHTML =
      j.status === "running"
        ? `<span class="muted">${esc(j.stage)}</span> — ${line}`
        : j.status === "failed"
          ? `<span class="err">✕ Generation failed: ${esc(j.error || "unknown error")}</span>`
          : `<span class="ok">✓ Done</span> — ${line}${res.warnings && res.warnings.length ? `<br><span class="warn">${esc(res.warnings.join("; "))}</span>` : ""}${res.errors && res.errors.length ? `<br><span class="err">${esc(res.errors.join("; "))}</span>` : ""}`;
    if (j.status !== "running") {
      $("#f-go").disabled = false;
      setBusy("#f-go", false);
      loadFeatures();
      refreshStatus();
      if (j.status === "failed")
        toast("Generation failed: " + (j.error || "unknown error"), true);
      else
        toast(
          `Generation complete — ${res.cases_new || 0} new, ${res.cases_reused || 0} reused test cases.`,
        );
      if (fid) openFeature(fid);
    }
  });
}
// Shows a live loader inside the feature detail while a generation job runs, so the
// user isn't left staring at the old/carried cases wondering if anything happened.
const GEN_WATCHING = new Set();
function watchFeatureGen(jobId, fid) {
  const banner = $("#d-genbanner");
  if (!banner || !jobId) return;
  if (GEN_WATCHING.has(jobId)) return; // avoid stacking watchers for the same job
  GEN_WATCHING.add(jobId);
  // Render the branded analyze loader once (so its animation doesn't reset each poll),
  // then update just the caption line below it as progress streams in.
  banner.innerHTML = `${brandLoader("analyze", { compact: true, messages: ["Generating test cases…", "AI drafting scenarios…", "Normalizing & de-duping…", "Finalizing suite…"] })}<div class="gen-sub" id="d-gencap" style="text-align:center;margin:2px 0 6px">this can take a minute; results will refresh automatically.</div>`;
  watchJob(jobId, (j) => {
    const res = j.result || {};
    if (j.status === "running") {
      const cap = $("#d-gencap");
      if (cap)
        cap.textContent = `${esc(j.stage || "Generating test cases…")} · ${res.cases_new || 0} new · ${res.cases_reused || 0} reused so far`;
    } else if (j.status === "failed") {
      GEN_WATCHING.delete(jobId);
      banner.innerHTML = `<div class="gen-banner err"><span>Generation failed: ${esc(j.error || "unknown error")}</span></div>`;
    } else {
      GEN_WATCHING.delete(jobId);
      banner.innerHTML = "";
      loadFeatures();
      refreshStatus();
      if (fid) openFeature(fid); // refresh the detail so the new cases appear
    }
  });
}
// If a feature has a generation/ingest job still running (e.g. after a refresh or
// navigating away and back), attach the live loader so it never looks "stuck at 0".
async function attachRunningGenWatcher(fid) {
  try {
    const r = await api("/api/jobs?status=running&limit=50");
    const job = (r.jobs || []).find(
      (j) => j.feature_id === fid && ["generate", "ingest"].includes(j.type),
    );
    if (job) watchFeatureGen(job.id, fid);
  } catch (e) {}
}
async function loadFeatures() {
  if (!$("#feat-list")) return;
  skIn("#feat-list", skeleton.cards(6, "Loading features"));
  try {
    const r = await api(
      "/api/features" + (currentProject ? `?project_id=${currentProject}` : ""),
    );
    if ($("#feature-new-btn"))
      $("#feature-new-btn").style.display = r.features.length ? "" : "none";
    $("#feat-list").innerHTML =
      r.features
        .map(
          (
            f,
          ) => `<div class="entity-card" data-feature-card="${f.id}" onclick="openFeature('${f.id}')">
    <button class="entity-menu-btn" title="Feature options" onclick="event.stopPropagation();toggleFeatureMenu('${f.id}')"><svg viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px;display:block"><circle cx="12" cy="5" r="2"></circle><circle cx="12" cy="12" r="2"></circle><circle cx="12" cy="19" r="2"></circle></svg></button>
    <div class="entity-menu" onclick="event.stopPropagation()">
      <button onclick="renameFeatureFromCard('${f.id}')">Rename</button>
      <button onclick="importSheetForFeature('${f.id}','${f.project_id || ""}')">Import Sheet</button>
      <button class="danger-option" onclick="deleteFeatureFromCard('${f.id}')">Delete</button>
    </div>
    <div class="entity-name">${esc(f.name)}</div>
    <div class="entity-meta">Version ${f.version || 1} · ${f.case_count} test case${f.case_count === 1 ? "" : "s"}${f.key ? ` · ${esc(f.key)}` : ""}</div>
    <div class="entity-foot"><span>Open workspace</span><span class="entity-arrow">›</span></div>
  </div>`,
        )
        .join("") ||
      `<div class="empty-state"><div class="empty-state-icon">+</div><h3>No features yet</h3><p>Create your first feature to continue.</p><button class="go" onclick="showFeatureCreate()">Create feature</button></div>`;
  } catch (e) {
    $("#feat-list").innerHTML =
      `<div class="empty-state"><div class="empty-state-icon">!</div><h3>Couldn't load features</h3><p>${esc(e.message)}</p><button class="ghost" onclick="loadFeatures()">Retry</button></div>`;
  }
}
window.toggleFeatureMenu = (fid) => {
  document.querySelectorAll("[data-feature-card]").forEach((card) => {
    if (card.getAttribute("data-feature-card") !== fid)
      card.classList.remove("menu-open");
  });
  const card = document.querySelector(`[data-feature-card="${fid}"]`);
  if (card) card.classList.toggle("menu-open");
};
window.renameFeatureFromCard = async (fid) => {
  const card = document.querySelector(`[data-feature-card="${fid}"]`);
  const current =
    card?.querySelector(".entity-name")?.textContent?.trim() || "";
  const name = await uiPrompt("Rename feature", "Feature name", current);
  if (!name) return;
  await api("/api/features/" + fid, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  loadFeatures();
  toast("Feature renamed");
};
window.deleteFeatureFromCard = async (fid) => {
  currentFeature = fid;
  const f = await api("/api/features/" + fid);
  openCaseConfirmation({
    title: "Delete feature",
    copy: "This removes the feature, its document chunks, and its test-case links. Test cases still linked to another feature will not be deleted.",
    summary: `<b>${esc(f.name)}</b><div class="muted" style="margin-top:6px">Version ${f.version || 1} · ${(f.test_cases || []).length} test case${(f.test_cases || []).length === 1 ? "" : "s"}</div>`,
    confirmLabel: "Delete feature",
    danger: true,
    onConfirm: async () => {
      const r = await api("/api/features/" + fid, { method: "DELETE" });
      currentFeature = null;
      showFeatureList();
      loadFeatures();
      refreshStatus();
      toast(
        `Feature deleted · ${r.removed_orphan_cases} orphan test case(s) removed · ${r.preserved_shared_cases} shared test case(s) preserved`,
      );
    },
  });
};
function featureSummaryText(f) {
  const summary = String(f.summary || "")
    .replace(/\s+/g, " ")
    .trim();
  if (summary && !/^(###|Document:|PRD|HLD|LLD)\b/i.test(summary))
    return summary;
  const text = String(f.text || "")
    .replace(/\s+/g, " ")
    .trim();
  const stripped = text
    .replace(
      /###\s*(document|uploaded documents?|pasted requirement|requirements?)\s*:?.*?(?=\n|$)/gi,
      "",
    )
    .replace(/\b[A-Za-z0-9_-]+\.pdf\b/gi, "")
    .replace(/\b(PRD|HLD|LLD)\s*[—-]\s*[^.?!\n]{0,180}/gi, "")
    .replace(/\b(PRD|HLD|LLD)\b\s*:?/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  const sentence = (stripped.match(/[^.!?]{40,260}[.!?]/) || [])[0];
  if (sentence) return sentence.trim();
  if (stripped.length > 80) return stripped.slice(0, 240).trim() + "…";
  return `${f.name} is ready for review with generated test coverage across functional, API, end-to-end, and reliability scenarios.`;
}
window.showAndScrollToTestCases = () => {
  document
    .querySelectorAll("#d-cases details.case-group")
    .forEach((details) => {
      details.open = true;
    });
  const el = $("#d-cases");
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
};
function renderMatchKey(f) {
  const box = $("#d-match-key");
  if (!box) return;
  const cur = (f && f.match_key) || "";
  box.innerHTML =
    `<span title="PRs whose title/body contain [TAG] auto-map to this feature">PR match tag: </span>` +
    `<input id="d-match-key-input" class="needs-editor" style="width:130px" placeholder="e.g. HOLDS" value="${esc(cur)}"/> ` +
    `<button class="ghost needs-editor" type="button" onclick="saveFeatureMatchKey()">Save</button> ` +
    `<span id="d-match-key-status" class="muted"></span>`;
}
window.saveFeatureMatchKey = async () => {
  if (!currentFeature) return;
  const v = (
    ($("#d-match-key-input") && $("#d-match-key-input").value) ||
    ""
  ).trim();
  try {
    const r = await api(`/api/features/${currentFeature}/match-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_key: v }),
    });
    if (currentFeatureData) currentFeatureData.match_key = r.match_key;
    if ($("#d-match-key-status"))
      $("#d-match-key-status").textContent = r.match_key
        ? `saved · PRs tagged [${esc(r.match_key)}] map here`
        : "cleared";
    toast(
      "PR match tag " +
        (r.match_key ? "set to [" + r.match_key + "]" : "cleared"),
    );
  } catch (e) {
    if ($("#d-match-key-status"))
      $("#d-match-key-status").textContent = e.message || "failed";
    toast(e.message || "failed", true);
  }
};
window.openFeature = async (fid) => {
  try {
    const f = await api("/api/features/" + fid);
    currentFeature = fid;
    currentFeatureData = f;
    currentFeatureCases = f.test_cases || [];
    if ($("#d-genbanner")) $("#d-genbanner").innerHTML = "";
    $("#feature-list-page").hidden = true;
    $("#feature-create-page").hidden = true;
    $("#detail-card").hidden = false;
    $("#d-name").textContent = f.name;
    renderMatchKey(f);
    const featureMeta = `Version ${f.version || 1}${f.key ? ` · ${esc(f.key)}` : ""} · ${f.test_cases.length} test case${f.test_cases.length === 1 ? "" : "s"}`;
    $("#d-meta").innerHTML = "";
    $("#d-export").onclick = () => bulkExportSelected("pdf");
    if ($("#d-export-csv"))
      $("#d-export-csv").onclick = () => bulkExportSelected("csv");
    $("#d-jira").style.display = f.key ? "" : "none";
    $("#d-jira").onclick = () => syncJira(fid);
    // version switcher
    const vers = f.versions || [];
    $("#d-version").innerHTML = vers
      .map(
        (v) =>
          `<option value="${v.id}" ${v.id === fid ? "selected" : ""}>v${v.version} · ${v.case_count} cases</option>`,
      )
      .join("");
    $("#d-version-chip").textContent =
      `Version ${f.version || 1} · ${f.test_cases.length} cases`;
    $("#d-version").onchange = (e) => openFeature(e.target.value);
    // version diff summary
    const vd = f.version_diff || {};
    if (vd.mode === "version" || (vd.retired && vd.retired.length)) {
      const ret = vd.retired || [];
      $("#d-verinfo").innerHTML =
        `<div class="explain" style="background:rgba(19,112,171,.08);border:1px solid rgba(19,112,171,.25);border-radius:8px;padding:10px 12px;margin:10px 0;font-size:12.5px">
      <b>Version ${vd.version} diff:</b> ${vd.kept || 0} cases carried over${ret.length ? `, ${ret.length} retired` : ""}, new cases added by generation.
      ${ret.length ? `<details style="margin-top:6px"><summary class="muted">retired cases</summary>${ret.map((r) => `<div class="muted" style="margin-top:4px">• ${esc(r.title || r.id)} — ${esc(r.reason || "")}</div>`).join("")}</details>` : ""}</div>`;
    } else if (vd.mode === "replace") {
      $("#d-verinfo").innerHTML =
        `<div class="muted" style="margin:8px 0">This version was regenerated; ${vd.retired_orphans || 0} obsolete cases removed.</div>`;
    } else {
      $("#d-verinfo").innerHTML = "";
    }
    const bt = {};
    f.test_cases.forEach((c) => {
      const _k = c.category || c.type;
      (bt[_k] = bt[_k] || []).push(c);
    });
    const groups = [
      [
        "api",
        "API",
        "Endpoint happy paths, validation, authorization, and failure handling",
      ],
      [
        "ui",
        "UI validations",
        "Visible fields, controls, and client-side validation",
      ],
      [
        "functional",
        "Business / functional",
        "Business rules and requirement behavior",
      ],
      [
        "e2e",
        "End-to-end",
        "Complete user journeys across UI, API, and persisted state",
      ],
      [
        "nfr",
        "Edge & reliability",
        "Concurrency, resilience, limits, latency, and degraded dependencies",
      ],
      [
        "integration",
        "Integration",
        "Cross-feature scenarios: cases inherited / linked from other features",
      ],
    ];
    // "UI validations" now has its own slider at feature creation (alongside
    // Functional / End-to-end / API / Edge & reliability — see FOCUS_TYPES),
    // so the distribution summary shows it as its own category again. Integration
    // is untouched: it's inherited/linked from other features, not generated by
    // this slider set, so it has no corresponding configuration option.
    const summaryGroups = [
      ["api", "API"],
      ["ui", "UI validations"],
      ["functional", "Business / functional"],
      ["e2e", "End-to-end"],
      ["nfr", "Edge & reliability"],
      ["integration", "Integration"],
    ];
    const overviewStats = summaryGroups
      .map(([t, label]) => {
        const cases = bt[t] || [];
        return `<div class="feature-stat"><b>${cases.length}</b><span>${label}</span></div>`;
      })
      .join("");
    const summaryText = featureSummaryText(f);
    $("#d-overview").innerHTML = `<div class="feature-hero">
    <div class="muted">${esc(featureMeta)}</div>
    <div class="feature-summary">${esc(summaryText)}</div>
    <div class="feature-stats">${overviewStats}</div>

    <div class="feature-action-grid">

  <button
    type="button"
    class="feature-action feature-action-cases"
    onclick="showAndScrollToTestCases()"
  >
   

    <div class="feature-action-content">
      <b>Test cases</b>
      <span>
        Review, filter, execute, and edit ${f.test_cases.length} cases.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>${f.test_cases.length} cases</span>
      <span>Open library</span>
    </div>
  </button>


  <button
    type="button"
    class="feature-action feature-action-validator"
    onclick="navigateTo('validator')"
  >
  

    <div class="feature-action-content">
      <b>Validator</b>
      <span>
        Check requirement clarity and identify missing decisions.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>Requirements</span>
      <span>Review</span>
    </div>
  </button>


  <button
    type="button"
    class="feature-action feature-action-plan"
    onclick="navigateTo('testplan')"
  >
   

    <div class="feature-action-content">
      <b>Test plan</b>
      <span>
        Build the QA strategy and generate an exportable test plan.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>QA strategy</span>
      <span>Generate</span>
    </div>
  </button>


  <button
    type="button"
    class="feature-action feature-action-gap"
    onclick="navigateTo('gap')"
  >
  

    <div class="feature-action-content">
      <b>Gap Analysis</b>
      <span>
        Inspect code and automation coverage with exact commit links.
      </span>
    </div>

    <div class="feature-action-meta">
      <span>Coverage</span>
      <span>Analyze</span>
    </div>
  </button>

</div>



  </div>`;
    const h = groups
      .map(([t, label, help], index) => {
        const cases = bt[t] || [];
        return `<details class="case-group">
      <summary title="${esc(help)}"><span>${label} (${cases.length})</span></summary>
      <div class="case-group-body">${cases.length ? caseListHeader("feature") + cases.map(caseCard).join("") : `<div class="case-group-empty">No ${label.toLowerCase()} were generated from the current evidence.</div>`}</div>
    </details>`;
      })
      .join("");
    $("#d-cases").innerHTML = h;
    updateCaseSelection();
    loadCoverage(fid);
    window.scrollTo({ top: 0, behavior: "smooth" });
    renderBreadcrumbs();
    updateBackbar();
    attachRunningGenWatcher(fid); // show the live loader if generation is still running
  } catch (e) {
    $("#d-cases").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
};
async function openFeatureTestCases(fid, pid) {
  navigateTo("cases");
  await initCases();
  $("#tc-proj").value = pid || currentProject || "";
  await fillFeatFilter();
  $("#tc-feat").value = fid;
  $("#tc-type").value = "";
  $("#tc-tag").value = "";
  $("#tc-status").value = "active";
  $("#tc-result").value = "";
  $("#tc-lineage").value = "";
  $("#tc-q").value = "";
  tcPage = 0;
  loadCases();
}
function activeCaseRoot() {
  if (!$("#view-features").hidden && !$("#detail-card").hidden)
    return $("#detail-card");
  if (!$("#view-cases").hidden) return $("#view-cases");
  return document;
}
function activeCaseCheckboxes() {
  return [...activeCaseRoot().querySelectorAll(".case-select[data-case-id]")];
}
function selectedCaseIds() {
  return activeCaseCheckboxes()
    .filter((x) => x.checked)
    .map((x) => x.dataset.caseId);
}
function setVisibleCaseSelection(checked) {
  activeCaseCheckboxes().forEach((x) => (x.checked = checked));
  updateCaseSelection();
}
function updateCaseSelection() {
  const root = activeCaseRoot();
  const boxes = activeCaseCheckboxes();
  const selected = boxes.filter((x) => x.checked);
  document
    .querySelectorAll(".case-bulk-toolbar")
    .forEach((bar) => bar.classList.remove("show"));
  const scope = root.id === "detail-card" ? "feature" : "cases";
  document.querySelectorAll(`[data-bulk-scope="${scope}"]`).forEach((bar) => {
    if (selected.length) bar.classList.add("show");
  });
  document
    .querySelectorAll(`[data-bulk-count="${scope}"]`)
    .forEach((x) => (x.textContent = `${selected.length} selected`));
  document
    .querySelectorAll(`[data-bulk-count="${scope}-floating"]`)
    .forEach((x) => (x.textContent = selected.length));
  root.querySelectorAll(".case-select-all").forEach((x) => {
    x.checked = boxes.length > 0 && selected.length === boxes.length;
    x.indeterminate = selected.length > 0 && selected.length < boxes.length;
  });
  document
    .querySelectorAll(`[data-bulk-scope="${scope}-floating"]`)
    .forEach((bar) => bar.classList.toggle("show", selected.length > 0));
}
document.addEventListener("change", (e) => {
  if (e.target.matches(".case-select-all"))
    setVisibleCaseSelection(e.target.checked);
  if (e.target.matches(".case-select[data-case-id]")) updateCaseSelection();
});
function selectedExportIds() {
  const rowIds = selectedCaseIds();
  if (rowIds.length) return rowIds;
  return [...document.querySelectorAll(".export-case-check")]
    .filter((x) => x.checked)
    .map((x) => x.value);
}
function refreshExportCount() {
  const n = selectedExportIds().length;
  $("#export-count").textContent = `${n} selected`;
  $("#export-pdf").disabled = !n;
  $("#export-csv").disabled = !n;
}
function openExportModal() {
  if (!currentFeature || !currentFeatureData) return;
  const cases = currentFeatureCases || [];
  $("#export-sub").textContent =
    `${currentFeatureData.name} · Version ${currentFeatureData.version || 1} · ${cases.length} test case${cases.length === 1 ? "" : "s"}`;
  $("#export-select-all").checked = true;
  $("#export-list").innerHTML =
    cases
      .map(
        (c) => `<label class="export-row">
    <input class="export-case-check" type="checkbox" value="${esc(c.id)}" checked/>
    <span class="badge">${esc(c.display_id || "")}</span>
    <span><span class="title">${esc(caseTitle(c))}</span><div class="meta">${esc(typeLabel(c.type))} · ${c.steps?.length || 0} step${(c.steps?.length || 0) === 1 ? "" : "s"}</div></span>
    <span class="meta">${prioBadge(c.priority)}</span>
  </label>`,
      )
      .join("") ||
    `<div class="muted" style="padding:14px">No test cases available.</div>`;
  document.querySelectorAll(".export-case-check").forEach(
    (x) =>
      (x.onchange = () => {
        const all = [...document.querySelectorAll(".export-case-check")];
        $("#export-select-all").checked =
          all.length && all.every((c) => c.checked);
        refreshExportCount();
      }),
  );
  refreshExportCount();
  $("#export-modal").classList.add("show");
}
async function downloadFeatureExport(format, explicitIds = null) {
  const ids = explicitIds === null ? selectedExportIds() : explicitIds;
  const featureId = !$("#view-cases").hidden
    ? $("#tc-feat")?.value
    : currentFeature;
  if (!featureId) {
    toast("Choose one feature before exporting selected test cases", true);
    return;
  }
  const ext = format === "pdf" ? "pdf" : "csv";
  const mime = format === "pdf" ? "application/pdf" : "text/csv";
  const request = ids.length
    ? {
        url: `/api/features/${featureId}/export/${format}-selected`,
        init: {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ testCaseIds: ids }),
        },
      }
    : {
        url: `/api/features/${featureId}/export/${format}`,
        init: { method: "GET" },
      };
  const res = await fetch(request.url, request.init);
  if (!res.ok) {
    let detail = "Export failed";
    try {
      detail = (await res.json()).detail || detail;
    } catch (e) {}
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(new Blob([blob], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(currentFeatureData?.name || "feature").replace(/[^a-z0-9]+/gi, "_").toLowerCase()}_test_cases.${ext}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
async function downloadGapExport(kind, fmt) {
  if (!currentFeature) {
    toast("Open a feature first", true);
    return;
  }
  const mime = fmt === "pdf" ? "application/pdf" : "text/csv";
  const res = await fetch(
    `/api/features/${currentFeature}/gap/${kind}/export/${fmt}`,
    { method: "GET" },
  );
  if (!res.ok) {
    let detail = "Export failed";
    try {
      detail = (await res.json()).detail || detail;
    } catch (e) {}
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(new Blob([blob], { type: mime }));
  const a = document.createElement("a");
  const base = (currentFeatureData?.name || "feature")
    .replace(/[^a-z0-9]+/gi, "_")
    .toLowerCase();
  const label = kind === "pr-coverage" ? "pr_coverage" : "automation_coverage";
  a.href = url;
  a.download = `${base}_${label}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
async function bulkExportSelected(format = "pdf") {
  const ids = selectedCaseIds();
  try {
    await downloadFeatureExport(format, ids);
    toast(
      ids.length
        ? "Selected test cases exported"
        : "All feature test cases exported",
    );
  } catch (e) {
    toast(e.message, true);
  }
}
async function bulkSetCaseResult(status) {
  const ids = selectedCaseIds();
  if (!ids.length) {
    toast("Select test cases first", true);
    return;
  }
  try {
    await Promise.all(
      ids.map((id) =>
        api(`/api/test-cases/${id}/execution`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        }),
      ),
    );
    ids.forEach((id) => {
      const item = document.querySelector(`[data-case-item="${id}"]`);
      const select = item?.querySelector(".result-select");
      if (select) {
        select.value = status;
        select.className = `result-select needs-editor ${status}`;
        [...select.options].forEach(
          (o) => (o.defaultSelected = o.value === status),
        );
      }
    });
    toast(
      `${ids.length} test case${ids.length === 1 ? "" : "s"} marked ${RESULT_LABELS[status].toLowerCase()}`,
    );
  } catch (e) {
    toast(e.message, true);
  }
}
async function bulkDeleteSelected() {
  const ids = selectedCaseIds();
  if (!ids.length) {
    toast("Select test cases first", true);
    return;
  }
  if (
    !(await uiConfirm(
      `Delete ${ids.length} selected test case${ids.length === 1 ? "" : "s"}? Shared test cases are only removed from the current feature when a feature is in context.`,
      "Delete Test Cases",
      "Delete",
      true,
    ))
  )
    return;
  const scopedFeature = !$("#view-cases").hidden
    ? $("#tc-feat")?.value || ""
    : currentFeature;
  try {
    for (const id of ids) {
      if (scopedFeature)
        await api(`/api/features/${scopedFeature}/test-cases/${id}`, {
          method: "DELETE",
        });
      else await api(`/api/test-cases/${id}`, { method: "DELETE" });
    }
    toast(
      `${ids.length} selected test case${ids.length === 1 ? "" : "s"} removed`,
    );
    if (!$("#view-cases").hidden) loadCases();
    if (currentFeature) openFeature(currentFeature);
  } catch (e) {
    toast(e.message, true);
  }
}
if ($("#export-close"))
  $("#export-close").onclick = () =>
    $("#export-modal").classList.remove("show");
if ($("#export-select-all"))
  $("#export-select-all").onchange = (e) => {
    document
      .querySelectorAll(".export-case-check")
      .forEach((x) => (x.checked = e.target.checked));
    refreshExportCount();
  };
if ($("#export-pdf"))
  $("#export-pdf").onclick = async () => {
    try {
      await downloadFeatureExport("pdf");
    } catch (e) {
      toast(e.message, true);
    }
  };
if ($("#export-csv"))
  $("#export-csv").onclick = async () => {
    try {
      await downloadFeatureExport("csv");
    } catch (e) {
      toast(e.message, true);
    }
  };
document.querySelectorAll(".feature-workspace-back").forEach((button) => {
  button.onclick = () => navigateTo("features");
});
document.querySelectorAll(".feature-workspace-cases").forEach((button) => {
  button.onclick = () => {
    if (currentFeature) openFeatureTestCases(currentFeature, currentProject);
  };
});
const TYPE_LABELS = {
  functional: "Business / functional",
  e2e: "End-to-end",
  api: "API",
  ui: "UI validation",
  nfr: "Edge & reliability",
  integration: "Integration",
};
const typeLabel = (t) => TYPE_LABELS[t] || t;
const caseTitle = (c) =>
  cleanRequirementText(c?.title || "Untitled test case") ||
  "Untitled test case";
function caseListHeader(scope) {
  return `<div class="case-list-head">
    <input type="checkbox" class="case-select case-select-all" data-bulk-scope="${scope}" title="Select all visible test cases" aria-label="Select all visible test cases" onclick="event.stopPropagation()"/>
    <span></span>
    <span>Test case</span>
    <span>Result</span>
    <span>Priority</span>
    <span>Action</span>
  </div>`;
}
function caseCard(c) {
  const orig = c.association && c.association.origin;
  const context = orig ? `${orig.replaceAll("_", " ")} · ` : "";
  const inherited = [
    "reused",
    "carried",
    "carried_repaired",
    "inherited",
    "adapted",
  ].includes(orig);
  const title = caseTitle(c);
  // "Imported from sheet" takes priority over the generic inherited badge, so a case
  // that came from an uploaded sheet is never mislabelled as inherited from a feature.
  // Fall back to the origin when the backend `imported` flag isn't present yet.
  const isImported = c.imported || orig === "imported";
  const originBadge = isImported
    ? `<span class="badge reused" style="margin-left:7px" title="Came from an uploaded sheet">Imported from sheet</span>`
    : inherited
      ? `<span class="badge reused" style="margin-left:7px">Inherited / reused</span>`
      : "";
  return `<div class="testcase-item" data-case-item="${c.id}">
    <div class="testcase-row" onclick="viewCase('${c.id}',this)">
      <input class="case-select" data-case-id="${esc(c.id)}" type="checkbox" aria-label="Select ${esc(title)}" onclick="event.stopPropagation()"/>
      <span class="testcase-chevron">›</span>
      <div><div class="testcase-title">${c.display_id ? `<span class="badge" style="margin-right:7px">${esc(c.display_id)}</span>` : ""}${esc(title)}${originBadge}</div><div class="testcase-sub">${esc(context + typeLabel(c.type))} · ${c.steps.length} step${c.steps.length === 1 ? "" : "s"}</div></div>
      ${resultSelect(c)}
      <span class="testcase-priority">${prioBadge(c.priority)}</span>
      <button class="testcase-delete needs-editor" title="Delete testcase" onclick="event.stopPropagation();requestDeleteCase('${c.id}')"><span>Delete</span></button>
    </div>
    <div class="testcase-detail" data-case-detail="${c.id}"></div>
  </div>`;
}
async function loadCoverage(fid) {
  $("#d-coverage").innerHTML = "";
  try {
    const r = await api(`/api/features/${fid}/coverage`);
    const s = r.summary;
    if (!s) return;
    const thr = s.ready_threshold != null ? s.ready_threshold : 80;
    const banner = s.ready
      ? `<div style="margin-top:10px;color:#34d399;font-weight:600;font-size:13px">✓ Minimum code-coverage target reached (${s.code_pct}% ≥ ${thr}%) — ready for manual QA.</div>`
      : `<div style="margin-top:10px;color:#f6a623;font-size:12.5px">Not ready for manual QA — code coverage ${s.code_pct}% is below the ${thr}% target for this feature.</div>`;
    const strategy = `<div style="margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px;color:var(--muted,#94a3b8)">
      <span>QA-readiness target:</span>
      <input id="fc-threshold" class="needs-editor" type="number" min="0" max="100" value="${thr}" style="width:64px" />
      <span>% code coverage</span>
      <button class="ghost needs-editor" type="button" onclick="saveReadyThreshold('${fid}')">Save</button>
      <span id="fc-threshold-status" class="muted"></span>
    </div>`;
    $("#d-coverage").innerHTML =
      `<div style="margin-top:14px;border:1px solid var(--line,#1e293b);border-radius:12px;padding:14px 16px;background:var(--panel,#0d1728)">
      <div style="font-size:13px;font-weight:600">Coverage <span style="font-weight:400;color:var(--muted,#94a3b8)">— aggregated across all PRs linked to this feature</span></div>
      <div style="font-size:12px;color:var(--muted,#94a3b8);margin:2px 0 10px">A test case counts as covered once ANY linked PR implements it (no single repo need cover everything).</div>
      <div class="dash-gauge"><div class="top"><span>Code coverage (cases hit by PRs)</span><b>${s.code_pct}%</b></div><div class="track"><div class="fill code" style="width:${s.code_pct}%"></div></div></div>
      <div class="dash-gauge"><div class="top"><span>Automation Test Coverage (dev-written tests)</span><b>${s.automation_pct}%</b></div><div class="track"><div class="fill auto" style="width:${s.automation_pct}%"></div></div></div>
      <div class="dash-cov-note">${s.covered_cases} covered · ${s.automated_cases} automated of ${s.total_cases} cases</div>
      ${banner}
      ${strategy}
    </div>`;
  } catch (e) {
    /* non-fatal: coverage card just stays empty */
  }
}
window.saveReadyThreshold = async (fid) => {
  const el = $("#fc-threshold");
  const v = parseInt((el && el.value) || "80", 10);
  try {
    const r = await api(`/api/features/${fid}/ready-threshold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold: isNaN(v) ? 80 : v }),
    });
    toast(`QA-readiness target set to ${r.ready_threshold}% code coverage`);
    loadCoverage(fid);
  } catch (e) {
    if ($("#fc-threshold-status"))
      $("#fc-threshold-status").textContent = e.message || "failed";
    toast(e.message || "Could not save target", true);
  }
};
$("#d-close").onclick = showFeatureList;
