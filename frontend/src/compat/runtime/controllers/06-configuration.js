// ---- configuration ----
async function loadConfig() {
  try {
    const s = await api("/api/settings");
    const llmProv = s.llm_provider || "ollama";
    $("#cfg-llm-provider").value = llmProv;
    if ($("#cfg-llm-region")) $("#cfg-llm-region").value = s.llm_region || "";
    updateModelOptions(llmProv, s.llm_model || "");
    $("#cfg-llm-status").innerHTML = s.llm_api_key_set
      ? `<span class="ok">API key / secret configured</span>`
      : `<span class="muted">no API key set</span>`;
    // Unified Endpoint URL field: shows the Ollama URL for Ollama (with the env-lock /
    // effective-URL hint), else the provider base/endpoint URL.
    if ($("#cfg-llm-endpoint")) {
      const inp = $("#cfg-llm-endpoint"),
        hint = $("#cfg-ollama-hint");
      if (llmProv === "ollama") {
        if (s.ollama_url_env_locked) {
          inp.value = s.ollama_url_effective || "";
          inp.disabled = true;
          hint.innerHTML = `Pinned by <code>OLLAMA_URL</code> in <code>.env</code> (takes priority). Edit <code>.env</code> to change it.`;
        } else {
          inp.disabled = false;
          inp.value = s.ollama_url || "";
          hint.innerHTML = `In use: <code>${esc(s.ollama_url_effective || "")}</code>${s.ollama_url ? "" : " (bundled default)"}. Applies immediately on save — no restart.`;
        }
      } else {
        inp.disabled = false;
        inp.value = s.llm_base_url || "";
        hint.innerHTML = "";
      }
    }
    applyLlmProviderUI(llmProv);
    // Deploy-time provider lock (e.g. an air-gapped Bedrock-only client): pin the LLM
    // dropdown only. Embeddings stay the admin's choice (handled in the embed section).
    if (s.provider_lock) {
      const lp = $("#cfg-llm-provider");
      if (lp && [...lp.options].some((o) => o.value === s.provider_lock)) {
        lp.value = s.provider_lock;
        lp.disabled = true;
        applyLlmProviderUI(s.provider_lock);
      }
    }
    if ($("#cfg-jira-base")) {
      $("#cfg-jira-base").value = s.jira_base_url || "";
      $("#cfg-jira-email").value = s.jira_email || "";
      // jira_token_set only means "something is stored" -- it can be a token
      // that no longer decrypts (e.g. after an app-secret change). Only
      // jira_token_readable means it's actually usable as-is.
      $("#cfg-jira-status").innerHTML = s.jira_token_readable
        ? `<span class="ok">Jira token configured</span>`
        : s.jira_token_set
          ? `<span class="warn">saved token can't be read — re-enter it below</span>`
          : `<span class="muted">no Jira token set</span>`;
    }
    if ($("#cfg-figma-status")) {
      $("#cfg-figma-status").innerHTML = s.figma_token_set
        ? `<span class="ok">Figma token configured</span>`
        : `<span class="muted">no Figma token set</span>`;
    }
    if ($("#cfg-poll-interval")) {
      const eff = s.poll_interval_s_effective || 1800;
      $("#cfg-poll-interval").value =
        s.poll_interval_s !== "" && s.poll_interval_s != null
          ? s.poll_interval_s
          : eff;
      $("#cfg-poll-interval").min = s.poll_interval_min_s || 30;
      if ($("#cfg-poll-status")) {
        const envNote = s.poll_interval_env_writable
          ? " Saved values are also written to <code>.env</code>."
          : " Applies at runtime only — <code>.env</code> isn't writable in this deployment.";
        $("#cfg-poll-status").innerHTML =
          `In use: <code>${eff}s</code> (≈ ${(eff / 60).toFixed(eff % 60 ? 1 : 0)} min).${envNote}`;
      }
    }
    if ($("#cfg-smtp-host")) {
      $("#cfg-smtp-host").value = s.smtp_host || "";
      $("#cfg-smtp-port").value = s.smtp_port || "";
      $("#cfg-smtp-user").value = s.smtp_user || "";
      $("#cfg-smtp-from").value = s.smtp_from || "";
      $("#cfg-smtp-tls").checked = s.smtp_tls !== false;
      $("#cfg-smtp-ssl").checked = !!s.smtp_ssl;
      $("#cfg-smtp-status").innerHTML = s.smtp_configured
        ? `<span class="ok">SMTP configured${s.smtp_pass_set ? " (password saved)" : ""}</span>`
        : `<span class="warn">not configured — email sign-in unavailable</span>`;
    }
    // Embedding model
    if ($("#cfg-embed-provider")) {
      EMBED_OPTS = s.embed_model_options || {};
      const embSel = $("#cfg-embed-provider");
      embSel.value = s.embed_provider || "ollama";
      // In a locked (air-gapped) install the admin may still pick their embedder, but
      // only the offline-safe ones: the local bundled Ollama or the locked provider
      // (e.g. Bedrock). Internet embedders (OpenAI / Gemini / Voyage) are hidden.
      if (s.provider_lock) {
        const allowed = new Set(["ollama", s.provider_lock]);
        [...embSel.options].forEach((o) => {
          o.hidden = !allowed.has(o.value);
        });
        if (!allowed.has(embSel.value)) embSel.value = "ollama";
      } else {
        [...embSel.options].forEach((o) => {
          o.hidden = false;
        });
      }
      const embProv = embSel.value;
      $("#cfg-embed-base").value = s.embed_base_url || "";
      if ($("#cfg-embed-region"))
        $("#cfg-embed-region").value = s.embed_region || "";
      updateEmbedModelOptions(embProv, s.embed_model || "");
      $("#cfg-embed-status").innerHTML =
        `<span class="muted">Active: ${esc(embProv)} / ${esc(s.embed_model || "nomic-embed-text")} · ${s.embed_dim || 768}-d${s.embed_api_key_set ? " · key set" : ""}</span>`;
    }

    // Update placeholders based on configuration status
    if ($("#cfg-llm-key")) {
      $("#cfg-llm-key").placeholder = s.llm_api_key_set
        ? "Leave blank to keep current"
        : "API token is required";
    }
    if ($("#cfg-llm-endpoint")) {
      const hasLlmEndpointConfig =
        s.ollama_url_env_locked ||
        s.llm_base_url ||
        s.ollama_url ||
        s.configured;
      $("#cfg-llm-endpoint").placeholder = hasLlmEndpointConfig
        ? "Leave blank to keep current"
        : "Endpoint URL is required";
    }
    if ($("#cfg-embed-key")) {
      $("#cfg-embed-key").placeholder = s.embed_api_key_set
        ? "Leave blank to keep current"
        : "API token is required";
    }
    if ($("#cfg-embed-base")) {
      const hasEmbedEndpointConfig = s.embed_base_url || s.configured;
      $("#cfg-embed-base").placeholder = hasEmbedEndpointConfig
        ? "Leave blank to keep current"
        : "Endpoint URL is required";
    }
    if ($("#cfg-jira-token")) {
      // Gate on jira_token_readable, not jira_token_set: a stored-but-
      // undecryptable token must NOT claim "leave blank to keep current" --
      // there is no readable current value to keep, and saving with it blank
      // would just re-trip Jira validation with a confusing error.
      $("#cfg-jira-token").placeholder = s.jira_token_readable
        ? "Leave blank to keep current"
        : s.jira_token_set
          ? "Saved token can't be read — re-enter it"
          : "API token is required";
    }
    if ($("#cfg-figma-token")) {
      $("#cfg-figma-token").placeholder = s.figma_token_set
        ? "Leave blank to keep current"
        : "API token is required";
    }
    if ($("#cfg-smtp-pass")) {
      $("#cfg-smtp-pass").placeholder = s.smtp_pass_set
        ? "Leave blank to keep current"
        : "API token is required";
    }
    if ($("#cfg-s3-bucket")) {
      $("#cfg-s3-bucket").value = s.s3_bucket || "";
      if ($("#cfg-s3-region")) $("#cfg-s3-region").value = s.s3_region || "";
      if ($("#cfg-s3-key")) $("#cfg-s3-key").value = s.s3_access_key_id || "";
      if ($("#cfg-s3-prefix"))
        $("#cfg-s3-prefix").value = s.s3_prefix || "documents";
      if ($("#cfg-s3-enabled"))
        $("#cfg-s3-enabled").checked = s.s3_enabled !== false && !!s.s3_bucket;
      if ($("#cfg-s3-status")) {
        $("#cfg-s3-status").innerHTML = s.s3_configured
          ? `<span class="ok">S3 configured for bucket '${esc(s.s3_bucket)}'${s.s3_secret_access_key_set ? " (secret key saved)" : ""}</span>`
          : `<span class="muted">not configured — document storage using default local mode</span>`;
      }
    }
    if ($("#cfg-s3-secret")) {
      $("#cfg-s3-secret").placeholder = s.s3_secret_access_key_set
        ? "Leave blank to keep current"
        : "Secret Access Key (optional)";
    }

    loadDbStatus();
  } catch (e) {}
}

