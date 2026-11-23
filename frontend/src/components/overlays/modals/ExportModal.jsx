/** Shared export-modal overlay. */
export default function ExportModal() {
  return (
    <div className="modal" id="export-modal" role="dialog" aria-modal="true" aria-labelledby="export-title">
      <div className="box" style={{ maxWidth: "820px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
          <div>
            <h2 id="export-title" style={{ margin: "0" }}>Export test-case report</h2>
            <div className="muted" id="export-sub" style={{ marginTop: "4px" }}></div>
          </div>
          <button className="ghost" id="export-close">Close</button>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", marginTop: "14px", flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", margin: "0", color: "var(--text)" }}>
            <input type="checkbox" id="export-select-all" style={{ width: "auto" }} defaultChecked />
            Select all visible test cases
          </label>
          <span className="muted" id="export-count"></span>
        </div>
        <div className="export-list" id="export-list"></div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px", flexWrap: "wrap" }}>
          <button className="ghost" id="export-csv">Download CSV</button>
          <button className="go" id="export-pdf">Download PDF report</button>
        </div>
      </div>
    </div>
  );
}
