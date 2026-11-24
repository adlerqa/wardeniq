/*
 * Markup shared by the two import dialogs. Styled by the `.sheet-*` rules in
 * styles/compat/02-overlays-and-auth.css (kept until the compat styles go).
 */

export function SheetKpis({ kpis }) {
  return (
    <div className="sheet-summary-grid">
      {kpis.map(([label, value, tone, icon]) => (
        <div key={label} className={`sheet-kpi ${tone}`}>
          <div className="l">{label}</div>
          <div className="v">{value}</div>
          <div className="ico">{icon}</div>
        </div>
      ))}
    </div>
  );
}

export function SheetPill({ tone = "", children }) {
  return <span className={tone ? `sheet-pill ${tone}` : "sheet-pill"}>{children}</span>;
}

/** Steps / expected box and the optional "Reason:" line of an imported row. */
export function SheetDetail({ steps, expected }) {
  return (
    <div className="sheet-detail-box">
      <b>Steps:</b> {steps}
      <br />
      <b>Expected:</b> {expected || "As described in the imported row."}
    </div>
  );
}