// ---- read-only Database status panel ----
async function loadDbStatus() {
  const box = $("#cfg-db-body");
  if (!box) return;
  box.innerHTML = skeleton.block("Loading database status");
  try {
    const d = await api("/api/db-status");
    const boot = d.boot || {};
    const err = boot.stage === "error";
    const bootMsg = formatBootStatus(boot);
    // Show only the connection status; the URL input below is always available.
    const rows = [];
    rows.push(
      dbRow(
        "Connection",
        err
          ? `<span class="err">⚠ ${esc(bootMsg.summary || "not ready")}</span>${bootBannerDetailsHtml(bootMsg.raw)}`
          : boot.ready
            ? `<span class="ok">● connected</span>`
            : `<span class="warn">● ${esc(boot.stage || "starting")}</span>`,
      ),
    );
    box.innerHTML = `<div class="db-table">${rows.join("")}</div>`;
    const sw = $("#cfg-db-switch");
    if (sw) sw.style.display = "block";
  } catch (e) {
    box.innerHTML = `<span class="err">${esc(e.message || "could not load database status")}</span>`;
    const sw = $("#cfg-db-switch");
    if (sw) sw.style.display = "block";
  }
}
// Ollama endpoint presets: point at native Ollama (uses the computer's GPU) or the
// bundled Docker container. Only fill the field — the user still clicks Save (LLM card).
// Show the Ollama-only convenience buttons only when Ollama is the provider (the
// input fields themselves stay common across every provider).
function applyLlmProviderUI(prov) {
  const presets = $("#cfg-ollama-presets");
  if (presets) presets.style.display = prov === "ollama" ? "flex" : "none";
}
if ($("#cfg-ollama-native"))
  $("#cfg-ollama-native").onclick = () => {
    const inp = $("#cfg-llm-endpoint");
    if (!inp || inp.disabled) return;
    inp.value = "http://host.docker.internal:11434";
    const h = $("#cfg-ollama-hint");
    if (h)
      h.innerHTML = `Points at Ollama on your computer (uses its GPU — much faster). <b>Important:</b> first <b>stop the bundled Ollama</b> so port 11434 is free (<code>docker compose stop ollama</code>), then <b>install Ollama</b> from ollama.com and pull a model, then click <b>Save</b>. <span class="warn">If the bundled Ollama is still running, this address just reaches it again (no speed gain).</span> On Linux, also add <code>--add-host=host.docker.internal:host-gateway</code> to the app container.`;
  };
