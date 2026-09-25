/** LlmSettingsCard configuration section. */
export default function LlmSettingsCard() {
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
        <select id="cfg-llm-provider">
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
          <span className="fi" tabIndex="0" data-tip="The model identifier. Ollama: qwen2.5:7b. OpenAI: gpt-4o. Anthropic: claude-sonnet-4-6. AWS Bedrock: the full model ID or inference-profile ARN, e.g. anthropic.claude-3-5-sonnet-20241022-v2:0.">i</span>
        </label>
        <select id="cfg-llm-model-select"></select>
        <input id="cfg-llm-model" placeholder="Enter model name / Bedrock model ID..." style={{ display: "none", marginTop: "6px" }} />
      </div>
      <div className="cfg-field" id="cfg-llm-endpoint-field">
        <label>
          Endpoint URL
          <span className="muted" style={{ fontWeight: "400" }}>(optional)</span>
          <span className="fi" tabIndex="0" data-tip="Leave blank for the provider default. Ollama: where Ollama runs (bundled Docker, your computer, or a remote host). OpenAI-compatible: your custom base URL. AWS Bedrock: an optional private VPC / PrivateLink endpoint for air-gapped networks.">i</span>
        </label>
        <input id="cfg-llm-endpoint" placeholder="Endpoint URL is required" />
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "6px" }} id="cfg-ollama-presets">
          <button type="button" className="ghost" id="cfg-ollama-native" style={{ fontSize: "11.5px", padding: "5px 10px" }}>Use Ollama on my computer</button>
          <button type="button" className="ghost" id="cfg-ollama-bundled" style={{ fontSize: "11.5px", padding: "5px 10px" }}>Use bundled (Docker) Ollama</button>
        </div>
        <div className="muted" id="cfg-ollama-hint" style={{ fontSize: "11px", marginTop: "6px" }}></div>
      </div>
      <div className="cfg-field" id="cfg-llm-region-field">
        <label>
          AWS region
          <span className="muted" style={{ fontWeight: "400" }}>(AWS Bedrock only)</span>
          <span className="fi" tabIndex="0" data-tip="AWS Bedrock only. The AWS region your Bedrock models are enabled in, e.g. us-east-1. Leave blank for every other provider.">i</span>
        </label>
        <input id="cfg-llm-region" placeholder="e.g. us-east-1" />
      </div>
      <div className="cfg-field">
        <label>
          API key / secret
          <span className="fi" tabIndex="0" data-tip="Ollama: usually blank (only for a secured/remote Ollama behind a token). Hosted providers: your API key. AWS Bedrock: leave blank to use the machine's IAM role (recommended for air-gapped), or enter accessKeyId:secretAccessKey.">i</span>
        </label>
        <input type="password" id="cfg-llm-key" placeholder="API token is required" />
      </div>
      <div className="cfg-status muted" id="cfg-llm-status"></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-llm-save">Save</button>
      </div>
    </div>
  );
}
