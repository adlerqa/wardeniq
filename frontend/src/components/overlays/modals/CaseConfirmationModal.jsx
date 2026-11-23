/** Shared case-confirm overlay. */
export default function CaseConfirmationModal() {
  return (
    <div className="modal" id="case-confirm" role="dialog" aria-modal="true" aria-labelledby="cc-title">
      <div className="box confirm-box">
        <h2 id="cc-title" style={{ margin: "0", fontSize: "17px" }}>Confirm testcase update</h2>
        <div id="cc-copy" className="muted" style={{ marginTop: "5px" }}></div>
        <div id="cc-summary" className="confirm-summary"></div>
        <div id="cc-error" className="err"></div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
          <button className="danger" id="cc-secondary" style={{ display: "none", marginRight: "auto" }}></button>
          <button className="ghost" id="cc-cancel">Cancel</button>
          <button className="go" id="cc-confirm">Update testcase</button>
        </div>
      </div>
    </div>
  );
}