if ($("#cfg-ollama-bundled"))
  $("#cfg-ollama-bundled").onclick = () => {
    const inp = $("#cfg-llm-endpoint");
    if (!inp || inp.disabled) return;
    inp.value = "http://ollama:11434";
    const h = $("#cfg-ollama-hint");
    if (h)
      h.innerHTML = `Set to the bundled Docker Ollama (no install, but CPU-only — slower for the language model). Click <b>Save</b> to apply.`;
  };
function dbRow(k, v) {
  return `<div class="db-r"><span class="db-k">${esc(k)}</span><span class="db-v">${v}</span></div>`;
}
if ($("#cfg-db-refresh")) $("#cfg-db-refresh").onclick = loadDbStatus;

// One simple action: copy the user's data into the database they entered, then switch
// to it. (If that database already has data, we ask once whether to overwrite it; if
// wardenIQ is busy with other work, we ask once whether to start anyway.)
async function runDbSwitch(overwrite, overrideBusy) {
  const uri = ($("#cfg-db-uri").value || "").trim();
  const st = $("#cfg-db-status"),
    btn = $("#cfg-db-switch-go"),
    lbl = "Switch to this database";
  if (!uri) {
    if (st) {
      st.classList.remove("ok", "err");
      st.innerHTML = `<span class="warn">Enter a database connection string.</span>`;
    }
    return;
  }
  btn.disabled = true;
  btn.textContent = "Starting…";
  if (st) {
    st.classList.remove("ok", "err");
    st.classList.add("is-saving");
    st.textContent = "Checking the database…";
  }
  try {
    const r = await api("/api/db-migrate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_uri: uri,
        overwrite: !!overwrite,
        override_busy: !!overrideBusy,
      }),
    });
    watchJob(r.job_id, (j) => {
      if (!st) return;
      if (j.status === "running") {
        st.classList.add("is-saving");
        st.classList.remove("ok", "err");
        st.textContent = `Transferring your data…${j.progress ? ` ${j.progress}%` : ""}`;
      } else if (j.status === "succeeded") {
        const res = j.result || {};
        st.classList.remove("is-saving");
        // A best-effort copy (started while busy, on request) can pass with warnings --
        // never hide those behind the plain success message.
        const warns = (res.warnings || [])
          .map((w) => `<div class="warn">${esc(w)}</div>`)
          .join("");
        // How to confirm the new database came up with working search after the restart.
        const check = res.post_restart_check
          ? `<div class="muted">${esc(res.post_restart_check)}</div>`
          : "";
        st.innerHTML = `<span class="ok">Your data has been copied to the new database.</span>${warns} Run <code>${esc(res.apply_cmd || "docker compose up -d")}</code> to finish switching.${check}`;
        $("#cfg-db-uri").value = "";
        btn.disabled = false;
        btn.textContent = lbl;
      } else {
        st.classList.remove("is-saving");
        st.innerHTML = `<span class="err">Couldn't switch: ${esc(j.error || "unknown error")}</span>`;
        btn.disabled = false;
        btn.textContent = lbl;
      }
    });
  } catch (e) {
    btn.disabled = false;
    btn.textContent = lbl;
    // If the target already has data, offer one clear yes/no instead of a separate control.
    if (!overwrite && /already contains data/i.test(e.message || "")) {
      if (
        await confirmModal({
          title: "Replace existing data?",
          body: "That database already has data in it.\n\nReplace it with your current data?",
          confirmText: "Replace data",
          danger: true,
        })
      )
        return runDbSwitch(true, overrideBusy);
      if (st) {
        st.classList.remove("is-saving");
        st.innerHTML = `<span class="muted">Cancelled — pick an empty database, or confirm replacing it.</span>`;
      }
      return;
    }
    // wardenIQ is running other work: copying a live database can capture it half-written,
    // so the server refuses unless the user explicitly accepts a best-effort snapshot.
    if (!overrideBusy && /currently busy|sync is currently running/i.test(e.message || "")) {
      if (
        await confirmModal({
          title: "wardenIQ is busy",
          body: `${e.message}\n\nCopying while it is busy is a best-effort snapshot: changes made during the copy may not be included. Start anyway?`,
          confirmText: "Start anyway",
          danger: true,
        })
      )
        return runDbSwitch(overwrite, true);
      if (st) {
        st.classList.remove("is-saving");
        st.innerHTML = `<span class="muted">Cancelled — try again once wardenIQ is idle.</span>`;
      }
      return;
    }
    if (st) {
      st.classList.remove("is-saving");
      st.innerHTML = `<span class="err">${esc(e.message)}</span>`;
    }
  }
}
if ($("#cfg-db-switch-go"))
  $("#cfg-db-switch-go").onclick = async () => {
    if (!($("#cfg-db-uri").value || "").trim()) {
      const st = $("#cfg-db-status");
      if (st) {
        st.classList.remove("ok", "err");
        st.innerHTML = `<span class="warn">Enter a database connection string.</span>`;
      }
      return;
    }
    if (
      !(await confirmModal({
        title: "Switch database?",
        body: "Copy your data to this database and switch wardenIQ to it?\n\nYour current database stays intact until you restart, so nothing is lost. The copy is a best-effort snapshot taken while wardenIQ is idle, and it is verified before wardenIQ is switched.",
        confirmText: "Switch database",
      }))
    )
      return;
    runDbSwitch(false);
  };

