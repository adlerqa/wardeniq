/** InviteUserPanel for users. */
export default function InviteUserPanel() {
  return (
    <div className="card">
      <h2>Invite a user</h2>
      <div className="sub">
        New users sign in passwordlessly with an emailed one-time code.{" "}
        <b>Viewer</b>{" "}
        = read-only,{" "}
        <b>Editor</b>{" "}
        = create/edit/generate,{" "}
        <b>Admin</b>{" "}
        = also manage users &amp; configuration.
      </div>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div style={{ flex: "2" }}>
          <label>Email</label>
          <input id="u-email" type="email" placeholder="teammate@company.com" />
        </div>
        <div>
          <label>Name</label>
          <input id="u-name" placeholder="optional" />
        </div>
        <div style={{ flex: "0 0 140px" }}>
          <label>Role</label>
          <select id="u-role">
            <option value="viewer">Viewer</option>
            <option value="editor">Editor</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button className="go" id="u-invite" style={{ margin: "0" }}>Invite</button>
      </div>
      <div className="proj-access" id="u-proj-access" style={{ marginTop: "14px" }}>
        <label style={{ display: "block", marginBottom: "6px" }}>Project access</label>
        <div className="proj-access-toggle">
          <label className="radio-inline">
            <input type="radio" name="u-scope" defaultValue="all" defaultChecked />
            All projects
          </label>
          <label className="radio-inline">
            <input type="radio" name="u-scope" defaultValue="some" />
            Specific projects
          </label>
        </div>
        <div id="u-proj-list" className="proj-checklist" hidden></div>
        <div className="muted" id="u-proj-hint" style={{ fontSize: "11.5px", marginTop: "4px" }}>Admins always have access to all projects.</div>
      </div>
      <div className="muted" id="u-msg" style={{ marginTop: "8px" }}></div>
    </div>
  );
}
