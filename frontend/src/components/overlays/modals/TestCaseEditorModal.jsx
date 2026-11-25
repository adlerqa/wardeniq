import useCaseEditor from "../../../features/test-cases/hooks/useCaseEditor.js";

function EditorMsg({ msg }) {
  if (!msg) return null;
  if (msg.kind === "ok") return <span className="ok">{msg.text}</span>;
  if (msg.kind === "err") return <span className="err">{msg.text}</span>;
  return msg.text;
}

/** One step row: action, expected result, remove; rows drag to reorder. */
function StepRow({ s, i, ed }) {
  const cls = `steprow${ed.drag.from === i ? " dragging" : ""}${ed.drag.over === i ? " drag-over" : ""}`;
  return (
    <div
      className={cls}
      draggable="true"
      data-i={i}
      onDragStart={(e) => ed.dragStart(i, e)}
      onDragEnd={ed.dragEnd}
      onDragOver={(e) => ed.dragOver(i, e)}
      onDragLeave={() => ed.dragLeave(i)}
      onDrop={(e) => ed.drop(i, e)}
    >
      <div className="drag-handle">⋮⋮</div>
      <textarea
        draggable="false"
        data-i={i}
        data-f="action"
        placeholder="action"
        value={s.action}
        onChange={(e) => ed.setStep(i, "action", e.target.value)}
      ></textarea>
      <textarea
        draggable="false"
        data-i={i}
        data-f="expected"
        placeholder="expected"
        value={s.expected}
        onChange={(e) => ed.setStep(i, "expected", e.target.value)}
      ></textarea>
      <div className="ctrl">
        <button className="iconbtn" title="Remove step from this testcase" onClick={() => ed.removeStep(i)}>
          ×
        </button>
      </div>
      {s.usage_count > 1 ? (
        <div className="editor-shared-note">
          {`This exact step is shared by ${s.usage_count} testcases. Editing its text updates all of them; removing it only unlinks it from this testcase.`}
        </div>
      ) : null}
    </div>
  );
}

/** The test case editor dialog (useCaseEditor). */
export default function TestCaseEditorModal() {
  const ed = useCaseEditor();
  const field = (k) => ({ value: ed.form[k], onChange: (e) => ed.setField(k, e.target.value) });
  return (
    <div className={`modal${ed.show ? " show" : ""}`} id="modal">
      <div className="box editor-box">
        <div className="editor-head">
          <div>
            <h2 id="m-heading" style={{ margin: "0", fontSize: "17px" }}>
              {ed.heading}
            </h2>
            <div className="muted" style={{ marginTop: "3px" }}>Keep the action and its expected result together. Drag rows to reorder them.</div>
          </div>
          <button className="ghost" id="m-close" onClick={ed.close}>
            close
          </button>
        </div>
        <div className="editor-body">
          <label>Title</label>
          <input id="m-title" {...field("title")} />
          <div className="editor-grid">
            <div>
              <label>Category</label>
              <select id="m-type" {...field("type")}>
                <option value="functional">Business / functional</option>
                <option value="e2e">End-to-end</option>
                <option value="api">API</option>
                <option value="ui">UI validation</option>
                <option value="nfr">Edge &amp; reliability</option>
              </select>
            </div>
            <div>
              <label>Priority</label>
              <select id="m-prio" {...field("prio")}>
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
            </div>
          </div>
          <div className="editor-grid">
            <div>
              <label>Preconditions</label>
              <input id="m-pre" {...field("pre")} />
            </div>
            <div>
              <label>Tags (comma separated)</label>
              <input id="m-tags" {...field("tags")} />
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
            <div id="m-steps">
              {ed.steps.map((s, i) => (
                <StepRow key={i} s={s} i={i} ed={ed} />
              ))}
            </div>
          </div>
          <button className="ghost" id="m-addstep" style={{ marginTop: "9px" }} onClick={ed.addStep}>
            + Add step
          </button>
          <div id="m-warn" className="muted" style={{ marginTop: "9px" }}>
            {ed.warn}
          </div>
          <div id="m-msg" className="muted" style={{ marginTop: "8px" }}>
            <EditorMsg msg={ed.msg} />
          </div>
        </div>
        <div className="editor-foot">
          <button
            className="danger"
            id="m-del"
            style={{ marginRight: "auto", display: ed.canDelete ? "" : "none" }}
            onClick={ed.deleteCase}
          >
            Delete testcase
          </button>
          <button className="ghost" id="m-cancel" onClick={ed.close}>
            Cancel
          </button>
          <button className="go" id="m-save" disabled={ed.saving} onClick={ed.review}>
            Review changes
          </button>
        </div>
      </div>
    </div>
  );
}
