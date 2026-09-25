/** DatabaseSettingsCard configuration section. */
export default function DatabaseSettingsCard() {
  return (
    <div className="card cfg-card">
      <div className="cfg-head">
        <div className="cfg-head-left">
          <span className="cfg-step">7</span>
          <h2>Database</h2>
        </div>
        <span className="cfg-badge glob">Global</span>
      </div>
      <div className="sub">
        Connect wardenIQ to a search-capable MongoDB (Atlas, or self-managed with mongot). Enter the connection string below. It is saved to{" "}
        <code>.env</code>{" "}
        and never shown again.
      </div>
      <div id="cfg-db-body" className="db-panel">
        <span className="muted">Loading database status…</span>
      </div>
      <div id="cfg-db-switch" style={{ marginTop: "16px", borderTop: "1px solid rgba(255,255,255,.06)", paddingTop: "14px", display: "none" }}>
        <div className="muted" style={{ fontSize: "12px", lineHeight: "1.55", marginBottom: "12px" }}>Enter the database you&apos;d like to use. wardenIQ copies your data into it and switches over — your current database is left untouched until you restart, so nothing is lost.</div>
        <div className="cfg-field">
          <label>
            Database connection string
            <span className="fi" tabIndex="0" data-tip="A search-capable MongoDB URI (Atlas mongodb+srv://… or a self-managed replica set with mongot). wardenIQ copies your data into it and switches over. Saved to .env, encrypted, and never shown again.">i</span>
          </label>
          <input type="password" id="cfg-db-uri" placeholder="mongodb+srv://user:pass@cluster…" autoComplete="off" />
        </div>
        <div className="cfg-status muted" id="cfg-db-status"></div>
        <div className="cfg-actions" style={{ border: "none", padding: "0", margin: "0" }}>
          <button className="go" id="cfg-db-switch-go">Switch to this database</button>
        </div>
      </div>
      <div className="cfg-actions">
        <button className="ghost" id="cfg-db-refresh">Refresh</button>
      </div>
    </div>
  );
}
