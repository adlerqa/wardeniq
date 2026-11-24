import { useState } from "react";

import { api } from "../../../lib/api.js";
import { confirmModal, renderJobLog, toast, watchJob } from "../../../lib/compatBridge.js";
import { useCardStatus, useSettingsForm } from "../hooks/useCardState.js";
import { embedModelChoice, embedProviderAllowed, embeddingPlaceholders } from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

const PROVIDER_LABELS = {
  ollama: "Ollama (built-in)",
  openai: "OpenAI",
  gemini: "Google Gemini",
  voyage: "Voyage AI",
  "openai-compatible": "OpenAI-compatible (custom)",
  bedrock: "AWS Bedrock (enterprise)",
};
const PROVIDERS = Object.keys(PROVIDER_LABELS);

function initEmbed(s) {
  let provider = s.embed_provider || "ollama";
  if (!embedProviderAllowed(s.provider_lock, provider)) provider = "ollama";
  return {
    provider,
    model: embedModelChoice(s.embed_model_options, provider, s.embed_model || "").value,
    base: s.embed_base_url || "",
    region: s.embed_region || "",
  };
}

/**
 * Embedding provider / model (card 2). Saving switches the model and starts a
 * re-embed job whose log is written into #cfg-embed-log by the compat
 * renderJobLog (React leaves that element's contents alone).
 */
