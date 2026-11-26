/** Shared jlogmodal overlay. */
export default function JobLogModal() {
  return (
    <div className="modal" id="jlogmodal" role="dialog" aria-modal="true" aria-labelledby="jlm-heading">
      <div className="box" style={{ maxWidth: "700px", width: "90%" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
          <h2 id="jlm-heading" style={{ margin: "0", fontSize: "16px" }}>Job execution logs</h2>
          <button className="ghost" id="jlm-close">close</button>
        </div>
        <div id="jlm-meta" className="muted" style={{ fontSize: "12px", marginBottom: "8px" }}></div>
        <pre id="jlm-logs" style={{ background: "var(--panel2)", border: "1px solid var(--line)", padding: "12px", borderRadius: "6px", fontFamily: "monospace", fontSize: "12px", height: "350px", overflowY: "auto", whiteSpace: "pre-wrap", margin: "0" }}></pre>
        <div style={{ marginTop: "14px", display: "flex", justifyContent: "flex-end" }}>
          <button className="ghost" id="jlm-cancel">Close</button>
        </div>
      </div>
    </div>
  );
}
