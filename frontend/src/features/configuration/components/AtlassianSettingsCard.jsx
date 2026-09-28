/** AtlassianSettingsCard configuration section. */
export default function AtlassianSettingsCard() {
  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">3</span>
          <h2>Jira &amp; Confluence (Atlassian Cloud)</h2>
        </div>
        <span className="cfg-badge opt">Optional</span>
      </div>
      <div className="sub">
        One Atlassian account for the whole workspace. wardenIQ uses it to read issues, list Jira projects/Confluence spaces when you create a project, and write coverage updates as comments. Create an API token at{" "}
        <code>id.atlassian.com → Security → API tokens</code>
        .
      </div>
      <div className="cfg-field">
        <label>
          Base URL
          <span className="fi" tabIndex="0" data-tip="Your Atlassian Cloud site URL, e.g. https://your-org.atlassian.net (no trailing path).">i</span>
        </label>
        <input id="cfg-jira-base" placeholder="https://your-org.atlassian.net" />
      </div>
      <div className="cfg-field">
        <label>
          Email
          <span className="fi" tabIndex="0" data-tip="The Atlassian account email that owns the API token below. Used with the token for Basic auth.">i</span>
        </label>
        <input id="cfg-jira-email" placeholder="you@org.com" />
      </div>
      <div className="cfg-field">
        <label>
          API token
          <span className="fi" tabIndex="0" data-tip="An Atlassian API token (not your password). Create one at id.atlassian.com → Security → API tokens. Stored encrypted; leave blank to keep the current one.">i</span>
        </label>
        <input type="password" id="cfg-jira-token" placeholder="API token is required" />
      </div>
      <div className="cfg-status muted" id="cfg-jira-status"></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-jira-save">Save</button>
      </div>
      <div className="muted" style={{ fontSize: "11px", marginTop: "10px" }}>
        Webhook:{" "}
        <code>/api/integrations/jira/webhook?token=&lt;WEBHOOK_SECRET&gt;</code>{" "}
        auto-creates features from new issues.
      </div>
    </div>
  );
}