export default function EmbeddingSettingsCard({ settings, version, loadConfig }) {
  const s = settings || {};
  const [form, update] = useSettingsForm(settings, version, initEmbed);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [logShown, setLogShown] = useState(false);
  const [status, setStatus] = useCardStatus(
    version,
    settings
      ? {
          tone: "muted",
          text: `Active: ${initEmbed(s).provider} / ${s.embed_model || "nomic-embed-text"} · ${s.embed_dim || 768}-d${
            s.embed_api_key_set ? " · key set" : ""
          }`,
        }
      : null,
  );
  const choice = settings
    ? embedModelChoice(s.embed_model_options, form.provider, form.model)
    : { options: [], value: "", freeText: false };
  const placeholders = settings ? embeddingPlaceholders(form.provider, s) : null;

  const changeProvider = (provider) =>
    update({ provider, model: embedModelChoice(s.embed_model_options, provider, "").value });

  const onSave = async () => {
    const model = choice.freeText ? choice.value.trim() : choice.value;
    if (!model) {
      toast("Choose or enter an embedding model", true);
      return;
    }
    const ok = await confirmModal({
      title: "Switch embedding model?",
      body: "This will RE-EMBED every stored vector and rebuild the search indexes. Search, dedup and Mind-Map results will be degraded until it completes.",
      confirmText: "Switch & re-embed",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setStatus({ tone: "", text: "Validating model & measuring dimension…" });
    const body = { provider: form.provider, model, base_url: form.base.trim(), region: form.region.trim() };
    if (key) body.api_key = key;
    try {
      const r = await api("/api/embedding/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setStatus({ tone: "ok", text: `Switching to ${r.provider}/${r.model} (${r.dim}-d) — re-embedding…` });
      setLogShown(true);
      setKey("");
      watchJob(r.job_id, (j) => {
        renderJobLog("#cfg-embed-log", j);
        if (j.status !== "running") {
          setBusy(false);
          if (j.status === "failed") setStatus({ tone: "err", text: `Re-embed failed: ${j.error || ""}` });
          else {
            setStatus({ tone: "ok", text: `Done — all vectors re-embedded with ${r.model} (${r.dim}-d).` });
            loadConfig();
          }
        }
      });
    } catch (e) {
      setStatus({ tone: "err", text: e.message });
      toast(e.message, { type: "err", title: "Couldn't switch embedding model" });
      setBusy(false);
    }
  };

  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">2</span>
          <h2>Embedding model</h2>
        </div>
        <span className="cfg-badge glob">Global</span>
      </div>
      <div className="sub">Controls how documents and test cases are vectorised for search, dedup, and Mind-Map retrieval.</div>
      <div className="warn" style={{ marginTop: "8px" }}>
        <b>⚠ Switching affects the whole system — read before changing:</b>
        <ul style={{ margin: "6px 0 0", paddingLeft: "18px", lineHeight: "1.6" }}>
          <li>
            This is a{" "}
            <b>global, one-time migration</b>{" "}
            — it re-embeds{" "}
            <b>every project&apos;s</b>{" "}
            vectors (features, documents, test steps &amp; cases) and rebuilds the search indexes at the new model&apos;s dimension.
          </li>
          <li>
            <b>Search, dedup and Mind-Map are degraded until it finishes</b>{" "}
            — run it when the system is idle.
          </li>
          <li>Time and token cost scale with your total corpus size; hosted models spend tokens on the new provider (see Usage &amp; Cost).</li>
          <li>
            Your test cases, steps, documents and coverage are{" "}
            <b>not changed</b>{" "}
            — only their numeric embedding vectors are recomputed.
          </li>
          <li>Pick once at setup if you can; avoid switching repeatedly.</li>
        </ul>
      </div>
      <div className="cfg-field">
        <label>
          Provider
          <span className="fi" tabIndex="0" data-tip="Ollama — free local embeddings (no key). OpenAI / Gemini / Voyage — hosted (need an API key). AWS Bedrock — Titan or Cohere embeddings; uses an AWS region plus an IAM role or access keys.">i</span>
        </label>
        <select id="cfg-embed-provider" value={form.provider} onChange={(e) => changeProvider(e.target.value)}>
          {PROVIDERS.map((p) => (
            <option key={p} value={p} hidden={!embedProviderAllowed(s.provider_lock, p)}>
              {PROVIDER_LABELS[p]}
            </option>
          ))}
        </select>
      </div>
      <div className="cfg-field">
        <label>
          Model
          <span className="fi" tabIndex="0" data-tip="The embedding model. Ollama: nomic-embed-text. OpenAI: text-embedding-3-small. AWS Bedrock: amazon.titan-embed-text-v2:0 or cohere.embed-english-v3.">i</span>
        </label>
        <select
          id="cfg-embed-model-select"
          value={choice.freeText ? "" : choice.value}
          style={choice.freeText ? { display: "none" } : undefined}
          onChange={(e) => update({ model: e.target.value })}
        >
          {choice.options.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        <input
          id="cfg-embed-model"
          placeholder="Enter model name / Bedrock model ID..."
          value={choice.value}
          onChange={(e) => update({ model: e.target.value })}
          style={{ display: choice.freeText ? "block" : "none", marginTop: "6px" }}
        />
      </div>
      <div className="cfg-field" id="cfg-embed-region-field">
        <label>
          AWS region
          <span className="muted" style={{ fontWeight: "400" }}>(AWS Bedrock only)</span>
          <span className="fi" tabIndex="0" data-tip="AWS Bedrock only. The AWS region your Bedrock embedding model is enabled in, e.g. us-east-1. Leave blank for every other provider.">i</span>
        </label>
        <input
          id="cfg-embed-region"
          placeholder="e.g. us-east-1"
          value={form.region}
          onChange={(e) => update({ region: e.target.value })}
        />
      </div>
      <div className="cfg-field">
        <label>
          API key / secret
          <span className="fi" tabIndex="0" data-tip="Hosted providers: your API key. AWS Bedrock: leave blank to use the machine's IAM role, or enter accessKeyId:secretAccessKey. Ollama: leave blank.">i</span>
        </label>
        <input
          type="password"
          id="cfg-embed-key"
          placeholder={placeholders ? placeholders.key : "Optional — no key needed for bundled Ollama"}
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </div>
      <div className="cfg-field">
        <label>
          Endpoint URL
          <span className="muted" style={{ fontWeight: "400" }}>(optional)</span>
          <span className="fi" tabIndex="0" data-tip="Leave blank for the provider default. OpenAI-compatible: your custom base URL. AWS Bedrock: an optional private VPC / PrivateLink endpoint for air-gapped networks.">i</span>
        </label>
        <input
          id="cfg-embed-base"
          placeholder={placeholders ? placeholders.endpoint : "Not used with Ollama"}
          value={form.base}
          onChange={(e) => update({ base: e.target.value })}
        />
      </div>
      <CardStatus id="cfg-embed-status" status={status} />
      <div id="cfg-embed-log" className="cfg-log" style={{ display: logShown ? "block" : "none", whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "11px", marginTop: "8px", maxHeight: "160px", overflow: "auto" }}></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-embed-save" disabled={busy} onClick={onSave}>
          Switch &amp; re-embed
        </button>
      </div>
    </div>
  );
}
