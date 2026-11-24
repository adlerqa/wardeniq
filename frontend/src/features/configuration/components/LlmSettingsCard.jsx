import { useState } from "react";

import { api } from "../../../lib/api.js";
import { toast } from "../../../lib/compatBridge.js";
import { useCardStatus, useSectionSave, useSettingsForm } from "../hooks/useCardState.js";
import {
  OLLAMA_BUNDLED_URL,
  OLLAMA_NATIVE_URL,
  llmModelChoice,
  llmPlaceholders,
  llmSaveBody,
} from "../lib/config.js";
import { CardStatus } from "./CardStatus.jsx";

const PROVIDERS = ["ollama", "groq", "openai", "anthropic", "gemini", "mistral", "openai-compatible", "bedrock"];

function initLlm(s, loaded) {
  const llmProv = s.llm_provider || "ollama";
  const lock = s.provider_lock && PROVIDERS.includes(s.provider_lock) ? s.provider_lock : "";
  let endpoint = s.llm_base_url || "";
  let endpointDisabled = false;
  let hint = null;
  if (loaded && llmProv === "ollama") {
    if (s.ollama_url_env_locked) {
      endpoint = s.ollama_url_effective || "";
      endpointDisabled = true;
      hint = (
        <>
          Pinned by <code>OLLAMA_URL</code> in <code>.env</code> (takes priority). Edit <code>.env</code> to change it.
        </>
      );
    } else {
      endpoint = s.ollama_url || "";
      hint = (
        <>
          In use: <code>{s.ollama_url_effective || ""}</code>
          {s.ollama_url ? "" : " (bundled default)"}. Applies immediately on save — no restart.
        </>
      );
    }
  }
  return {
    // The select shows the locked provider; the model list and placeholders
    // follow the saved provider until the user picks another (as before).
    provider: lock || llmProv,
    locked: !!lock,
    uiProvider: llmProv,
    model: llmModelChoice(llmProv, s.llm_model || "").value,
    region: s.llm_region || "",
    endpoint,
    endpointDisabled,
    hint,
  };
}

const NATIVE_HINT = (
  <>
    Points at Ollama on your computer (uses its GPU — much faster). <b>Important:</b> first{" "}
    <b>stop the bundled Ollama</b> so port 11434 is free (<code>docker compose stop ollama</code>), then{" "}
    <b>install Ollama</b> from ollama.com and pull a model, then click <b>Save</b>.{" "}
    <span className="warn">
      If the bundled Ollama is still running, this address just reaches it again (no speed gain).
    </span>{" "}
    On Linux, also add <code>--add-host=host.docker.internal:host-gateway</code> to the app container.
  </>
);
const BUNDLED_HINT = (
  <>
    Set to the bundled Docker Ollama (no install, but CPU-only — slower for the language model). Click <b>Save</b>{" "}
    to apply.
  </>
);
const SWITCHED_TO_OLLAMA_HINT = (
  <>
    Click <b>Use bundled (Docker) Ollama</b> or <b>Use Ollama on my computer</b>, or leave blank for the bundled
    default.
  </>
);