let EMBED_OPTS = {};
function updateEmbedModelOptions(provider, selected) {
  // Built-in embedding models only — fixed list per provider, no custom entry.
  const opts = EMBED_OPTS[provider] || [];
  const sel = $("#cfg-embed-model-select"),
    inp = $("#cfg-embed-model");
  if (!sel || !inp) return;
  if (!opts.length) {
    // No built-in list (custom OpenAI-compatible) → plain typed model name.
    sel.style.display = "none";
    inp.style.display = "block";
    inp.value = selected || "";
    return;
  }
  sel.style.display = "";
  const chosen = opts.some((m) => m.id === selected) ? selected : opts[0].id;
  sel.innerHTML = opts
    .map(
      (m) =>
        `<option value="${esc(m.id)}" ${m.id === chosen ? "selected" : ""}>${esc(m.id)} (${m.dim}-d)</option>`,
    )
    .join("");
  inp.style.display = "none";
  inp.value = sel.value;
}
if ($("#cfg-embed-provider"))
  $("#cfg-embed-provider").onchange = () =>
    updateEmbedModelOptions($("#cfg-embed-provider").value, "");
if ($("#cfg-embed-model-select"))
  $("#cfg-embed-model-select").onchange = () => {
    const inp = $("#cfg-embed-model");
    if (inp) inp.value = $("#cfg-embed-model-select").value;
  };
