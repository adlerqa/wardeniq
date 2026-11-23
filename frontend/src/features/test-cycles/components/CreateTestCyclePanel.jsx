/** CreateTestCyclePanel for test-cycles. */
export default function CreateTestCyclePanel() {
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: "0" }}>Create a test cycle</h2>
          <div className="sub">Spin up a release regression cycle for a project, then add the cases you want to retest — independent of change-impact analysis.</div>
        </div>
        <button className="ghost" id="tcy-refresh">
          <span className="icon">↻</span>
          <span>Refresh</span>
        </button>
      </div>
      <div className="row" style={{ marginTop: "12px", alignItems: "flex-end", gap: "10px", flexWrap: "wrap" }}>
        <div style={{ flex: "0 0 240px" }}>
          <label>Project</label>
          <select id="tcy-proj" style={{ height: "38px" }} aria-label="Filter by Panel"></select>
        </div>
        <div style={{ flex: "1", minWidth: "200px" }}>
          <label>Cycle name</label>
          <input id="tcy-name" placeholder="e.g. Sprint 12 regression" />
        </div>
        <button className="go" id="tcy-new" style={{ flex: "0 0 auto" }}>+ New cycle</button>
      </div>
    </div>
  );
}
