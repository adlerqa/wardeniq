import { typeLabel } from "../../test-cases/lib/testCases.js";
import { StepsTable } from "../../test-cycles/components/TestCycleDetailPanel.jsx";
import {
  doneText,
  evidenceFileLine,
  impactNarrative,
  impactStatusBadge,
  plural,
  riskBadge,
  runningText,
  signalLabel,
  sourceLabel,
} from "../lib/codeAnalysis.js";

/** Contents of #cyc-status. */
export function AnalysisStatus({ status }) {
  if (!status) return null;
  if (status.kind === "text") return status.text;
  if (status.kind === "muted") return <span className="muted">{status.text}</span>;
  if (status.kind === "error") return <span className="err">{status.text}</span>;
  if (status.kind === "failed") return <span className="err">{`Analysis failed: ${status.text}`}</span>;
  if (status.kind === "running") return runningText(status.stage, status.result);
  return doneText(status.result);
}

function RiskBadge({ risk }) {
  const r = riskBadge(risk);
  return (
    <span
      style={{
        fontSize: "10px",
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: "999px",
        border: `1px solid ${r.border}`,
        background: r.background,
        color: r.color,
      }}
    >
      {r.label}
    </span>
  );
}

function Evidence({ ev }) {
  if (!(ev || []).length)
    return (
      <div className="cycle-impact-empty">
        No direct code evidence was saved for this item. It was surfaced from the broader impact review.
      </div>
    );
  return (
    <div className="cycle-impact-evidence">
      <div className="cycle-impact-evidence-label">Code evidence</div>
      {ev.map((e, i) => {
        const commit = (e.sha || "").slice(0, 7);
        const row = (
          <>
            <span className="cycle-impact-evidence-file">{evidenceFileLine(e)}</span>
            <span className="cycle-impact-evidence-meta">
              {commit ? <span className="pill">{commit}</span> : null}
              {e.repo ? <span className="badge">{e.repo}</span> : null}
            </span>
          </>
        );
        return e.url ? (
          <a key={i} className="cycle-impact-evidence-row" href={e.url} target="_blank" rel="noopener noreferrer">
            {row}
          </a>
        ) : (
          <div key={i} className="cycle-impact-evidence-row">
            {row}
          </div>
        );
      })}
    </div>
  );
}

function ImpactItem({ c, checked, onToggle }) {
  const evidenceCount = (c.evidence || []).length;
  const status = impactStatusBadge(c.status);
  const type = c.type || "functional";
  return (
    <details className="cycle-impact-item">
      <summary>
        {/* Clicking around the checkbox must not open / close the row. */}
        <span
          className="cycle-impact-check"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
        >
          <input
            type="checkbox"
            className="imp-chk"
            checked={checked}
            onChange={(e) => onToggle(e.target.checked)}
            onClick={(e) => e.stopPropagation()}
            style={{ width: "auto" }}
          />
        </span>
        <span className="cycle-impact-toggle" aria-hidden="true"></span>
        <div className="cycle-impact-main">
          <div className="cycle-impact-title">
            {c.display_id ? (
              <code
                style={{
                  fontSize: "10px",
                  background: "rgba(255,255,255,.06)",
                  padding: "1px 6px",
                  borderRadius: "4px",
                  color: "#94a3b8",
                  marginRight: "6px",
                }}
              >
                {c.display_id}
              </code>
            ) : null}
            {c.title}
          </div>
          <div className="cycle-impact-sub">
            <span>{typeLabel(c.type)}</span>
            <span>·</span>
            <span>{sourceLabel(c)}</span>
            <span>·</span>
            <span>{`${evidenceCount} evidence point${evidenceCount === 1 ? "" : "s"}`}</span>
          </div>
        </div>
        <div className="cycle-impact-badges">
          <span className={`badge ${status.cls}`}>{status.label}</span>
          <span className={`badge ${type}`}>{typeLabel(type)}</span>
          <RiskBadge risk={c.risk} />
        </div>
      </summary>
      <div className="cycle-impact-body">
        <div className="cycle-impact-summary">{impactNarrative(c)}</div>
        <StepsTable steps={c.steps} />
        {c.signal ? (
          <div className="cycle-impact-signal">
            <span className="pill">{signalLabel(c.signal_type)}</span>
            <code>{c.signal}</code>
          </div>
        ) : null}
        <Evidence ev={c.evidence} />
      </div>
    </details>
  );
}

/** Contents of #cyc-impacted. */
export function ImpactResults({ ca }) {
  const imp = ca.impacted;
  if (!imp) return null;
  const list = imp.list;
  if (!list.length)
    return (
      <div className="mindmap-summary-card">
        <div className="mindmap-summary-head">
          <h2>No impacted test cases</h2>
          <div className="mindmap-chip-row">
            <span className="badge">0 impacted</span>
          </div>
        </div>
        <div className="sub">
          No recent changes in the selected repositories mapped to the current test suite for this lookback window.
        </div>
      </div>
    );
  const n = ca.selected.size;
  return (
    <>
      <div className="mindmap-summary-card">
        <div className="mindmap-summary-head">
          <h2>Impact review</h2>
          <div className="mindmap-chip-row">
            <span className="badge mm-covered">{`${imp.grounded} direct evidence`}</span>
            <span className="badge mm-partial">{`${imp.ai} needs review`}</span>
            <span className="badge">{`${list.length} impacted cases`}</span>
          </div>
        </div>
        <div className="sub">
          These testcases are the strongest candidates for regression based on the selected code changes. Open any row
          to inspect the matching signal and exact evidence.
        </div>
      </div>
      <div className="mindmap-feature-card">
        <div className="mindmap-feature-head">
          <div>
            <div className="mindmap-feature-title">
              <strong>Impacted test cases</strong>
            </div>
            <div className="mindmap-feature-meta">
              Select the cases you want to carry into a release regression cycle.
            </div>
          </div>
          <div className="mindmap-chip-row">
            <span className="pill">{plural(list.length, "case")}</span>
          </div>
        </div>
        <div className="mindmap-case-list" key={imp.key}>
          <div className="cycles-select-bar" style={{ alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            <label className="case-select-label" style={{ margin: "0" }}>
              <input
                type="checkbox"
                id="imp-select-all"
                checked={n > 0 && n === list.length}
                onChange={(e) => ca.toggleAll(e.target.checked)}
                style={{ width: "auto" }}
              />
              {" Select all impacted cases"}
            </label>
            <span className="cycles-select-count" id="imp-selected-count">{`${n} selected`}</span>
            <button
              className="go"
              id="imp-create-top"
              style={{ marginLeft: "auto", padding: "6px 14px" }}
              onClick={ca.createCycle}
            >
              Create cycle from selected
            </button>
          </div>
          {list.map((c, i) => (
            <ImpactItem key={i} c={c} checked={ca.selected.has(i)} onToggle={(on) => ca.toggleCase(i, on)} />
          ))}
        </div>
      </div>
      {imp.commits.length ? (
        <div className="card mindmap-diagnostics cycles-commit-list">
          <details>
            <summary>{`${imp.commits.length} commits reviewed as evidence`}</summary>
            <div className="sub">
              {imp.commits.map((cm, i) => (
                <div key={i} className="stepitem">
                  {cm.repo ? (
                    <>
                      <span className="pill">{cm.repo}</span>{" "}
                    </>
                  ) : null}
                  <a href={cm.url ?? ""} target="_blank" rel="noopener noreferrer">
                    {cm.sha}
                  </a>{" "}
                  <span className="muted">{cm.message}</span>
                </div>
              ))}
            </div>
          </details>
        </div>
      ) : null}
    </>
  );
}
