import {
  fmtTok,
  fmtUsd,
  modelText,
  projectLabel,
  projectText,
  recentRow,
  recentText,
  rowShown,
  statCards,
} from "../lib/usage.js";

const ICONS = {
  total: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="3"></circle>
      <path d="M19 12a7 7 0 0 0-7-7"></path>
      <path d="M5 12a7 7 0 0 0 7 7"></path>
      <path d="M12 2v3"></path>
      <path d="M12 19v3"></path>
      <path d="M2 12h3"></path>
      <path d="M19 12h3"></path>
    </svg>
  ),
  input: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3v12"></path>
      <path d="m7 10 5 5 5-5"></path>
      <path d="M5 21h14"></path>
    </svg>
  ),
  output: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 21V9"></path>
      <path d="m7 14 5-5 5 5"></path>
      <path d="M5 3h14"></path>
    </svg>
  ),
  cost: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9"></circle>
      <path d="M12 6v12"></path>
      <path d="M16 8.5c-.8-1-2-1.5-4-1.5-2.2 0-3.5 1-3.5 2.5 0 3.5 7 1.5 7 5 0 1.5-1.3 2.5-3.5 2.5-1.8 0-3.3-.6-4-1.5"></path>
    </svg>
  ),
};

/** Contents of #usage-totals. */
export function UsageTotals({ us }) {
  if (us.error) return <div className="err">{us.error}</div>;
  if (!us.data) return null;
  return statCards(us.data.totals).map((c) => (
    <div key={c.type} className={`usage-stat-card usage-stat-${c.type}`}>
      <div className="usage-stat-head">
        <span className="usage-stat-label">{c.label}</span>
        <span className="usage-stat-icon">{ICONS[c.type]}</span>
      </div>
      <div className="usage-stat-value">{c.value}</div>
      <div className="usage-stat-description">{c.description}</div>
    </div>
  ));
}

const hideUnless = (shown) => (shown ? undefined : { display: "none" });

/** Contents of #usage-recent. */
export function RecentTable({ us }) {
  if (!us.data) return null;
  if (!us.data.recent.length) return <span className="muted">No processes yet.</span>;
  return (
    <table>
      <tbody>
        <tr>
          <th>Process</th>
          <th>Project</th>
          <th>Feature</th>
          <th>Status</th>
          <th>When</th>
          <th>Models</th>
          <th>Total tokens</th>
          <th>Est. cost</th>
        </tr>
        {us.data.recent.map((j, i) => {
          const r = recentRow(j);
          return (
            <tr key={i} style={hideUnless(rowShown(recentText(r), us.search))}>
              <td>{r.process}</td>
              <td>{r.project}</td>
              <td>{r.feature}</td>
              <td>
                <span className={r.statusClass}>{r.status}</span>
              </td>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>
                {r.when}
              </td>
              <td>
                <span className="muted" style={{ fontSize: "11px" }}>
                  {r.models}
                </span>
              </td>
              <td>{r.tokens}</td>
              <td>{r.cost}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Contents of #usage-by-model. */
export function ModelTable({ us }) {
  if (!us.data) return null;
  if (!us.data.models.length)
    return <span className="muted">No usage recorded yet — run a generation or analysis.</span>;
  return (
    <table>
      <tbody>
        <tr>
          <th>Model</th>
          <th>Type</th>
          <th>Calls</th>
          <th>Input</th>
          <th>Output</th>
          <th>Total</th>
          <th>Est. cost</th>
        </tr>
        {us.data.models.map(([m, d]) => (
          <tr key={m} style={hideUnless(rowShown(modelText([m, d]), us.model))}>
            <td>
              <code>{m}</code>
              {d.estimated ? (
                <>
                  {" "}
                  <span className="muted" title="tokens estimated">
                    ~est
                  </span>
                </>
              ) : null}
            </td>
            <td>{d.kind || ""}</td>
            <td>{fmtTok(d.calls)}</td>
            <td>{fmtTok(d.prompt_tokens)}</td>
            <td>{fmtTok(d.completion_tokens)}</td>
            <td>{fmtTok(d.total_tokens)}</td>
            <td>{fmtUsd(d.cost_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Contents of #usage-by-project. */
export function ProjectTable({ us }) {
  if (!us.data) return null;
  if (!us.data.projects.length) return <span className="muted">—</span>;
  return (
    <table>
      <tbody>
        <tr>
          <th>Project</th>
          <th>Total tokens</th>
          <th>Est. cost</th>
        </tr>
        {us.data.projects.map((p, i) => (
          <tr key={i} style={hideUnless(rowShown(projectText(p), us.project))}>
            <td>{projectLabel(p)}</td>
            <td>{fmtTok(p.total_tokens)}</td>
            <td>{fmtUsd(p.cost_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
