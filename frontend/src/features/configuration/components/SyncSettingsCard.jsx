/** SyncSettingsCard configuration section. */
export default function SyncSettingsCard() {
  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">8</span>
          <h2>Sync &amp; polling</h2>
        </div>
        <span className="cfg-badge glob">Global</span>
      </div>
      <div className="sub">
        How often wardenIQ polls your watched GitHub repositories for new commits &amp; pull requests. GitLab is webhook-driven and unaffected. Applies on the next poll — no restart needed — and is also written to{" "}
        <code>.env</code>{" "}
        (
        <code>POLL_INTERVAL_SECONDS</code>
        ) so the config file stays in sync.
      </div>
      <div className="cfg-field" style={{ maxWidth: "320px" }}>
        <label>
          Poll interval (seconds)
          <span className="fi" tabIndex="0" data-tip="Seconds between GitHub polls of watched repos. Lower = fresher but more API calls; higher = fewer calls. Minimum 30s. Common values: 300 (5 min), 1800 (30 min), 3600 (1 hour).">i</span>
        </label>
        <input type="number" id="cfg-poll-interval" min="30" step="30" placeholder="1800" />
      </div>
      <div className="cfg-status muted" id="cfg-poll-status"></div>
      <div className="cfg-actions">
        <button className="go" id="cfg-poll-save">Save</button>
      </div>
    </div>
  );
}
