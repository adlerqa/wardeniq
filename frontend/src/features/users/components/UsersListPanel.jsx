/** UsersListPanel for users. */
export default function UsersListPanel() {
  return (
    <div className="card">
      <h2>Users</h2>
      <div className="u-filters" id="u-filters">
        <input id="u-search" type="search" placeholder="Search name or email…" style={{ flex: "1", minWidth: "180px" }} />
        <select id="u-filter-status" style={{ width: "auto" }}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
          <option value="pending">Invite pending</option>
        </select>
        <select id="u-filter-role" style={{ width: "auto" }}>
          <option value="">All roles</option>
          <option value="admin">Admin</option>
          <option value="editor">Editor</option>
          <option value="viewer">Viewer</option>
        </select>
        <span className="muted" id="u-count" style={{ fontSize: "12px", marginLeft: "auto" }}></span>
      </div>
      <div id="u-list"></div>
    </div>
  );
}
