/** Shared confirm-modal overlay. */
export default function ConfirmationModal() {
  return (
    <div className="modal" id="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="box confirm-box" style={{ maxWidth: "460px" }}>
        <h2 id="confirm-title" style={{ margin: "0", fontSize: "17px" }}>Please confirm</h2>
        <div id="confirm-body" className="muted" style={{ marginTop: "8px", lineHeight: "1.5", whiteSpace: "pre-wrap" }}></div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "18px" }}>
          <button className="ghost" id="confirm-cancel">Cancel</button>
          <button className="go" id="confirm-ok">Continue</button>
        </div>
      </div>
    </div>
  );
}
