/**
 * Pure helpers for the Configuration screen (was
 * compat/runtime/controllers/06-configuration.js).
 */

/** Placeholders of the LLM API key and endpoint inputs for a provider. */
export function llmPlaceholders(provider, settings = {}) {
  const keyIsRequired = !["ollama", "bedrock"].includes(provider);
  const endpointIsRequired = provider === "openai-compatible";
  const sameProvider = (settings.llm_provider || "ollama") === provider;
  const key =
    settings.llm_api_key_set && sameProvider
      ? "Leave blank to keep current"
      : keyIsRequired
        ? "API key is required"
        : provider === "ollama"
          ? "Optional — only for secured Ollama endpoints"
          : "Optional — use an AWS IAM role or access keys";
  const hasEndpoint =
    sameProvider &&
    (provider === "ollama" ? settings.ollama_url_env_locked || settings.ollama_url : settings.llm_base_url);
  const endpoint = hasEndpoint
    ? provider === "ollama"
      ? "Blank resets to bundled Ollama"
      : "Leave blank to keep current"
    : endpointIsRequired
      ? "Custom endpoint URL is required"
      : provider === "ollama"
        ? "Optional — blank uses bundled Ollama"
        : "Optional — uses the provider default";
  return { key, endpoint };
}

/** Placeholders of the embedding API key and endpoint inputs for a provider. */
export function embeddingPlaceholders(provider, settings = {}) {
  const sameProvider = (settings.embed_provider || "ollama") === provider;
  const keyIsRequired = !["ollama", "bedrock"].includes(provider);
  const key =
    sameProvider && settings.embed_api_key_set
      ? "Leave blank to keep current"
      : keyIsRequired
        ? "API key is required"
        : provider === "ollama"
          ? "Optional — no key needed for bundled Ollama"
          : "Optional — use an AWS IAM role or access keys";
  const hasEndpoint = sameProvider && settings.embed_base_url;
  const endpoint = hasEndpoint
    ? "Leave blank to keep current"
    : provider === "openai-compatible"
      ? "Custom endpoint URL is required"
      : provider === "ollama"
        ? "Not used with Ollama"
        : "Optional — uses the provider default";
  return { key, endpoint };
}

export const smtpPasswordPlaceholder = (settings = {}) =>
  settings.smtp_pass_set ? "Leave blank to keep current" : "SMTP password or app password";

/**
 * Jira token placeholder. Gate on jira_token_readable, not jira_token_set: a
 * stored token that no longer decrypts has no current value to keep.
 */
export const jiraTokenPlaceholder = (settings = {}) =>
  settings.jira_token_readable
    ? "Leave blank to keep current"
    : settings.jira_token_set
      ? "Saved token can't be read — re-enter it"
      : "API token is required";

export const figmaTokenPlaceholder = (settings = {}) =>
  settings.figma_token_set ? "Leave blank to keep current" : "API token is required";

export const s3SecretPlaceholder = (settings = {}) =>
  settings.s3_secret_access_key_set ? "Leave blank to keep current" : "Secret Access Key (optional)";

/** Curated LLM models per provider; empty list = free-text model id. */
export const PREDEFINED_MODELS = {
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
  // Model ids are account / endpoint specific here, so they stay free text.
  "openai-compatible": [],
  bedrock: [],
};

/**
 * Model picker state: { options: [{ value, label }], value, freeText }.
 * A provider with a list shows a select (falling back to its first model);
 * without one, a text input holding `selected`.
 */
export function llmModelChoice(provider, selected) {
  const models = PREDEFINED_MODELS[provider] || [];
  if (!models.length) return { options: [], value: selected || "", freeText: true };
  const value = models.some((m) => m.id === selected) ? selected : models[0].id;
  return { options: models.map((m) => ({ value: m.id, label: m.label })), value, freeText: false };
}

/** Same for embedding models, from the server's embed_model_options. */
export function embedModelChoice(modelOptions, provider, selected) {
  const opts = (modelOptions || {})[provider] || [];
  if (!opts.length) return { options: [], value: selected || "", freeText: true };
  const value = opts.some((m) => m.id === selected) ? selected : opts[0].id;
  return { options: opts.map((m) => ({ value: m.id, label: `${m.id} (${m.dim}-d)` })), value, freeText: false };
}

/** In a provider-locked (air-gapped) install only Ollama and the locked provider embed. */
export function embedProviderAllowed(lock, provider) {
  return !lock || provider === "ollama" || provider === lock;
}

/** "5" for 300 s, "1.5" for 90 s. */
export const minutesText = (seconds) => (seconds / 60).toFixed(seconds % 60 ? 1 : 0);

/** Value shown in the poll interval input. */
export function pollIntervalValue(settings) {
  const eff = settings.poll_interval_s_effective || 1800;
  return settings.poll_interval_s !== "" && settings.poll_interval_s != null ? settings.poll_interval_s : eff;
}

/** Ollama endpoint presets (only fill the field; the user still saves). */
export const OLLAMA_NATIVE_URL = "http://host.docker.internal:11434";
export const OLLAMA_BUNDLED_URL = "http://ollama:11434";

/** Body of PUT /api/settings for the LLM card. */
export function llmSaveBody({ provider, model, region, endpoint, endpointDisabled, key }) {
  const epv = (endpoint || "").trim();
  const b = { llm_provider: provider, llm_model: (model || "").trim(), llm_region: (region || "").trim() };
  if (provider === "ollama") {
    if (!endpointDisabled) b.ollama_url = epv;
    b.llm_base_url = "";
  } else {
    b.llm_base_url = epv;
  }
  if (key) b.llm_api_key = key;
  return b;
}

/** Body of PUT /api/settings for the SMTP card. */
export function smtpSaveBody({ host, port, user, from, tls, ssl, pass }) {
  const b = {
    smtp_host: (host || "").trim(),
    smtp_port: parseInt(port) || null,
    smtp_user: (user || "").trim(),
    smtp_from: (from || "").trim(),
    smtp_tls: !!tls,
    smtp_ssl: !!ssl,
  };
  const p = (pass || "").trim();
  if (p) b.smtp_pass = p;
  return b;
}

/** Body of PUT /api/settings for the S3 card. */
export function s3SaveBody({ bucket, region, key, prefix, enabled, secret }) {
  const b = {
    s3_bucket: (bucket || "").trim(),
    s3_region: (region || "").trim(),
    s3_access_key_id: (key || "").trim(),
    s3_prefix: (prefix || "").trim(),
    s3_enabled: !!enabled,
  };
  const sec = (secret || "").trim();
  if (sec) b.s3_secret_access_key = sec;
  return b;
}

/** Busy refusals the user may override with a best-effort copy. */
export const isBusyRefusal = (message) => /currently busy|sync is currently running/i.test(message || "");
export const isTargetNotEmpty = (message) => /already contains data/i.test(message || "");
