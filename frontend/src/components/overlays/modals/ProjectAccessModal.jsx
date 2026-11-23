/** Shared pmodal overlay. */
export default function ProjectAccessModal() {
  return (
    <div className="modal" id="pmodal" role="dialog" aria-modal="true" aria-labelledby="pm-title">
      <div className="box" style={{ maxWidth: "420px" }}>
        <h2 id="pm-title" style={{ margin: "0 0 6px", fontSize: "16px" }}>Input</h2>
        <label id="pm-label" htmlFor="pm-input">Value</label>
        <input id="pm-input" />
        <div style={{ marginTop: "14px", display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button className="ghost" id="pm-cancel">Cancel</button>
          <button className="go" id="pm-ok">OK</button>
        </div>
      </div>
    </div>
  );
}
