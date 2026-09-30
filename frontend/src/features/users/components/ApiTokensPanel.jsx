/** ApiTokensPanel for users: create/revoke service-account API tokens. */
export default function ApiTokensPanel() {
  return (
    <div className="card">
      <h2>API tokens</h2>
      <div className="sub">
        Service accounts for CI jobs and other machine callers. An API token authenticates with{" "}
        <code>Authorization: Bearer &lt;token&gt;</code>{" "}
        instead of a login — no password, no invite flow.
      </div>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div style={{ flex: "2" }}>
          <label>Name</label>
          <input id="at-name" placeholder="e.g. GitHub Actions — coverage check" />
        </div>
        <div style={{ flex: "0 0 140px" }}>
          <label>Role</label>
          <select id="at-role">
            <option value="viewer">Viewer</option>
            <option value="editor">Editor</option>
          </select>
        </div>
        <div style={{ flex: "0 0 140px" }}>
          <label>Expires (days)</label>
          <input id="at-expires-days" type="number" min="1" placeholder="never" />
        </div>
        <button className="go" id="at-create" style={{ margin: "0" }}>Create token</button>
      </div>
      <div className="proj-access" id="at-proj-access" style={{ marginTop: "14px" }}>
        <label style={{ display: "block", marginBottom: "6px" }}>Project access</label>
        <div className="proj-access-toggle">
          <label className="radio-inline">
            <input type="radio" name="at-scope" defaultValue="all" defaultChecked />
            All projects
          </label>
          <label className="radio-inline">
            <input type="radio" name="at-scope" defaultValue="some" />
            Specific projects
          </label>
        </div>
        <div id="at-proj-list" className="proj-checklist" hidden></div>
      </div>
      <div className="muted" id="at-msg" style={{ marginTop: "8px" }}></div>
      <div id="at-list" style={{ marginTop: "14px" }}></div>
    </div>
  );
}