/** LLM provider, model, endpoint, region and key (card 1). */
export default function LlmSettingsCard({ settings, version, saveSettings }) {
  const s = settings || {};
  const [form, update] = useSettingsForm(settings, version, initLlm);
  const [key, setKey] = useState("");
  const [hintAfterSave, setHintAfterSave] = useState(null);
  const [status, setStatus] = useCardStatus(
    version,
    settings
      ? s.llm_api_key_set
        ? { tone: "ok", text: "API key / secret configured" }
        : { tone: "muted", text: "no API key set" }
      : null,
  );
  const [busy, save] = useSectionSave(version, saveSettings, setStatus);
  // Before the first load the model select is empty, as in the static markup.
  const choice = settings ? llmModelChoice(form.uiProvider, form.model) : { options: [], value: "", freeText: false };
  const placeholders = settings ? llmPlaceholders(form.uiProvider, s) : null;
  const hint = hintAfterSave && hintAfterSave.ver === version ? hintAfterSave.node : form.hint;

  const changeProvider = (prov) =>
    update({
      provider: prov,
      uiProvider: prov,
      model: llmModelChoice(prov, "").value,
      endpoint: "",
      endpointDisabled: false,
      hint: prov === "ollama" ? SWITCHED_TO_OLLAMA_HINT : null,
    });

  const preset = (url, presetHint) => {
    if (form.endpointDisabled) return;
    update({ endpoint: url, hint: presetHint });
  };

  const onSave = async () => {
    const body = llmSaveBody({ ...form, key });
    try {
      const v = await save(body, "LLM settings saved");
      setKey("");
      // For Ollama, report what the reached instance has, so users can tell
      // which Ollama answered (bundled container vs a native install).
      if (body.llm_provider === "ollama") {
        try {
          const r = await api("/api/llm/test", { method: "POST" });
          const models = r.models || [];
          const n = models.length;
          setHintAfterSave({
            ver: v,
            node: (
              <span className="ok">
                Connected to Ollama — {n} model{n === 1 ? "" : "s"} available
                {n ? (
                  <>
                    : <code>{models.slice(0, 6).join(", ")}</code>
                  </>
                ) : null}
                .
              </span>
            ),
          });
        } catch (e) {
          setHintAfterSave({
            ver: v,
            node: <span className="warn">Saved, but the test call to Ollama failed: {e.message}</span>,
          });
        }
      }
    } catch (e) {
      toast(e.message, { type: "err", title: "Couldn't save LLM settings" });
    }
  };

  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">1</span>
          <h2>LLM</h2>
        </div>
        <span className="cfg-badge req">Required</span>
      </div>
      <div className="sub">
        <b>Ollama (built-in)</b>{" "}
        runs the AI inside this Docker stack — free, private, no API key, nothing to install (this is the default). Or pick a hosted provider — OpenAI, Anthropic (Claude), Google Gemini, Mistral, or any OpenAI-compatible endpoint — with your own API key. Or{" "}
        <b>AWS Bedrock</b>{" "}
        for enterprise / air-gapped deployments. Every provider uses the same fields below — just fill the ones it needs (hover each{" "}
        <b>i</b>{" "}
        for guidance). Used for all generation, code review, coverage, and impact analysis.
      </div>
      <div className="cfg-field">
        <label>
          Provider
          <span className="fi" tabIndex="0" data-tip="Ollama — free local AI (open-source, no key). OpenAI / Anthropic / Gemini / Mistral / Groq — hosted APIs (need an API key). AWS Bedrock — enterprise / air-gapped: uses an AWS region plus an IAM role or access keys.">i</span>
        </label>
        <select
          id="cfg-llm-provider"
          value={form.provider}
          disabled={form.locked}
          onChange={(e) => changeProvider(e.target.value)}
        >
          <option value="ollama">Ollama (built-in)</option>
          <option value="groq">Groq (fast · free tier)</option>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic (Claude)</option>
          <option value="gemini">Google Gemini</option>
          <option value="mistral">Mistral</option>
          <option value="openai-compatible">OpenAI-compatible (custom)</option>
          <option value="bedrock">AWS Bedrock (enterprise)</option>
        </select>
      </div>
      <div className="cfg-field">
        <label>
          Model
          <span className="fi" tabIndex="0" data-tip="The model identifier. Ollama: qwen2.5:7b. OpenAI: gpt-4o. Anthropic: claude-sonnet-4-6. AWS Bedrock: the full model ID or inference-profile ARN, e.g. anthropic.claude-3-5-sonnet-20241022-v2:0. Model choice affects quality, cost and speed; see Choosing a model in docs/configuration.md.">i</span>
        </label>
        <select
          id="cfg-llm-model-select"
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
          id="cfg-llm-model"
          placeholder="Enter model name / Bedrock model ID..."
          value={choice.value}
          onChange={(e) => update({ model: e.target.value })}
          style={{ display: choice.freeText ? "block" : "none", marginTop: "6px" }}
        />
        <div className="muted" id="cfg-model-guidance" style={{ fontSize: "11px", marginTop: "6px" }}>
          Not sure which model? On local Ollama, qwen2.5:3b is the fast default and qwen2.5:7b gave the best
          results in our tests (about twice as slow, needs ~16 GB RAM). See &ldquo;Choosing a model&rdquo; in docs/configuration.md.
        </div>
      </div>
      <div className="cfg-field" id="cfg-llm-endpoint-field">
        <label>
          Endpoint URL
          <span className="muted" style={{ fontWeight: "400" }}>(optional)</span>
          <span className="fi" tabIndex="0" data-tip="Leave blank for the provider default. Ollama: where Ollama runs (bundled Docker, your computer, or a remote host). OpenAI-compatible: your custom base URL. AWS Bedrock: an optional private VPC / PrivateLink endpoint for air-gapped networks.">i</span>
        </label>
        <input
          id="cfg-llm-endpoint"
          placeholder={placeholders ? placeholders.endpoint : "Optional — blank uses bundled Ollama"}
          value={form.endpoint}
          disabled={form.endpointDisabled}
          onChange={(e) => update({ endpoint: e.target.value })}
        />
        <div
          style={{
            display: settings && form.provider !== "ollama" ? "none" : "flex",
            gap: "8px",
            flexWrap: "wrap",
            marginTop: "6px",
          }}
          id="cfg-ollama-presets"
        >
          <button
            type="button"
            className="ghost"
            id="cfg-ollama-native"
            style={{ fontSize: "11.5px", padding: "5px 10px" }}
            onClick={() => preset(OLLAMA_NATIVE_URL, NATIVE_HINT)}
          >
            Use Ollama on my computer
          </button>
          <button
            type="button"
            className="ghost"
            id="cfg-ollama-bundled"
            style={{ fontSize: "11.5px", padding: "5px 10px" }}
            onClick={() => preset(OLLAMA_BUNDLED_URL, BUNDLED_HINT)}
          >
            Use bundled (Docker) Ollama
          </button>
        </div>
        <div className="muted" id="cfg-ollama-hint" style={{ fontSize: "11px", marginTop: "6px" }}>
          {hint}
        </div>
      </div>
      <div className="cfg-field" id="cfg-llm-region-field">
        <label>
          AWS region
          <span className="muted" style={{ fontWeight: "400" }}>(AWS Bedrock only)</span>
          <span className="fi" tabIndex="0" data-tip="AWS Bedrock only. The AWS region your Bedrock models are enabled in, e.g. us-east-1. Leave blank for every other provider.">i</span>
        </label>
        <input
          id="cfg-llm-region"
          placeholder="e.g. us-east-1"
          value={form.region}
          onChange={(e) => update({ region: e.target.value })}
        />
      </div>
      <div className="cfg-field">
        <label>
          API key / secret
          <span className="fi" tabIndex="0" data-tip="Ollama: usually blank (only for a secured/remote Ollama behind a token). Hosted providers: your API key. AWS Bedrock: leave blank to use the machine's IAM role (recommended for air-gapped), or enter accessKeyId:secretAccessKey.">i</span>
        </label>
        <input
          type="password"
          id="cfg-llm-key"
          placeholder={placeholders ? placeholders.key : "Optional — only for secured Ollama endpoints"}
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </div>
      <CardStatus id="cfg-llm-status" status={status} />
      <div className="cfg-actions">
        <button className="go" id="cfg-llm-save" disabled={busy} onClick={onSave}>
          {busy ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}
