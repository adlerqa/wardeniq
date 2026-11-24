import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
import React, { act } from "react";

// Create the DOM globals before react-dom loads (see api-tokens-panel.test.js).
const dom = new JSDOM("<!doctype html><body></body>", { url: "http://localhost/" });
const { window } = dom;
const { document } = window;
Object.assign(globalThis, { window, document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import("react-dom/client");
test.after(() => window.close());

const entry = fileURLToPath(new URL("../src/features/configuration/pages/ConfigurationPage.jsx", import.meta.url));
const bundled = await build({
  entryPoints: [entry],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "neutral",
  jsx: "automatic",
  external: ["react", "react/jsx-runtime", "react-dom"],
  loader: { ".css": "empty" },
  logLevel: "silent",
});
const require = createRequire(import.meta.url);
const settle = () => new Promise((r) => setTimeout(r, 0));

const SETTINGS = {
  llm_provider: "openai",
  llm_model: "gpt-4o-mini",
  llm_region: "",
  llm_base_url: "",
  llm_api_key_set: true,
  provider_lock: "",
  ollama_url: "",
  ollama_url_effective: "http://ollama:11434",
  ollama_url_env_locked: false,
  poll_interval_s: "",
  poll_interval_s_effective: 1800,
  poll_interval_min_s: 30,
  poll_interval_env_writable: true,
  jira_base_url: "",
  jira_email: "",
  jira_token_set: false,
  jira_token_readable: false,
  smtp_host: "",
  smtp_tls: true,
  smtp_ssl: false,
  smtp_configured: false,
  smtp_pass_set: false,
  figma_token_set: false,
  embed_provider: "ollama",
  embed_model: "nomic-embed-text",
  embed_dim: 768,
  embed_api_key_set: false,
  embed_base_url: "",
  embed_model_options: {
    ollama: [{ id: "nomic-embed-text", dim: 768 }, { id: "mxbai-embed-large", dim: 1024 }],
    openai: [{ id: "text-embedding-3-small", dim: 1536 }],
    bedrock: [{ id: "amazon.titan-embed-text-v2:0", dim: 1024 }],
  },
  s3_bucket: "",
  s3_configured: false,
};

function harness(t, { settings = SETTINGS, routes = {} } = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  delete window.loadConfig;
  const calls = { toast: [], prompt: [], confirm: [], sync: 0, jobLog: [] };
  let current = settings;
  const answers = { prompt: null, confirm: false };
  Object.assign(window, {
    toast: (m, o) => calls.toast.push([m, o === true ? "err" : o?.type || "", o?.title || ""]),
    uiPrompt: async (...a) => {
      calls.prompt.push(a);
      return answers.prompt;
    },
    confirmModal: async (o) => {
      calls.confirm.push(o);
      return answers.confirm;
    },
    loadSyncStatus: () => calls.sync++,
    getCurrentUser: () => ({ email: "admin@example.test" }),
    formatBootStatus: (b) => ({ summary: b.stage === "error" ? "not ready" : "", raw: b.detail || "" }),
    watchJob: (id, cb) => calls.jobLog.push(cb),
    renderJobLog: (sel, j) => calls.jobLog.push([sel, j.status]),
  });
  const requests = [];
  async function fakeFetch(path, opts = {}) {
    const method = opts.method || "GET";
    requests.push([method, path, opts.body ? JSON.parse(opts.body) : undefined]);
    const route = routes[`${method} ${path}`];
    let [status, body] = route
      ? route(opts)
      : path === "/api/settings" && method === "GET"
        ? [200, current]
        : path === "/api/db-status"
          ? [200, { boot: { ready: true } }]
          : [200, { ok: true }];
    return { status, ok: status < 300, text: async () => JSON.stringify(body) };
  }
  const module = { exports: {} };
  vm.runInNewContext(bundled.outputFiles[0].text, {
    module, exports: module.exports, require, window, document, console, fetch: fakeFetch, setTimeout,
  });
  const root = createRoot(container);
  t.after(async () => {
    try {
      await act(async () => root.unmount());
    } catch {
      /* already unmounted by the test */
    }
    container.remove();
  });
  const $ = (sel) => container.querySelector(sel);
  const flush = async (fn) =>
    act(async () => {
      await fn?.();
      for (let i = 0; i < 6; i++) await settle();
    });
  const valueSetter = (el) =>
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), el.type === "checkbox" ? "checked" : "value").set;
  return {
    $, calls, requests, answers, root,
    setSettings: (s) => (current = s),
    async mount() {
      await act(async () => root.render(React.createElement(module.exports.default)));
    },
    async open() {
      await this.mount();
      await flush(() => window.loadConfig());
    },
    async type(sel, value) {
      const el = $(sel);
      await flush(() => {
        valueSetter(el).call(el, value);
        el.dispatchEvent(new window.Event(el.tagName === "SELECT" || el.type === "checkbox" ? "change" : "input", { bubbles: true }));
      });
    },
    async check(sel, value) {
      const el = $(sel);
      await flush(() => {
        if (el.checked !== value) el.click();
      });
    },
    async click(sel) {
      await flush(() => $(sel).dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    },
    puts: () => requests.filter(([m, p]) => m === "PUT" && p === "/api/settings").map(([, , b]) => b),
  };
}

test("registers window.loadConfig without fetching; loads every card", async (t) => {
  const h = harness(t);
  await h.mount();
  assert.equal(h.requests.length, 0);
  assert.equal(h.$("#cfg-db-body").textContent, "Loading database status…");
  assert.equal(h.$("#cfg-llm-model-select").options.length, 0);
  await h.open();
  assert.equal(typeof window.loadConfig, "function");
  assert.deepEqual(h.requests.map(([m, p]) => `${m} ${p}`), ["GET /api/settings", "GET /api/db-status"]);
  assert.equal(h.$("#cfg-llm-provider").value, "openai");
  assert.equal(h.$("#cfg-llm-model-select").value, "gpt-4o-mini");
  assert.equal(h.$("#cfg-llm-model").style.display, "none");
  assert.equal(h.$("#cfg-ollama-presets").style.display, "none");
  assert.equal(h.$("#cfg-llm-key").placeholder, "Leave blank to keep current");
  assert.equal(h.$("#cfg-llm-endpoint").placeholder, "Optional — uses the provider default");
  assert.equal(h.$("#cfg-llm-status").innerHTML, '<span class="ok">API key / secret configured</span>');
  assert.equal(h.$("#cfg-embed-model-select").value, "nomic-embed-text");
  assert.equal(h.$("#cfg-embed-status").textContent, "Active: ollama / nomic-embed-text · 768-d");
  assert.equal(h.$("#cfg-jira-status").innerHTML, '<span class="muted">no Jira token set</span>');
  assert.equal(h.$("#cfg-figma-status").innerHTML, '<span class="muted">no Figma token set</span>');
  assert.equal(h.$("#cfg-smtp-status").innerHTML, '<span class="warn">not configured — email sign-in unavailable</span>');
  assert.equal(h.$("#cfg-smtp-tls").checked, true);
  assert.equal(h.$("#cfg-s3-prefix").value, "documents");
  assert.equal(h.$("#cfg-s3-enabled").checked, false);
  assert.equal(h.$("#cfg-poll-interval").value, "1800");
  assert.equal(
    h.$("#cfg-poll-status").innerHTML,
    "In use: <code>1800s</code> (≈ 30 min). Saved values are also written to <code>.env</code>.",
  );
  assert.equal(h.$("#cfg-db-switch").style.display, "block");
  assert.match(h.$("#cfg-db-body").innerHTML, /<span class="ok">● connected<\/span>/);
});

test("LLM provider change, Ollama presets and the pinned Ollama URL", async (t) => {
  const h = harness(t);
  await h.open();
  await h.type("#cfg-llm-provider", "ollama");
  assert.deepEqual(
    [...h.$("#cfg-llm-model-select").options].map((o) => o.value),
    ["llama3.2:1b", "qwen2.5:3b", "llama3.2:3b", "qwen2.5:7b"],
  );
  assert.equal(h.$("#cfg-llm-model").value, "llama3.2:1b");
  assert.equal(h.$("#cfg-ollama-presets").style.display, "flex");
  assert.equal(h.$("#cfg-llm-key").placeholder, "Optional — only for secured Ollama endpoints");
  assert.match(h.$("#cfg-ollama-hint").innerHTML, /^Click <b>Use bundled \(Docker\) Ollama<\/b>/);
  await h.click("#cfg-ollama-native");
  assert.equal(h.$("#cfg-llm-endpoint").value, "http://host.docker.internal:11434");
  assert.match(h.$("#cfg-ollama-hint").textContent, /stop the bundled Ollama/);
  await h.click("#cfg-ollama-bundled");
  assert.equal(h.$("#cfg-llm-endpoint").value, "http://ollama:11434");
  await h.type("#cfg-llm-provider", "bedrock");
  assert.equal(h.$("#cfg-llm-model-select").style.display, "none");
  assert.equal(h.$("#cfg-llm-model").style.display, "block");
  assert.equal(h.$("#cfg-llm-endpoint").value, "");
  assert.equal(h.$("#cfg-ollama-hint").innerHTML, "");

  h.setSettings({ ...SETTINGS, llm_provider: "ollama", llm_model: "qwen2.5:7b", ollama_url_env_locked: true, ollama_url_effective: "http://gpu:11434" });
  await h.click("#cfg-llm-save"); // any save reloads; use the button path instead of the hook
  const ep = h.$("#cfg-llm-endpoint");
  assert.equal(h.$("#cfg-llm-provider").value, "ollama");
  assert.equal(ep.value, "http://gpu:11434");
  assert.equal(ep.disabled, true);
  assert.equal(
    h.$("#cfg-ollama-hint").innerHTML,
    "Pinned by <code>OLLAMA_URL</code> in <code>.env</code> (takes priority). Edit <code>.env</code> to change it.",
  );
  await h.click("#cfg-ollama-native");
  assert.equal(ep.value, "http://gpu:11434", "a pinned URL is not replaced by a preset");
});

test("provider lock pins the LLM select and hides internet embedders", async (t) => {
  const h = harness(t, { settings: { ...SETTINGS, llm_provider: "bedrock", llm_model: "anthropic.m", provider_lock: "bedrock", embed_provider: "openai" } });
  await h.open();
  assert.equal(h.$("#cfg-llm-provider").value, "bedrock");
  assert.equal(h.$("#cfg-llm-provider").disabled, true);
  assert.equal(h.$("#cfg-llm-model").value, "anthropic.m");
  const hidden = [...h.$("#cfg-embed-provider").options].filter((o) => o.hidden).map((o) => o.value);
  assert.deepEqual(hidden, ["openai", "gemini", "voyage", "openai-compatible"]);
  assert.equal(h.$("#cfg-embed-provider").value, "ollama");
});

test("LLM save: body, success after reload, key cleared; failure shows the error and a toast", async (t) => {
  let fail = false;
  const h = harness(t, {
    routes: { "PUT /api/settings": () => (fail ? [400, { detail: "Invalid API key" }] : [200, { ok: true }]) },
  });
  await h.open();
  await h.type("#cfg-llm-key", "sk-1");
  await h.type("#cfg-llm-region", " us-east-1 ");
  await h.click("#cfg-llm-save");
  assert.deepEqual(h.puts().at(-1), {
    llm_provider: "openai", llm_model: "gpt-4o-mini", llm_region: "us-east-1", llm_base_url: "", llm_api_key: "sk-1",
  });
  assert.equal(h.$("#cfg-llm-status").innerHTML, '<span class="ok">LLM settings saved</span>');
  assert.equal(h.$("#cfg-llm-key").value, "");
  assert.equal(h.$("#cfg-llm-region").value, "", "fields re-read from the reloaded settings");
  assert.equal(h.$("#cfg-llm-save").textContent, "Save");
  fail = true;
  await h.type("#cfg-llm-key", "sk-2");
  await h.click("#cfg-llm-save");
  assert.equal(h.$("#cfg-llm-status").innerHTML, '<span class="err">Invalid API key</span>');
  assert.deepEqual(h.calls.toast.at(-1), ["Invalid API key", "err", "Couldn't save LLM settings"]);
  assert.equal(h.$("#cfg-llm-key").value, "sk-2");
});

test("saving one card reloads the others but keeps typed secrets", async (t) => {
  const h = harness(t);
  await h.open();
  await h.type("#cfg-smtp-pass", "pw");
  await h.type("#cfg-jira-base", "https://draft");
  await h.type("#cfg-figma-token", "ft");
  await h.click("#cfg-figma-save");
  assert.deepEqual(h.puts().at(-1), { figma_api_token: "ft" });
  assert.equal(h.$("#cfg-figma-status").innerHTML, '<span class="ok">Figma token saved</span>');
  assert.equal(h.$("#cfg-figma-token").value, "");
  assert.equal(h.$("#cfg-smtp-pass").value, "pw");
  assert.equal(h.$("#cfg-jira-base").value, "", "non-secret fields are re-read, as loadConfig did");
});

test("validation toasts: Jira, Figma, poll interval, embedding model", async (t) => {
  const h = harness(t, { settings: { ...SETTINGS, jira_token_set: true } });
  await h.open();
  await h.click("#cfg-jira-save");
  assert.deepEqual(h.calls.toast.at(-1), ["Your saved Jira API token can no longer be read — re-enter it to save", "err", ""]);
  assert.equal(h.$("#cfg-jira-token").placeholder, "Saved token can't be read — re-enter it");
  await h.click("#cfg-figma-save");
  assert.deepEqual(h.calls.toast.at(-1), ["Enter a Figma token", "err", ""]);
  await h.type("#cfg-poll-interval", "10");
  await h.click("#cfg-poll-save");
  assert.deepEqual(h.calls.toast.at(-1), ["Enter a poll interval of at least 30 seconds", "err", ""]);
  await h.type("#cfg-embed-provider", "openai-compatible");
  await h.click("#cfg-embed-save");
  assert.deepEqual(h.calls.toast.at(-1), ["Choose or enter an embedding model", "err", ""]);
  assert.equal(h.puts().length, 0);
});

test("Jira with nothing configured is blocked; poll, SMTP and S3 saves", async (t) => {
  const h = harness(t);
  await h.open();
  await h.click("#cfg-jira-save");
  assert.deepEqual(h.calls.toast.at(-1), ["Enter Base URL, Email and API token to configure Jira", "err", ""]);
  await h.type("#cfg-poll-interval", "90");
  await h.click("#cfg-poll-save");
  assert.deepEqual(h.puts().at(-1), { poll_interval_s: 90 });
  assert.equal(h.$("#cfg-poll-status").innerHTML, '<span class="ok">Poll interval set to 90s (≈ 1.5 min)</span>');
  assert.equal(h.calls.sync, 1);
  await h.type("#cfg-smtp-host", "smtp.example.test");
  await h.type("#cfg-smtp-port", "465");
  await h.check("#cfg-smtp-ssl", true);
  await h.type("#cfg-smtp-pass", " pw ");
  await h.click("#cfg-smtp-save");
  assert.deepEqual(h.puts().at(-1), {
    smtp_host: "smtp.example.test", smtp_port: 465, smtp_user: "", smtp_from: "", smtp_tls: true, smtp_ssl: true, smtp_pass: "pw",
  });
  assert.equal(h.$("#cfg-smtp-status").innerHTML, '<span class="ok">SMTP settings saved</span>');
  await h.click("#cfg-s3-save");
  assert.equal(h.puts().at(-1).s3_prefix, "documents");
  assert.equal(h.$("#cfg-s3-status").innerHTML, '<span class="ok">Settings saved</span>');
});

test("SMTP test email and S3 connection test", async (t) => {
  const h = harness(t, {
    routes: {
      "POST /api/smtp/test": () => [500, { detail: "Auth failed" }],
      "POST /api/settings/s3/test": () => [200, { message: "Connected to bucket b" }],
    },
  });
  await h.open();
  await h.click("#cfg-smtp-test");
  assert.deepEqual(h.calls.prompt[0], ["Send test email", "Send a test sign-in email to:", "admin@example.test"]);
  assert.equal(h.requests.filter(([, p]) => p === "/api/smtp/test").length, 0, "cancelled prompt sends nothing");
  h.answers.prompt = " to@example.test ";
  await h.click("#cfg-smtp-test");
  assert.deepEqual(h.requests.at(-1), ["POST", "/api/smtp/test", { email: "to@example.test" }]);
  assert.equal(h.$("#cfg-smtp-status").innerHTML, '<span class="err">Auth failed</span>');
  assert.equal(h.$("#cfg-smtp-test").textContent, "Send test email");
  await h.click("#cfg-s3-test");
  assert.equal(h.$("#cfg-s3-status").innerHTML, '<span class="err">Enter an S3 bucket name to test connection</span>');
  await h.type("#cfg-s3-bucket", "b");
  await h.type("#cfg-s3-secret", "sec");
  await h.click("#cfg-s3-test");
  assert.deepEqual(h.requests.at(-1)[2], { bucket: "b", region: "", access_key_id: "", secret_access_key: "sec" });
  assert.equal(h.$("#cfg-s3-status").innerHTML, '<span class="ok">Connected to bucket b</span>');
});

test("embedding switch: confirm, start, job log, done reloads", async (t) => {
  const h = harness(t, {
    routes: {
      "POST /api/embedding/switch": () => [200, { provider: "openai", model: "text-embedding-3-small", dim: 1536, job_id: "j1" }],
    },
  });
  await h.open();
  await h.type("#cfg-embed-provider", "openai");
  assert.equal(h.$("#cfg-embed-key").placeholder, "API key is required");
  assert.equal(h.$("#cfg-embed-base").placeholder, "Optional — uses the provider default");
  assert.equal(h.$("#cfg-embed-model-select").value, "text-embedding-3-small");
  await h.type("#cfg-embed-key", "k");
  await h.click("#cfg-embed-save");
  assert.equal(h.calls.confirm[0].confirmText, "Switch & re-embed");
  assert.equal(h.requests.filter(([, p]) => p === "/api/embedding/switch").length, 0, "declined: nothing sent");
  h.answers.confirm = true;
  await h.click("#cfg-embed-save");
  assert.deepEqual(h.requests.at(-1)[2], { provider: "openai", model: "text-embedding-3-small", base_url: "", region: "", api_key: "k" });
  assert.equal(h.$("#cfg-embed-status").innerHTML, '<span class="ok">Switching to openai/text-embedding-3-small (1536-d) — re-embedding…</span>');
  assert.equal(h.$("#cfg-embed-log").style.display, "block");
  assert.equal(h.$("#cfg-embed-key").value, "");
  assert.ok(h.$("#cfg-embed-save").disabled);
  const onTick = h.calls.jobLog.find((x) => typeof x === "function");
  const loads = h.requests.filter(([, p]) => p === "/api/settings").length;
  await act(async () => {
    onTick({ status: "succeeded" });
    for (let i = 0; i < 6; i++) await settle();
  });
  assert.deepEqual(h.calls.jobLog.at(-1), ["#cfg-embed-log", "succeeded"]);
  assert.equal(h.requests.filter(([, p]) => p === "/api/settings").length, loads + 1);
  assert.equal(h.$("#cfg-embed-save").disabled, false);
});

test("database status: error with details, request failure", async (t) => {
  let mode = "boot-error";
  const h = harness(t, {
    routes: {
      "GET /api/db-status": () =>
        mode === "boot-error"
          ? [200, { boot: { stage: "error", ready: false, detail: "mongot refused <b>x</b>" } }]
          : [500, { detail: "db status boom" }],
    },
  });
  await h.open();
  assert.equal(
    h.$("#cfg-db-body .db-v").innerHTML,
    '<span class="err">⚠ not ready</span><details class="boot-banner-details"><summary>Details</summary><pre class="boot-banner-raw">mongot refused &lt;b&gt;x&lt;/b&gt;</pre></details>',
  );
  mode = "fail";
  await h.click("#cfg-db-refresh");
  assert.equal(h.$("#cfg-db-body").innerHTML, '<span class="err">db status boom</span>');
  assert.equal(h.$("#cfg-db-switch").style.display, "block");
});

test("window.loadConfig is removed on unmount", async (t) => {
  const h = harness(t);
  await h.mount();
  const hook = window.loadConfig;
  assert.equal(typeof hook, "function");
  await act(async () => h.root.unmount());
  assert.equal(window.loadConfig, undefined);
});
