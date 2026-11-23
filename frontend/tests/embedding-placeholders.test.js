import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../src/compat/runtime/controllers/06-configuration.js", import.meta.url),
  "utf8",
);
const start = source.indexOf("function updateEmbeddingFieldPlaceholders");
const end = source.indexOf("\nasync function loadConfig()", start);
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end);

function placeholders(provider, settings = {}) {
  const elements = {
    "#cfg-embed-key": { placeholder: "" },
    "#cfg-embed-base": { placeholder: "" },
    "#cfg-smtp-pass": { placeholder: "" },
  };
  const context = vm.createContext({
    $: (selector) => elements[selector] || null,
  });
  vm.runInContext(
    `${helperSource}; this.updateEmbeddingFieldPlaceholders = updateEmbeddingFieldPlaceholders; this.updateSmtpPasswordPlaceholder = updateSmtpPasswordPlaceholder;`,
    context,
  );
  context.updateEmbeddingFieldPlaceholders(provider, settings);
  return {
    key: elements["#cfg-embed-key"].placeholder,
    endpoint: elements["#cfg-embed-base"].placeholder,
    smtp: (smtpSettings) => {
      context.updateSmtpPasswordPlaceholder(smtpSettings);
      return elements["#cfg-smtp-pass"].placeholder;
    },
  };
}

test("Ollama placeholders explain that the key and endpoint are optional", () => {
  const result = placeholders("ollama");
  assert.equal(result.key, "Optional — no key needed for bundled Ollama");
  assert.equal(result.endpoint, "Not used with Ollama");
});

test("Bedrock credentials and endpoint remain optional", () => {
  const result = placeholders("bedrock");
  assert.equal(result.key, "Optional — use an AWS IAM role or access keys");
  assert.equal(result.endpoint, "Optional — uses the provider default");
});

test("hosted providers require an API key but use their default endpoint", () => {
  const result = placeholders("openai");
  assert.equal(result.key, "API key is required");
  assert.equal(result.endpoint, "Optional — uses the provider default");
});

test("OpenAI-compatible embeddings require a custom endpoint", () => {
  const result = placeholders("openai-compatible");
  assert.equal(result.key, "API key is required");
  assert.equal(result.endpoint, "Custom endpoint URL is required");
});

test("saved credentials and custom endpoints keep the current-value hint", () => {
  const result = placeholders("openai", {
    embed_provider: "openai",
    embed_api_key_set: true,
    embed_base_url: "https://embeddings.example",
  });
  assert.equal(result.key, "Leave blank to keep current");
  assert.equal(result.endpoint, "Leave blank to keep current");
});

test("switching away from the saved provider refreshes its hints", () => {
  const result = placeholders("ollama", {
    embed_provider: "openai",
    embed_api_key_set: true,
    embed_base_url: "https://embeddings.example",
  });
  assert.equal(result.key, "Optional — no key needed for bundled Ollama");
  assert.equal(result.endpoint, "Not used with Ollama");
});

test("SMTP placeholder describes the password and keeps saved-password behavior", () => {
  const result = placeholders("ollama");
  assert.equal(result.smtp({}), "SMTP password or app password");
  assert.equal(result.smtp({ smtp_pass_set: true }), "Leave blank to keep current");
});
