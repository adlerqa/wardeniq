import assert from "node:assert/strict";
import test from "node:test";

import {
  embedModelChoice,
  embedProviderAllowed,
  figmaTokenPlaceholder,
  jiraTokenPlaceholder,
  llmModelChoice,
  llmPlaceholders,
  llmSaveBody,
  minutesText,
  pollIntervalValue,
  s3SaveBody,
  s3SecretPlaceholder,
  smtpSaveBody,
} from "../src/features/configuration/lib/config.js";

test("LLM placeholders follow the provider and what is saved for it", () => {
  assert.deepEqual(llmPlaceholders("ollama", {}), {
    key: "Optional — only for secured Ollama endpoints",
    endpoint: "Optional — blank uses bundled Ollama",
  });
  assert.deepEqual(llmPlaceholders("bedrock", {}), {
    key: "Optional — use an AWS IAM role or access keys",
    endpoint: "Optional — uses the provider default",
  });
  assert.deepEqual(llmPlaceholders("openai-compatible", {}), {
    key: "API key is required",
    endpoint: "Custom endpoint URL is required",
  });
  const saved = { llm_provider: "openai", llm_api_key_set: true, llm_base_url: "https://x" };
  assert.deepEqual(llmPlaceholders("openai", saved), {
    key: "Leave blank to keep current",
    endpoint: "Leave blank to keep current",
  });
  assert.equal(llmPlaceholders("anthropic", saved).key, "API key is required");
  assert.equal(
    llmPlaceholders("ollama", { llm_provider: "ollama", ollama_url: "http://o" }).endpoint,
    "Blank resets to bundled Ollama",
  );
  assert.equal(
    llmPlaceholders("ollama", { ollama_url_env_locked: true }).endpoint,
    "Blank resets to bundled Ollama",
  );
});

test("token placeholders", () => {
  assert.equal(jiraTokenPlaceholder({}), "API token is required");
  assert.equal(jiraTokenPlaceholder({ jira_token_set: true }), "Saved token can't be read — re-enter it");
  assert.equal(jiraTokenPlaceholder({ jira_token_set: true, jira_token_readable: true }), "Leave blank to keep current");
  assert.equal(figmaTokenPlaceholder({ figma_token_set: true }), "Leave blank to keep current");
  assert.equal(s3SecretPlaceholder({}), "Secret Access Key (optional)");
});

test("model pickers: curated list with first-model fallback, else free text", () => {
  const anthropic = llmModelChoice("anthropic", "claude-haiku-4-5");
  assert.equal(anthropic.freeText, false);
  assert.equal(anthropic.value, "claude-haiku-4-5");
  assert.equal(anthropic.options[0].label, "Claude Opus 4.8 (newest)");
  assert.equal(llmModelChoice("openai", "gpt-unknown").value, "gpt-5");
  assert.deepEqual(llmModelChoice("bedrock", "anthropic.x"), { options: [], value: "anthropic.x", freeText: true });
  const opts = { ollama: [{ id: "nomic-embed-text", dim: 768 }, { id: "mxbai", dim: 1024 }] };
  assert.deepEqual(embedModelChoice(opts, "ollama", "mxbai"), {
    options: [
      { value: "nomic-embed-text", label: "nomic-embed-text (768-d)" },
      { value: "mxbai", label: "mxbai (1024-d)" },
    ],
    value: "mxbai",
    freeText: false,
  });
  assert.equal(embedModelChoice(opts, "openai-compatible", "m").freeText, true);
  assert.ok(embedProviderAllowed("", "voyage"));
  assert.ok(embedProviderAllowed("bedrock", "ollama"));
  assert.ok(!embedProviderAllowed("bedrock", "openai"));
});

test("poll interval and minutes", () => {
  assert.equal(pollIntervalValue({ poll_interval_s: "", poll_interval_s_effective: 900 }), 900);
  assert.equal(pollIntervalValue({ poll_interval_s: 300 }), 300);
  assert.equal(pollIntervalValue({}), 1800);
  assert.equal(minutesText(300), "5");
  assert.equal(minutesText(90), "1.5");
});

test("save bodies", () => {
  assert.deepEqual(
    llmSaveBody({ provider: "ollama", model: " qwen2.5:7b ", region: "", endpoint: " http://o ", endpointDisabled: false, key: "" }),
    { llm_provider: "ollama", llm_model: "qwen2.5:7b", llm_region: "", ollama_url: "http://o", llm_base_url: "" },
  );
  assert.deepEqual(
    llmSaveBody({ provider: "ollama", model: "m", region: "", endpoint: "x", endpointDisabled: true, key: "" }),
    { llm_provider: "ollama", llm_model: "m", llm_region: "", llm_base_url: "" },
  );
  assert.deepEqual(
    llmSaveBody({ provider: "bedrock", model: "m", region: " eu-west-1 ", endpoint: "https://vpce", key: "a:b" }),
    { llm_provider: "bedrock", llm_model: "m", llm_region: "eu-west-1", llm_base_url: "https://vpce", llm_api_key: "a:b" },
  );
  assert.deepEqual(smtpSaveBody({ host: " h ", port: "587", user: "", from: "", tls: true, ssl: false, pass: "  " }), {
    smtp_host: "h", smtp_port: 587, smtp_user: "", smtp_from: "", smtp_tls: true, smtp_ssl: false,
  });
  assert.equal(smtpSaveBody({ port: "" }).smtp_port, null);
  assert.equal(smtpSaveBody({ pass: " pw " }).smtp_pass, "pw");
  assert.deepEqual(s3SaveBody({ bucket: " b ", region: "r", key: "", prefix: "docs", enabled: true, secret: "" }), {
    s3_bucket: "b", s3_region: "r", s3_access_key_id: "", s3_prefix: "docs", s3_enabled: true,
  });
});
