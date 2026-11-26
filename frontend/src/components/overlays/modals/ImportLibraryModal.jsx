/** Shared implib-modal overlay. */
export default function ImportLibraryModal() {
  return (
    <div className="modal sheet-modal" id="implib-modal" role="dialog" aria-modal="true" aria-labelledby="implib-heading">
      <div className="box">
        <div className="editor-head">
          <div className="sheet-head-left">
            <div className="sheet-icon">DOC</div>
            <div className="sheet-title">
              <h2 id="implib-heading">Reuse imported sheets</h2>
              <div className="muted">Expand an imported sheet and add rows into this feature. Existing rows are reused automatically, so duplicates stay out of the generated list.</div>
            </div>
          </div>
          <button className="ghost sheet-close" id="implib-close">Close</button>
        </div>
        <div className="sheet-body">
          <div id="implib-stats"></div>
          <div className="sheet-section-head">
            <div>
              <div className="typehdr">Project imported sheets</div>
              <div className="muted">Expand any uploaded sheet and toggle rows. Click Save changes when done.</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
              <span className="badge" id="implib-loaded-count">0 rows loaded</span>
              <button className="ghost" id="implib-refresh" type="button">Refresh / rescore</button>
            </div>
          </div>
          <div id="implib-list" className="sheet-list"></div>
        </div>
        <div className="sheet-footer">
          <button className="ghost" id="implib-cancel" type="button">Cancel</button>
          <button className="go sheet-primary" id="implib-save" type="button" disabled>Save changes</button>
        </div>
      </div>
    </div>
  );
}
