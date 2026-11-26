/** Shared imp-modal overlay. */
export default function ImportSheetModal() {
  return (
    <div className="modal sheet-modal" id="imp-modal" role="dialog" aria-modal="true" aria-labelledby="imp-heading">
      <div className="box">
        <div className="editor-head">
          <div className="sheet-head-left">
            <div className="sheet-icon">XLS</div>
            <div className="sheet-title">
              <h2 id="imp-heading">Import test cases</h2>
              <div className="muted" id="imp-subtitle">Upload a spreadsheet and link tests to this feature.</div>
            </div>
          </div>
          <button className="ghost sheet-close" id="imp-close">Close</button>
        </div>
        <div className="sheet-body">
          <div className="muted" style={{ fontSize: "14px", maxWidth: "720px" }}>Upload a CSV or XLSX spreadsheet containing your test cases. WardenIQ will automatically extract and link them to this feature.</div>
          <div className="sheet-template-panel">
            <div>
              <b>Need a template?</b>
              <div className="muted">Download our system-shaped starter template to format your testcases.</div>
            </div>
            <div className="sheet-template-actions">
              <button className="ghost" id="imp-template-csv" type="button">CSV Template</button>
              <button className="ghost" id="imp-template-xlsx" type="button">XLSX Template</button>
            </div>
          </div>
          <div className="sheet-upload-panel">
            <div className="sheet-file-row">
              <input type="file" id="imp-file" aria-label="Spreadsheet file to import" accept=".csv,.xlsx,.xlsm,.tsv" />
              <button className="ghost sheet-file-btn" id="imp-file-pick" type="button">Choose file</button>
              <button className="ghost" id="imp-file-clear" type="button">Clear</button>
              <span className="sheet-selected" id="imp-selected">Selected: none</span>
            </div>
            <div className="muted" style={{ marginTop: "14px" }}>Imported test cases are saved as feature memory to be inherited by future versions.</div>
            <div className="sheet-progress" id="imp-progress" hidden>
              <span></span>
            </div>
            <div id="imp-status" className="sheet-status"></div>
          </div>
          <div id="imp-summary"></div>
        </div>
        <div className="sheet-footer">
          <button className="ghost" id="imp-cancel" type="button">Cancel</button>
          <button className="go sheet-primary" id="imp-upload">Upload and analyse</button>
        </div>
      </div>
    </div>
  );
}
