/** Shared modal overlay. */
export default function TestCaseEditorModal() {
  return (
    <div className="modal" id="modal" role="dialog" aria-modal="true" aria-labelledby="m-heading">
      <div className="box editor-box">
        <div className="editor-head">
          <div>
            <h2 id="m-heading" style={{ margin: "0", fontSize: "17px" }}>Edit test case</h2>
            <div className="muted" style={{ marginTop: "3px" }}>Keep the action and its expected result together. Drag rows to reorder them.</div>
          </div>
          <button className="ghost" id="m-close">close</button>
        </div>
        <div className="editor-body">
          <label htmlFor="m-title">Title</label>
          <input id="m-title" />
          <div className="editor-grid">
            <div>
              <label htmlFor="m-type">Category</label>
              <select id="m-type">
                <option value="functional">Business / functional</option>
                <option value="e2e">End-to-end</option>
                <option value="api">API</option>
                <option value="ui">UI validation</option>
                <option value="nfr">Edge &amp; reliability</option>
              </select>
            </div>
            <div>
              <label htmlFor="m-prio">Priority</label>
              <select id="m-prio">
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
            </div>
          </div>
          <div className="editor-grid">
            <div>
              <label htmlFor="m-pre">Preconditions</label>
              <input id="m-pre" />
            </div>
            <div>
              <label htmlFor="m-tags">Tags (comma separated)</label>
              <input id="m-tags" />
            </div>
          </div>
          <label>Steps</label>
          <div className="editor-steps">
            <div className="editor-step-head">
              <span></span>
              <span>Action</span>
              <span>Expected result</span>
              <span></span>
            </div>
            <div id="m-steps"></div>
          </div>
          <button className="ghost" id="m-addstep" style={{ marginTop: "9px" }}>+ Add step</button>
          <div id="m-warn" className="muted" style={{ marginTop: "9px" }}></div>
          <div id="m-msg" className="muted" style={{ marginTop: "8px" }}></div>
        </div>
        <div className="editor-foot">
          <button className="danger" id="m-del" style={{ marginRight: "auto", display: "none" }}>Delete testcase</button>
          <button className="ghost" id="m-cancel">Cancel</button>
          <button className="go" id="m-save">Review changes</button>
        </div>
      </div>
    </div>
  );
}
