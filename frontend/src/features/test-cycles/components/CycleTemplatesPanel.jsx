/** Saved case sets that new cycles can start from. */
export default function CycleTemplatesPanel({ tc }) {
  const templates = tc.templates;
  return (
    <div className="card">
      <h2>Cycle templates</h2>
      <div className="sub">Reusable case sets — save any cycle as a template, then spin up new cycles from it.</div>
      <div id="cyc-templates">
        {templates == null ? null : templates.length ? (
          templates.map((t) => (
            <div key={t.id} className="feat" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px" }}>
              <div>
                <div className="n">{t.name}</div>
                <div className="m">{`${t.case_count} case(s)${t.description ? ` · ${t.description}` : ""}`}</div>
              </div>
              <div style={{ display: "flex", gap: "6px" }}>
                <button className="go" style={{ padding: "5px 12px" }} onClick={() => tc.newFromTemplate(t.id)}>
                  New cycle
                </button>
                <button className="danger" style={{ padding: "5px 12px" }} onClick={() => tc.deleteTemplate(t.id)}>
                  Delete
                </button>
              </div>
            </div>
          ))
        ) : (
          <span className="muted">no templates yet — open a cycle and click “Save as template”</span>
        )}
      </div>
    </div>
  );
}