if ($("#cfg-embed-save"))
  $("#cfg-embed-save").onclick = async () => {
    const provider = $("#cfg-embed-provider").value;
    // Dropdown for providers with a built-in list; the text input only for providers
    // without one (custom OpenAI-compatible), which is the only time it's visible.
    const inpEl = $("#cfg-embed-model");
    const model =
      inpEl && inpEl.style.display !== "none"
        ? inpEl.value.trim()
        : $("#cfg-embed-model-select").value;
    if (!model) {
      toast("Choose or enter an embedding model", true);
      return;
    }
    if (
      !(await confirmModal({
        title: "Switch embedding model?",
        body: "This will RE-EMBED every stored vector and rebuild the search indexes. Search, dedup and Mind-Map results will be degraded until it completes.",
        confirmText: "Switch & re-embed",
        danger: true,
      }))
    )
      return;
    const btn = $("#cfg-embed-save");
    btn.disabled = true;
    $("#cfg-embed-status").textContent =
      "Validating model & measuring dimension…";
    const body = {
      provider,
      model,
      base_url: $("#cfg-embed-base").value.trim(),
      region: $("#cfg-embed-region") ? $("#cfg-embed-region").value.trim() : "",
    };
    const key = $("#cfg-embed-key").value;
    if (key) body.api_key = key;
    try {
      const r = await api("/api/embedding/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      $("#cfg-embed-status").innerHTML =
        `<span class="ok">Switching to ${esc(r.provider)}/${esc(r.model)} (${r.dim}-d) — re-embedding…</span>`;
      $("#cfg-embed-log").style.display = "block";
      $("#cfg-embed-key").value = "";
      watchJob(r.job_id, (j) => {
        renderJobLog("#cfg-embed-log", j);
        if (j.status !== "running") {
          btn.disabled = false;
          if (j.status === "failed")
            $("#cfg-embed-status").innerHTML =
              `<span class="err">Re-embed failed: ${esc(j.error || "")}</span>`;
          else {
            $("#cfg-embed-status").innerHTML =
              `<span class="ok">Done — all vectors re-embedded with ${esc(r.model)} (${r.dim}-d).</span>`;
            loadConfig();
          }
        }
      });
    } catch (e) {
      $("#cfg-embed-status").innerHTML =
        `<span class="err">${esc(e.message)}</span>`;
      btn.disabled = false;
    }
  };

const PREDEFINED_MODELS = {
  ollama: [
    { id: "llama3.2:1b", label: "Llama 3.2 1B — fastest, basic quality" },
    { id: "qwen2.5:3b", label: "Qwen 2.5 3B — balanced (built-in default)" },
    { id: "llama3.2:3b", label: "Llama 3.2 3B — balanced" },
    { id: "qwen2.5:7b", label: "Qwen 2.5 7B — best quality, slowest" },
  ],
  groq: [
    { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B — best quality" },
    { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B Instant — fastest" },
    { id: "llama3-70b-8192", label: "Llama 3 70B" },
    { id: "llama3-8b-8192", label: "Llama 3 8B" },
    { id: "gemma2-9b-it", label: "Gemma 2 9B" },
    { id: "mixtral-8x7b-32768", label: "Mixtral 8x7B" },
  ],
  // Curated per provider — newest flagships + balanced + cost-efficient staples.
  openai: [
    { id: "gpt-5", label: "GPT-5 (newest)" },
    { id: "gpt-5-mini", label: "GPT-5 Mini — cost-efficient" },
    { id: "gpt-4.1", label: "GPT-4.1" },
    { id: "gpt-4.1-mini", label: "GPT-4.1 Mini" },
    { id: "gpt-4o", label: "GPT-4o" },
    { id: "gpt-4o-mini", label: "GPT-4o Mini — cheapest" },
  ],
  anthropic: [
    { id: "claude-opus-4-8", label: "Claude Opus 4.8 (newest)" },
    { id: "claude-sonnet-5", label: "Claude Sonnet 5 — balanced" },
    { id: "claude-haiku-4-5", label: "Claude Haiku 4.5 — cheapest" },
    { id: "claude-opus-4-6", label: "Claude Opus 4.6" },
    { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
    { id: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku" },
  ],
  gemini: [
    { id: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro (newest)" },
    { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash (newest)" },
    { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro — best quality" },
    { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash — balanced" },
    { id: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite" },
    { id: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite — cheapest" },
  ],
  mistral: [
    { id: "mistral-large-latest", label: "Mistral Large — best quality" },
    { id: "mistral-medium-latest", label: "Mistral Medium — balanced" },
    { id: "mistral-small-latest", label: "Mistral Small — cost-efficient" },
    { id: "ministral-8b-latest", label: "Ministral 8B — cheapest" },
    { id: "open-mistral-nemo", label: "Mistral Nemo" },
    { id: "codestral-latest", label: "Codestral — code" },
  ],
  "openai-compatible": [],
  // Bedrock model IDs vary by account/region and may be inference-profile ARNs, so
  // this stays free-text (empty list → the model text input is shown).
  bedrock: [],
};

function updateModelOptions(provider, selectedModel) {
  // Fixed curated dropdown of selected models per provider. Providers without a
  // list (custom OpenAI-compatible, Bedrock) fall back to a typed model id since
  // their model names are account/endpoint-specific.
  const models = PREDEFINED_MODELS[provider] || [];
  const select = $("#cfg-llm-model-select");
  const input = $("#cfg-llm-model");
  if (!select || !input) return;

  if (!models.length) {
    select.style.display = "none";
    input.style.display = "block";
    input.value = selectedModel || "";
    return;
  }

  select.style.display = "";
  const sel = models.some((m) => m.id === selectedModel)
    ? selectedModel
    : models[0].id;
  select.innerHTML = models
    .map(
      (m) =>
        `<option value="${m.id}" ${m.id === sel ? "selected" : ""}>${m.label}</option>`,
    )
    .join("");
  input.style.display = "none";
  input.value = select.value; // hidden input mirrors the dropdown; save reads it
}

if ($("#cfg-llm-model-select")) {
  $("#cfg-llm-model-select").onchange = (e) => {
    const input = $("#cfg-llm-model");
    if (input) input.value = e.target.value; // dropdown choice → mirror to hidden input
  };
}

if ($("#cfg-llm-provider")) {
  $("#cfg-llm-provider").onchange = (e) => {
    const prov = e.target.value;
    updateModelOptions(prov, "");
    applyLlmProviderUI(prov);
    // Reset the unified endpoint + its hint when switching provider families.
    const ep = $("#cfg-llm-endpoint");
    if (ep) {
      ep.disabled = false;
      ep.value = "";
    }
    const h = $("#cfg-ollama-hint");
    if (h)
      h.innerHTML =
        prov === "ollama"
          ? `Click <b>Use bundled (Docker) Ollama</b> or <b>Use Ollama on my computer</b>, or leave blank for the bundled default.`
          : "";
  };
}
async function saveConfigSection({
  buttonId,
  statusId,
  body,
  clearIds = [],
  successMessage = "Settings saved",
}) {
  const btn = $(buttonId),
    status = $(statusId);
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Saving...";
  if (status) {
    status.classList.add("is-saving");
    status.classList.remove("ok", "err");
    status.textContent = "Checking and saving settings...";
  }
  try {
    await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    clearIds.forEach((id) => {
      if ($(id)) $(id).value = "";
    });
    await loadConfig();
    if (status) {
      status.classList.remove("is-saving");
      status.innerHTML = `<span class="ok">${esc(successMessage)}</span>`;
    }
  } catch (e) {
    if (status) {
      status.classList.remove("is-saving");
      status.innerHTML = `<span class="err">${esc(e.message)}</span>`;
    }
    throw e;
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}
$("#cfg-llm-save").onclick = async () => {
  const prov = $("#cfg-llm-provider").value;
  const ep = $("#cfg-llm-endpoint");
  const epv = ep ? ep.value.trim() : "";
  // Unified "Endpoint URL" field maps to the Ollama URL for Ollama, else the
  // provider base/endpoint URL (custom OpenAI-compatible or a Bedrock VPC endpoint).
  const b = {
    llm_provider: prov,
    llm_model: $("#cfg-llm-model").value.trim(),
    llm_region: $("#cfg-llm-region").value.trim(),
  };
  if (prov === "ollama") {
    if (ep && !ep.disabled) b.ollama_url = epv;
    b.llm_base_url = "";
  } else {
    b.llm_base_url = epv;
  }
  const k = $("#cfg-llm-key").value;
  if (k) b.llm_api_key = k;
  try {
    await saveConfigSection({
      buttonId: "#cfg-llm-save",
      statusId: "#cfg-llm-status",
      body: b,
      clearIds: ["#cfg-llm-key"],
      successMessage: "LLM settings saved",
    });
    // For Ollama, report what the reached instance actually has, so users can confirm
    // which Ollama answered (bundled container vs a native install).
    if (b.llm_provider === "ollama") {
      const h = $("#cfg-ollama-hint");
      if (h) {
        try {
          const r = await api("/api/llm/test", { method: "POST" });
          const n = (r.models || []).length;
          h.innerHTML = `<span class="ok">Connected to Ollama — ${n} model${n === 1 ? "" : "s"} available${n ? `: <code>${(r.models || []).slice(0, 6).map(esc).join(", ")}</code>` : ""}.</span>`;
        } catch (e) {
          h.innerHTML = `<span class="warn">Saved, but the test call to Ollama failed: ${esc(e.message)}</span>`;
        }
      }
    }
  } catch (e) {
    toast(e.message, true);
  }
};
$("#cfg-jira-save").onclick = async () => {
  const b = {
    jira_base_url: $("#cfg-jira-base").value.trim(),
    jira_email: $("#cfg-jira-email").value.trim(),
  };
  const t = $("#cfg-jira-token").value;
  if (t) b.jira_api_token = t;
  // Nothing entered and nothing previously configured: hitting Save here would
  // silently no-op on the backend (empty base URL/email/token all validate as
  // "unset") and still report success, which reads as "Jira is now configured."
  // Block it client-side instead of showing a false-positive "saved" message.
  const tokenAlreadySet =
    $("#cfg-jira-token").placeholder !== "API token is required";
  if (!b.jira_base_url && !b.jira_email && !t && !tokenAlreadySet) {
    toast("Enter Base URL, Email and API token to configure Jira", true);
    return;
  }
  // The stored token exists but can no longer be decrypted (see backend
  // jira_token_readable) -- leaving it blank here would just re-trip the
  // server's "all required" validation. Catch it client-side with the same
  // explanation the placeholder already gave, instead of a generic 400.
  if (!t && $("#cfg-jira-token").placeholder === "Saved token can't be read — re-enter it") {
    toast("Your saved Jira API token can no longer be read — re-enter it to save", true);
    return;
  }
  try {
    await saveConfigSection({
      buttonId: "#cfg-jira-save",
      statusId: "#cfg-jira-status",
      body: b,
      clearIds: ["#cfg-jira-token"],
      successMessage: "Jira settings saved",
    });
  } catch (e) {
    toast(e.message, true);
  }
};
$("#cfg-figma-save").onclick = async () => {
  const t = $("#cfg-figma-token").value;
  if (!t) {
    toast("Enter a Figma token", true);
    return;
  }
  try {
    await saveConfigSection({
      buttonId: "#cfg-figma-save",
      statusId: "#cfg-figma-status",
      body: { figma_api_token: t },
      clearIds: ["#cfg-figma-token"],
      successMessage: "Figma token saved",
    });
  } catch (e) {
    toast(e.message, true);
  }
};
$("#cfg-poll-save").onclick = async () => {
  const v = parseInt($("#cfg-poll-interval").value, 10);
  const min = parseInt($("#cfg-poll-interval").min, 10) || 30;
  if (!Number.isFinite(v) || v < min) {
    toast(`Enter a poll interval of at least ${min} seconds`, true);
    return;
  }
  try {
    await saveConfigSection({
      buttonId: "#cfg-poll-save",
      statusId: "#cfg-poll-status",
      body: { poll_interval_s: v },
      successMessage: `Poll interval set to ${v}s (≈ ${(v / 60).toFixed(v % 60 ? 1 : 0)} min)`,
    });
    if (typeof loadSyncStatus === "function") loadSyncStatus();
  } catch (e) {
    toast(e.message, true);
  }
};
$("#cfg-smtp-save").onclick = async () => {
  const b = {
    smtp_host: $("#cfg-smtp-host").value.trim(),
    smtp_port: parseInt($("#cfg-smtp-port").value) || null,
    smtp_user: $("#cfg-smtp-user").value.trim(),
    smtp_from: $("#cfg-smtp-from").value.trim(),
    smtp_tls: $("#cfg-smtp-tls").checked,
    smtp_ssl: $("#cfg-smtp-ssl").checked,
  };
  const p = $("#cfg-smtp-pass").value.trim();
  if (p) b.smtp_pass = p;
  try {
    await saveConfigSection({
      buttonId: "#cfg-smtp-save",
      statusId: "#cfg-smtp-status",
      body: b,
      clearIds: ["#cfg-smtp-pass"],
      successMessage: b.smtp_host ? "SMTP settings saved" : "Settings saved",
    });
  } catch (e) {
    toast(e.message, true);
  }
};
$("#cfg-smtp-test").onclick = async () => {
  const st = $("#cfg-smtp-status");
  const def = $("#cfg-smtp-user").value.trim() || (ME && ME.email) || "";
  const to = (
    (await uiPrompt("Send test email", "Send a test sign-in email to:", def)) ||
    ""
  ).trim();
  if (!to) return;
  const btn = $("#cfg-smtp-test"),
    lbl = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Sending...";
  if (st) {
    st.classList.remove("ok", "err");
    st.classList.add("is-saving");
    st.textContent = "Sending test email (uses saved settings)...";
  }
  try {
    await api("/api/smtp/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: to }),
    });
    if (st) {
      st.classList.remove("is-saving");
      st.innerHTML = `<span class="ok">Test email sent to ${esc(to)} — check the inbox (and spam).</span>`;
    }
  } catch (e) {
    if (st) {
      st.classList.remove("is-saving");
      st.innerHTML = `<span class="err">${esc(e.message)}</span>`;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = lbl;
  }
};

if ($("#cfg-s3-save")) {
  $("#cfg-s3-save").onclick = async () => {
    const b = {
      s3_bucket: $("#cfg-s3-bucket").value.trim(),
      s3_region: $("#cfg-s3-region").value.trim(),
      s3_access_key_id: $("#cfg-s3-key").value.trim(),
      s3_prefix: $("#cfg-s3-prefix").value.trim(),
      s3_enabled: $("#cfg-s3-enabled").checked,
    };
    const sec = $("#cfg-s3-secret").value.trim();
    if (sec) b.s3_secret_access_key = sec;
    try {
      await saveConfigSection({
        buttonId: "#cfg-s3-save",
        statusId: "#cfg-s3-status",
        body: b,
        clearIds: ["#cfg-s3-secret"],
        successMessage: b.s3_bucket
          ? "AWS S3 settings saved"
          : "Settings saved",
      });
    } catch (e) {
      toast(e.message, true);
    }
  };
}

if ($("#cfg-s3-test")) {
  $("#cfg-s3-test").onclick = async () => {
    const st = $("#cfg-s3-status");
    const bucket = $("#cfg-s3-bucket").value.trim();
    const region = $("#cfg-s3-region").value.trim();
    const access_key_id = $("#cfg-s3-key").value.trim();
    const secret_access_key = $("#cfg-s3-secret").value.trim();
    if (!bucket) {
      if (st)
        st.innerHTML = `<span class="err">Enter an S3 bucket name to test connection</span>`;
      return;
    }
    const btn = $("#cfg-s3-test"),
      lbl = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Testing...";
    if (st) {
      st.classList.remove("ok", "err");
      st.classList.add("is-saving");
      st.textContent = "Testing S3 bucket connection...";
    }
    try {
      const res = await api("/api/settings/s3/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bucket,
          region,
          access_key_id,
          secret_access_key,
        }),
      });
      if (st) {
        st.classList.remove("is-saving");
        st.innerHTML = `<span class="ok">${esc(res.message || "Connected to AWS S3 bucket successfully")}</span>`;
      }
    } catch (e) {
      if (st) {
        st.classList.remove("is-saving");
        st.innerHTML = `<span class="err">${esc(e.message)}</span>`;
      }
    } finally {
      btn.disabled = false;
      btn.textContent = lbl;
    }
  };
}

