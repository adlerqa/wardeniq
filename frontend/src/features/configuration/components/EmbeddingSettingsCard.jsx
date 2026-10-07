/** EmbeddingSettingsCard configuration section. */
export default function EmbeddingSettingsCard() {
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
        <select id="cfg-embed-provider">
          <option value="ollama">Ollama (built-in)</option>
          <option value="openai">OpenAI</option>
          <option value="gemini">Google Gemini</option>
          <option value="voyage">Voyage AI</option>
          <option value="openai-compatible">OpenAI-compatible (custom)</option>
          <option value="bedrock">AWS Bedrock (enterprise)</option>
        </select>
      </div>
      <div className="cfg-field">
        <label>
          Model
          <span className="fi" tabIndex="0" data-tip="The embedding model. Ollama: nomic-embed-text. OpenAI: text-embedding-3-small. AWS Bedrock: amazon.titan-embed-text-v2:0 or cohere.embed-english-v3.">i</span>
        </label>
        <select id="cfg-embed-model-select"></select>
        <input id="cfg-embed-model" placeholder="Enter model name / Bedrock model ID..." style={{ display: "none", marginTop: "6px" }} />
      </div>
      <div className="cfg-field" id="cfg-embed-region-field">
        <label>
          AWS region
          <span className="muted" style={{ fontWeight: "400" }}>(AWS Bedrock only)</span>
          <span className="fi" tabIndex="0" data-tip="AWS Bedrock only. The AWS region your Bedrock embedding model is enabled in, e.g. us-east-1. Leave blank for every other provider.">i</span>
        </label>
        <input id="cfg-embed-region" placeholder="e.g. us-east-1" />
      </div>
      <div className="cfg-field">
        <label>
          API key / secret
          <span className="fi" tabIndex="0" data-tip="Hosted providers: your API key. AWS Bedrock: leave blank to use the machine's IAM role, or enter accessKeyId:secretAccessKey. Ollama: leave blank.">i</span>
        </label>
        <input type="password" id="cfg-embed-key" placeholder="API token is required" />
      </div>
      <div className="cfg-field">
        <label>
          Endpoint URL
          <span className="muted" style={{ fontWeight: "400" }}>(optional)</span>
          <span className="fi" tabIndex="0" data-tip="Leave blank for the provider default. OpenAI-compatible: your custom base URL. AWS Bedrock: an optional private VPC / PrivateLink endpoint for air-gapped networks.">i</span>
        </label>
        <input id="cfg-embed-base" placeholder="Endpoint URL is required" />
      </div>
      <div className="cfg-status muted" id="cfg-embed-status"></div>
      <div id="cfg-embed-log" className="cfg-log" style={{ display: "none", whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "11px", marginTop: "8px", maxHeight: "160px", overflow: "auto" }}></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-embed-save">Switch &amp; re-embed</button>
      </div>
    </div>
  );
}
