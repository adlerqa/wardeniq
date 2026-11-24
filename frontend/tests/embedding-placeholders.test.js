import assert from "node:assert/strict";
import test from "node:test";

import { embeddingPlaceholders, smtpPasswordPlaceholder } from "../src/features/configuration/lib/config.js";

function placeholders(provider, settings = {}) {
  const { key, endpoint } = embeddingPlaceholders(provider, settings);
  return { key, endpoint, smtp: (smtpSettings) => smtpPasswordPlaceholder(smtpSettings) };
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
